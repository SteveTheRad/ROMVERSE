import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
import zipfile
from time import monotonic

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

from romverse.applications.receipts import ApkReceiptStore
from romverse.backup.plans import GuardianBackupPlanStore
from romverse.device.apk_install import ApkInstallRequest, create_install_plan
from romverse.device.models import AndroidDevice, DeviceState
from romverse.guardian.approval import ApprovalStore
from romverse.guardian.audit import GuardianAuditStore
from romverse.guardian.manifest_review import GuardianManifestReviewService
from romverse.infrastructure.process import CommandResult
from romverse.nexus.planning import NexusObjective, NexusPlanner
from romverse.ui.guardian_center import GuardianCenter
from romverse.ui.theme import STYLESHEET
from tests.test_guardian_manifest_review import _prepared as _prepared_manifest
from tests.test_nexus_planning import _evidence


def _device() -> AndroidDevice:
    return AndroidDevice(
        "private-serial",
        DeviceState.DEVICE,
        manufacturer="Google",
        model="Test Phone",
        verified_boot="green",
    )


def _wait_for_guardian(center: GuardianCenter, app: QApplication) -> None:
    deadline = monotonic() + 5
    while center.worker is not None and monotonic() < deadline:
        QThreadPool.globalInstance().waitForDone(20)
        app.processEvents()
    assert center.worker is None


