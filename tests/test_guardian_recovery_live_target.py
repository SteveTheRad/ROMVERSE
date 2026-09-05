from __future__ import annotations

import inspect
import json
import os
import stat
from dataclasses import replace
from datetime import UTC, datetime, timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from romverse.core.settings import ExperienceMode
from romverse.device.models import DeviceState
from romverse.guardian.audit import GuardianAuditStore
from romverse.guardian.recovery_live_target import (
    GuardianRecoveryLiveTargetReceiptService,
    RecoveryLiveTargetValidationError,
)
from romverse.guardian.recovery_preparation import GuardianRecoveryPreparationService
from romverse.ui.guardian_center import GuardianCenter
from tests.test_guardian_live_target_receipt import _AdbFixture, _FastbootFixture
from tests.test_guardian_recovery_preparation import _context

_OBSERVED_AT = datetime(2026, 9, 5, 10, 0, tzinfo=UTC)


def _live_context(tmp_path, monkeypatch, *, adb=None, fastboot=None):
    plans, _project, phone, autopilot, incident, route = _context(tmp_path, monkeypatch)
    preparations = GuardianRecoveryPreparationService(plans.store, plans.registry, autopilot)
    prepared = preparations.prepare(incident.incident_id, route.route_id, [phone])
    adb_fixture = adb or _AdbFixture()
    fastboot_fixture = fastboot or _FastbootFixture()
    service = GuardianRecoveryLiveTargetReceiptService(
        preparations,
        adb_fixture,
        fastboot_fixture,
        clock=lambda: _OBSERVED_AT,
    )
    return service, prepared, phone, autopilot, adb_fixture, fastboot_fixture


def test_recovery_live_target_binds_exact_preparation_with_read_only_probes(
    tmp_path, monkeypatch
) -> None:
    service, prepared, phone, _autopilot, adb, fastboot = _live_context(tmp_path, monkeypatch)

    receipt = service.observe(prepared, phone)

    assert receipt.preparation_id == prepared.preparation_id
    assert receipt.preparation_digest == prepared.preparation_digest
    assert receipt.incident_id == prepared.incident_id
    assert receipt.incident_record_digest == prepared.incident_record_digest
    assert receipt.route_id == prepared.route_id
    assert receipt.project_id == prepared.project_id
    assert receipt.device_key == prepared.device_key
    assert receipt.source_original_sha256 == prepared.source_original_sha256
    assert receipt.device_pack_id == prepared.device_pack_id
    assert receipt.device_pack_version == prepared.device_pack_version
    assert receipt.device_pack_sha256 == prepared.device_pack_sha256
    assert receipt.steps_digest == prepared.steps_digest
    assert receipt.expected_entry_mode == "bootloader"
    assert receipt.observed_entry_mode == "bootloader"
    assert receipt.expected_product == phone.product
    assert receipt.observed_product == phone.product
    assert receipt.observed_unlocked
    assert receipt.recorded_prewrite_slot == ""
    assert receipt.discovery_pass_count == 3
    assert receipt.probe_round_count == 2
    assert [item.variable for item in receipt.probe_results] == [
        "product",
        "unlocked",
        "is-userspace",
    ] * 2
    assert receipt.identity_verified
    assert not receipt.cryptographic_device_attestation
    assert not receipt.recovery_consent_available
    assert receipt.execution_authority == "none"
    assert not receipt.runtime_invoked
    assert not receipt.phone_changed
    assert adb.calls == 3
    assert fastboot.discovery_calls == 3
    assert fastboot.getvar_calls == ["product", "unlocked", "is-userspace"] * 2
    assert service.load(prepared, phone, now=_OBSERVED_AT + timedelta(seconds=60)) == receipt

    path = (
        service.store.workspace
        / "diagnostics"
        / "recovery-preparations"
        / prepared.incident_id
        / service.LATEST_NAME
    )
    serialized = path.read_text(encoding="utf-8")
    assert phone.serial not in serialized
    assert "set_active" not in serialized
    assert "flash" not in serialized
    if os.name != "nt":
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"product": "wrong", "unlocked": "yes", "is-userspace": "no"}, "product"),
        ({"product": "product", "unlocked": "no", "is-userspace": "no"}, "unlocked"),
        (
            {"product": "product", "unlocked": "yes", "is-userspace": "yes"},
            "is-userspace",
        ),
    ],
)
def test_recovery_live_target_rejects_identity_unlock_or_mode_mismatch(
    tmp_path, monkeypatch, values, message
) -> None:
    fastboot = _FastbootFixture(values=values)
    service, prepared, phone, *_rest = _live_context(
        tmp_path,
        monkeypatch,
        fastboot=fastboot,
    )

    with pytest.raises(RecoveryLiveTargetValidationError, match=message):
        service.observe(prepared, phone)

    assert not service._path(prepared.incident_id).exists()


def test_recovery_live_target_rejects_transport_swap_and_adb_ambiguity(
    tmp_path, monkeypatch
) -> None:
    swapped = _FastbootFixture(
        discovery=(
            "private-serial\tfastboot usb:1-2\n",
            "other-serial\tfastboot usb:1-3\n",
        )
    )
    service, prepared, phone, *_rest = _live_context(
        tmp_path,
        monkeypatch,
        fastboot=swapped,
    )
    with pytest.raises(RecoveryLiveTargetValidationError, match="reviewed device"):
        service.observe(prepared, phone)

    ambiguous = _AdbFixture(("List of devices attached\nother\tdevice usb:1-3\n",))
    service, prepared, phone, *_rest = _live_context(
        tmp_path,
        monkeypatch,
        adb=ambiguous,
    )
    with pytest.raises(RecoveryLiveTargetValidationError, match="exactly one Fastboot"):
        service.observe(prepared, phone)

    disconnected = _FastbootFixture(discovery=("",))
    service, prepared, phone, *_rest = _live_context(
        tmp_path,
        monkeypatch,
        fastboot=disconnected,
    )
    with pytest.raises(RecoveryLiveTargetValidationError, match="exactly one Fastboot"):
        service.observe(prepared, phone)

    multiple = _FastbootFixture(
        discovery=("private-serial\tfastboot usb:1-2\nother-serial\tfastboot usb:1-3\n",)
    )
    service, prepared, phone, *_rest = _live_context(
        tmp_path,
        monkeypatch,
        fastboot=multiple,
    )
    with pytest.raises(RecoveryLiveTargetValidationError, match="exactly one Fastboot"):
        service.observe(prepared, phone)


def test_recovery_live_target_expires_and_stale_preparation_cannot_be_observed(
    tmp_path, monkeypatch
) -> None:
    service, prepared, phone, autopilot, *_rest = _live_context(tmp_path, monkeypatch)
    receipt = service.observe(prepared, phone)

    assert service.load(prepared, phone, now=_OBSERVED_AT + timedelta(seconds=121)) is None
    autopilot.record_route_result(
        prepared.incident_id,
        prepared.route_id,
        "reviewed",
        "Incident evidence changed after live-target preparation.",
    )
    with pytest.raises(RecoveryLiveTargetValidationError, match="no longer matches"):
        service.observe(prepared, phone)
    assert receipt.execution_authority == "none"


def test_recovery_live_target_load_rejects_tamper_extra_duplicate_and_link(
    tmp_path, monkeypatch
) -> None:
    service, prepared, phone, *_rest = _live_context(tmp_path, monkeypatch)
    receipt = service.observe(prepared, phone)
    path = service._path(prepared.incident_id)
    original = path.read_text(encoding="utf-8")

    document = json.loads(original)
    document["execution_authority"] = "recovery"
    path.write_text(json.dumps(document), encoding="utf-8")
    assert service.load(prepared, phone, now=_OBSERVED_AT) is None

    document = json.loads(original)
    document["unexpected"] = True
    path.write_text(json.dumps(document), encoding="utf-8")
    assert service.load(prepared, phone, now=_OBSERVED_AT) is None

    duplicate = original.replace(
        '"schema_version": 1,',
        '"schema_version": 1, "schema_version": 1,',
        1,
    )
    assert duplicate != original
    path.write_text(duplicate, encoding="utf-8")
    assert service.load(prepared, phone, now=_OBSERVED_AT) is None

    if os.name != "nt":
        target = path.with_name("ordinary-recovery-target.json")
        target.write_text(original, encoding="utf-8")
        path.unlink()
        path.symlink_to(target.name)
        assert service.load(prepared, phone, now=_OBSERVED_AT) is None

    assert receipt.execution_authority == "none"