def test_guardian_displays_verified_plan_digest_and_rejects_later_tampering(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    store = GuardianBackupPlanStore(tmp_path)
    record = store.create(_device())
    center = GuardianCenter(GuardianAuditStore(tmp_path))
    _wait_for_guardian(center, app)

    assert record.plan_digest[:16] in center.integrity_detail.text()

    data = json.loads(store.latest_path.read_text(encoding="utf-8"))
    data["phone_data_copied"] = True
    store.latest_path.write_text(json.dumps(data), encoding="utf-8")
    center.refresh()
    _wait_for_guardian(center, app)

    assert "plan rejected" in center.integrity_detail.text().casefold()
    assert "integrity mismatch" in center.integrity_detail.text().casefold()
    center.close()


def test_guardian_verifies_apk_preflight_and_install_receipts(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    apk = tmp_path / "guardian-review.apk"
    with zipfile.ZipFile(apk, "w") as archive:
        archive.writestr("AndroidManifest.xml", b"manifest")
        archive.writestr("classes.dex", b"dex\n035\0")
    plan = create_install_plan(
        ApkInstallRequest(
            str(apk),
            "PRIVATE-SERIAL",
            battery_percent=90,
            device_free_bytes=1024**3,
        ),
        "private-device-key",
    )
    receipts = ApkReceiptStore(tmp_path)
    preflight = receipts.write_preflight(plan)
    install = receipts.write_install(
        plan,
        CommandResult(("adb",), 0, "Success\nPRIVATE OUTPUT", ""),
        True,
    )

    center = GuardianCenter(GuardianAuditStore(tmp_path))
    _wait_for_guardian(center, app)
    detail = center.integrity_detail.text()
    assert preflight.receipt_digest[:16] in detail
    assert install.receipt_digest[:16] in detail
    assert "latest apk install result: success" in detail.casefold()
    assert "PRIVATE" not in detail

    data = json.loads(receipts.latest_install_path.read_text(encoding="utf-8"))
    data["success"] = False
    receipts.latest_install_path.write_text(json.dumps(data), encoding="utf-8")
    center.refresh()
    _wait_for_guardian(center, app)
    assert "apk install receipt rejected" in center.integrity_detail.text().casefold()
    assert "integrity mismatch" in center.integrity_detail.text().casefold()
    center.close()


def test_guardian_displays_active_approval_chain_and_rejects_tampering(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    approvals = ApprovalStore(tmp_path)
    approvals.issue("exact-plan", "private-device-key")
    center = GuardianCenter(GuardianAuditStore(tmp_path))
    _wait_for_guardian(center, app)

    assert "1 active / 1 recorded" in center.integrity_detail.text()
    assert center.integrity_badge.text() == "INTEGRITY VERIFIED"

    data = json.loads(approvals.path.read_text(encoding="utf-8"))
    data["target"] = "another-device"
    approvals.path.write_text(json.dumps(data) + "\n", encoding="utf-8")
    center.refresh()
    _wait_for_guardian(center, app)

    assert center.integrity_badge.text() == "APPROVAL INTEGRITY FAILURE"
    assert "No stored approval can authorize" in center.integrity_detail.text()
    center.close()


def test_guardian_verification_is_backgrounded_and_duplicate_locked(
    tmp_path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    started: list[object] = []
    monkeypatch.setattr("romverse.ui.guardian_center.start_background", started.append)

    center = GuardianCenter(GuardianAuditStore(tmp_path))

    assert len(started) == 1
    assert center.worker is started[0]
    assert not center.refresh_button.isEnabled()
    assert center.progress.minimum() == 0
    assert center.progress.maximum() == 0
    assert "background" in center.integrity_detail.text().casefold()
    center.refresh()
    assert len(started) == 1

    started[0].execute()
    app.processEvents()
    assert center.worker is None
    assert center.refresh_button.isEnabled()
    assert center.integrity_badge.text() == "INTEGRITY VERIFIED"
    center.close()


def test_guardian_dashboard_state_never_claims_verified_before_or_after_stale_evidence(
    tmp_path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    started: list[object] = []
    states: list[tuple[str, str, bool]] = []
    monkeypatch.setattr("romverse.ui.guardian_center.start_background", started.append)
    audit = GuardianAuditStore(tmp_path)
    center = GuardianCenter(audit, auto_start=False)
    center.dashboard_state_changed.connect(
        lambda state, detail, verified: states.append((state, detail, verified))
    )

    assert center.current_dashboard_state()[0] == "unverified"
    assert center.open_dashboard_intent("Guardian")
    assert not center.dashboard_handoff.isHidden()
    assert center.dashboard_handoff_badge.text() == "VERIFY REQUIRED"
    assert not center.open_dashboard_intent("Unknown workflow")

    center.refresh()
    assert center.current_dashboard_state()[0] == "verifying"
    assert center.dashboard_handoff_badge.text() == "VERIFYING"
    assert len(started) == 1

    started[0].execute()
    app.processEvents()

    assert center.current_dashboard_state()[0] == "verified"
    assert center.current_dashboard_state()[2] is True
    assert center.dashboard_handoff_badge.text() == "INTEGRITY VERIFIED"
    assert "0 operation records" in center.dashboard_handoff_detail.text()

    audit.path.parent.mkdir(parents=True, exist_ok=True)
    audit.path.write_text("tampered after verification\n", encoding="utf-8")
    assert center.invalidate_dashboard_if_evidence_changed()

    assert center.current_dashboard_state()[0] == "review_due"
    assert center.current_dashboard_state()[2] is False
    assert center.dashboard_handoff_badge.text() == "REVERIFY REQUIRED"
    assert [state for state, _detail, _verified in states] == [
        "verifying",
        "verified",
        "review_due",
    ]
    center.close()


def test_hidden_guardian_defers_automatic_refresh_until_it_is_viewed(
    tmp_path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    started: list[object] = []
    monkeypatch.setattr("romverse.ui.guardian_center.start_background", started.append)
    center = GuardianCenter(GuardianAuditStore(tmp_path), auto_start=False)

    center.request_refresh()
    app.processEvents()

    assert center.worker is None
    assert started == []
    assert center._refresh_pending

    center.show()
    center._refresh_timer.setInterval(0)
    center.request_refresh()
    app.processEvents()

    assert len(started) == 1
    assert center.worker is started[0]
    center.worker = None
    center.close()


def test_guardian_presents_nexus_plan_as_zero_authority_review_context(tmp_path) -> None:
    QApplication.instance() or QApplication([])
    store, profile, matrix = _evidence(tmp_path)
    plan = NexusPlanner(store).plan(profile, matrix, NexusObjective.BUILD_ROM)
    center = GuardianCenter(GuardianAuditStore(tmp_path), auto_start=False)
    returned: list[tuple[str, str]] = []
    center.nexus_requested.connect(
        lambda project_id, digest: returned.append((project_id, digest))
    )

    assert center.open_nexus_review(plan, "Device DNA")
    assert not center.nexus_review.isHidden()
    assert center.nexus_review_title.text() == "Build a ROM  •  Device DNA"
    detail = center.nexus_review_detail.text()
    assert plan.plan_digest[:16] in detail
    assert plan.mission_id[:12] in detail
    assert "Approval: none" in detail
    assert "Execution: none" in detail
    assert "Bootloader relock: never" in detail
    assert all(requirement in detail for requirement in plan.guardian_requirements)
    assert center.nexus_review_badge.text() == "ZERO AUTHORITY"
    center.nexus_return_button.click()
    assert returned == [(plan.project_id, plan.plan_digest)]
    center.close()


def test_guardian_presents_recovery_plan_as_zero_authority_evidence(tmp_path) -> None:
    QApplication.instance() or QApplication([])
    store = GuardianBackupPlanStore(tmp_path)
    record = store.create(_device())
    loaded = store.load_latest()
    center = GuardianCenter(GuardianAuditStore(tmp_path), auto_start=False)
    returned: list[tuple[str, str]] = []
    center.time_machine_requested.connect(
        lambda plan_id, digest: returned.append((plan_id, digest))
    )

    assert center.open_backup_review(loaded)
    assert not center.backup_review.isHidden()
    assert center.nexus_review.isHidden()
    assert center.backup_review_identity == (record.plan_id, record.plan_digest)
    assert center.backup_review_badge.text() == "ZERO AUTHORITY"
    assert "Test Phone" in center.backup_review_title.text()
    detail = center.backup_review_detail.text()
    assert record.plan_id in detail
    assert record.plan_digest[:16] in detail
    assert "ADB authorized: yes" in detail
    assert "Verified Boot: green" in detail
    assert "Phone data copied: no" in detail
    assert "Approval: none" in detail
    assert "Execution: none" in detail
    center.backup_return_button.click()
    assert returned == [(record.plan_id, record.plan_digest)]
    center.close()


def test_guardian_presents_exact_studio_manifest_and_returns_its_identity(tmp_path) -> None:
    QApplication.instance() or QApplication([])
    store, project, registry, report, device = _prepared_manifest(tmp_path)
    manifest = GuardianManifestReviewService(store, registry).compile(
        project.project_id,
        report,
        device,
    )
    center = GuardianCenter(GuardianAuditStore(store.workspace), auto_start=False)
    returned: list[tuple[str, str]] = []
    center.rom_studio_requested.connect(
        lambda project_id, digest: returned.append((project_id, digest))
    )

    assert center.open_studio_review(manifest, project.name)
    assert not center.studio_review.isHidden()
    assert center.studio_review.objectName() == "StudioReviewCard"
    assert "QFrame#StudioReviewCard" in STYLESHEET
    assert center.nexus_review.isHidden()
    assert center.backup_review.isHidden()
    assert center.studio_review_identity == (
        project.project_id,
        manifest.manifest_digest,
    )
    detail = center.studio_review_detail.text()
    assert manifest.manifest_digest[:16] in detail
    assert manifest.handoff_digest[:16] in detail
    assert manifest.source_sha256[:16] in detail
    assert "Execution: none" in detail
    assert "Final consent: locked" in detail
    assert "Bootloader relock: never" in detail
    assert "Phone changed: no" in detail

    center.studio_return_button.click()
    assert returned == [(project.project_id, manifest.manifest_digest)]
    center.close()