def test_recovery_live_target_rejects_same_model_different_physical_phone(
    tmp_path, monkeypatch
) -> None:
    service, prepared, phone, *_rest = _live_context(tmp_path, monkeypatch)
    substitute = replace(phone, serial="same-model-different-device")

    with pytest.raises(RecoveryLiveTargetValidationError, match="no longer matches"):
        service.observe(prepared, substitute)


def test_recovery_live_target_rejects_stale_scan_mode_and_naive_validation_time(
    tmp_path, monkeypatch
) -> None:
    service, prepared, phone, *_rest = _live_context(tmp_path, monkeypatch)
    receipt = service.observe(prepared, phone)

    with pytest.raises(RecoveryLiveTargetValidationError, match="exact prepared"):
        service.observe(prepared, replace(phone, state=DeviceState.DEVICE))
    with pytest.raises(RecoveryLiveTargetValidationError, match="timezone-aware"):
        service.validate(receipt, prepared, now=datetime(2026, 9, 5, 10, 1))


def test_recovery_live_target_service_has_no_consent_or_mutation_surface() -> None:
    names = set(dir(GuardianRecoveryLiveTargetReceiptService))
    forbidden = {
        "approve",
        "consent",
        "erase",
        "execute",
        "flash",
        "reboot",
        "relock",
        "restore",
        "set_active",
        "unlock",
        "wipe",
    }

    assert names.isdisjoint(forbidden)
    assert "subprocess" not in inspect.getsource(GuardianRecoveryLiveTargetReceiptService)


def test_guardian_recovery_card_checks_exact_phone_then_expires_without_consent(
    tmp_path, monkeypatch
) -> None:
    app = QApplication.instance() or QApplication([])
    service, prepared, phone, autopilot, _adb, _fastboot = _live_context(tmp_path, monkeypatch)
    service.clock = lambda: datetime.now(UTC)
    incident = autopilot.load(prepared.incident_id)
    route = next(item for item in incident.routes if item.route_id == prepared.route_id)
    queued = []
    monkeypatch.setattr("romverse.ui.guardian_center.start_background", queued.append)
    center = GuardianCenter(GuardianAuditStore(service.store.workspace), auto_start=False)
    try:
        assert center.open_recovery_review(incident, route, prepared, service, phone)
        assert center.recovery_focus_spacer.isVisibleTo(center)
        assert len(queued) == 1
        assert "CHECKING YOUR PHONE" in center.recovery_target_status.text()
        assert not center.recovery_target_button.isEnabled()
        queued.pop().run()
        app.processEvents()

        receipt = center.recovery_live_target_receipt
        assert receipt is not None
        assert receipt.preparation_digest == prepared.preparation_digest
        assert "EXACT PHONE VERIFIED" in center.recovery_target_status.text()
        assert receipt.receipt_digest not in center.recovery_target_status.text()
        assert not center.recovery_technical_detail.isVisibleTo(center)
        center.set_experience_mode(ExperienceMode.EXPERT)
        assert center.recovery_technical_detail.isVisibleTo(center)
        assert "EXACT PHONE CONFIRMED" in center.recovery_target_status.text()
        assert receipt.receipt_digest[:20] in center.recovery_target_status.text()
        assert "Recovery consent: locked" in center.recovery_target_status.text()
        assert "Execution: none" in center.recovery_target_status.text()
        assert "Phone changed: no" in center.recovery_target_status.text()
        center.set_experience_mode(ExperienceMode.GUIDED)
        assert not center.recovery_technical_detail.isVisibleTo(center)
        assert "EXACT PHONE VERIFIED" in center.recovery_target_status.text()
        assert center.recovery_target_button.text() == "Check exact phone again"
        assert center.recovery_target_button.isEnabled()

        center._recovery_target_expiry_timer.stop()
        center._expire_recovery_target_receipt()
        assert center.recovery_live_target_receipt is None
        assert "PHONE CHECK EXPIRED" in center.recovery_target_status.text()
        assert center.recovery_target_button.isEnabled()

        center.recovery_target_button.click()
        assert len(queued) == 1
        queued.pop().run()
        app.processEvents()
        assert center.recovery_live_target_receipt is not None
        assert not center.revalidate_recovery_live_target(
            prepared,
            replace(phone, state=DeviceState.DEVICE),
        )
        assert center.recovery_live_target_receipt is None
        assert "WAITING FOR THE PHONE IN THIS RECOVERY INCIDENT" in (
            center.recovery_target_status.text()
        )
        assert not center.recovery_target_button.isEnabled()

        assert center.revalidate_recovery_live_target(prepared, phone)
        assert len(queued) == 1
        assert "CHECKING YOUR PHONE" in center.recovery_target_status.text()
        queued.pop().run()
        app.processEvents()
        assert center.recovery_live_target_receipt is not None
    finally:
        center.close()


def test_guardian_recovery_card_fails_closed_and_offers_one_retry(tmp_path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    fastboot = _FastbootFixture(
        values={"product": "wrong-phone", "unlocked": "yes", "is-userspace": "no"}
    )
    service, prepared, phone, autopilot, _adb, _fastboot = _live_context(
        tmp_path,
        monkeypatch,
        fastboot=fastboot,
    )
    incident = autopilot.load(prepared.incident_id)
    route = next(item for item in incident.routes if item.route_id == prepared.route_id)
    queued = []
    monkeypatch.setattr("romverse.ui.guardian_center.start_background", queued.append)
    center = GuardianCenter(GuardianAuditStore(service.store.workspace), auto_start=False)
    try:
        assert center.open_recovery_review(incident, route, prepared, service, phone)
        assert len(queued) == 1
        queued.pop().run()
        app.processEvents()

        assert center.recovery_live_target_receipt is None
        assert "PHONE CHECK NEEDS ATTENTION" in center.recovery_target_status.text()
        assert "wrong-phone" not in center.recovery_target_status.text()
        assert "product" in center.recovery_technical_detail.text()
        assert center.recovery_target_button.text() == "Retry exact phone check"
        assert center.recovery_target_button.isEnabled()
        assert not prepared.runtime_invoked
        assert not prepared.phone_changed
    finally:
        center.close()


def test_guardian_recovery_card_discards_late_result_after_phone_disappears(
    tmp_path, monkeypatch
) -> None:
    app = QApplication.instance() or QApplication([])
    service, prepared, phone, autopilot, _adb, _fastboot = _live_context(tmp_path, monkeypatch)
    service.clock = lambda: datetime.now(UTC)
    incident = autopilot.load(prepared.incident_id)
    route = next(item for item in incident.routes if item.route_id == prepared.route_id)
    queued = []
    monkeypatch.setattr("romverse.ui.guardian_center.start_background", queued.append)
    center = GuardianCenter(GuardianAuditStore(service.store.workspace), auto_start=False)
    try:
        assert center.open_recovery_review(incident, route, prepared, service, phone)
        assert len(queued) == 1
        stale_worker = queued.pop()

        center.recovery_live_target_unavailable()
        stale_worker.run()
        app.processEvents()

        assert center.recovery_live_target_receipt is None
        assert "WAITING FOR THE PHONE IN THIS RECOVERY INCIDENT" in (
            center.recovery_target_status.text()
        )
        assert center.recovery_target_worker is None

        assert center.revalidate_recovery_live_target(prepared, phone)
        assert len(queued) == 1
        queued.pop().run()
        app.processEvents()
        assert center.recovery_live_target_receipt is not None
        assert "EXACT PHONE VERIFIED" in center.recovery_target_status.text()
    finally:
        center.close()


def test_guardian_recovery_card_explains_unavailable_tools_without_a_dead_end(
    tmp_path, monkeypatch
) -> None:
    QApplication.instance() or QApplication([])
    _service, prepared, phone, autopilot, _adb, _fastboot = _live_context(tmp_path, monkeypatch)
    incident = autopilot.load(prepared.incident_id)
    route = next(item for item in incident.routes if item.route_id == prepared.route_id)
    center = GuardianCenter(GuardianAuditStore(tmp_path), auto_start=False)
    toolchain_requests = []
    center.toolchain_requested.connect(lambda: toolchain_requests.append(True))
    try:
        assert center.open_recovery_review(incident, route, prepared)
        assert center.recovery_target_button.isVisibleTo(center)
        assert center.recovery_target_button.isEnabled()
        assert center.recovery_target_button.text() == "Open Forge Arsenal"
        assert "READ-ONLY PHONE CHECK NOT AVAILABLE" in center.recovery_target_status.text()
        assert "Verified ADB and Fastboot tools are required" in (
            center.recovery_target_status.text()
        )
        center.recovery_target_button.click()
        assert toolchain_requests == [True]
        assert center.recovery_live_target_receipt is None
        assert not phone.boot_completed
    finally:
        center.close()
