from __future__ import annotations

import json
import os
from dataclasses import asdict

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog

from romverse.device.models import AndroidDevice, DeviceState
from romverse.galaxy.intelligence import GalaxyIntelligenceService
from romverse.ui.galaxy_center import GalaxyCenter
from romverse.ui.galaxy_intelligence import (
    GalaxyContributionPreviewDialog,
    GalaxyIntelligenceDialog,
)


def _device() -> AndroidDevice:
    return AndroidDevice(
        "VERY-PRIVATE-SERIAL",
        DeviceState.DEVICE,
        manufacturer="Samsung",
        brand="samsung",
        model="SM-S928B",
        marketing_name="Galaxy S24 Ultra",
        product="e3qxxx",
        codename="e3q",
        android_version="16",
        build_id="BP2A.FIXTURE",
        security_patch="2026-08-01",
        verified_boot="green",
        ab_update=True,
        virtual_ab=True,
        dynamic_partitions=True,
    )


def _fill(dialog: GalaxyIntelligenceDialog) -> None:
    dialog.title_input.setText("Galaxy S24 Ultra projection result")
    dialog.summary_input.setPlainText("The exact build completed the vehicle projection test.")
    dialog.symptoms_input.setPlainText("Projection previously stopped during handshake")
    dialog.steps_input.setPlainText("Re-test with the same cable and exact build")
    dialog.evidence_input.setPlainText("https://example.com/samsung/projection-result")
    dialog.pack_input.setText("samsung-e3q-fixture")


def test_galaxy_intelligence_ui_previews_device_dna_without_private_identity(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    service = GalaxyIntelligenceService(workspace)
    dialog = GalaxyIntelligenceDialog(service, (_device(),), reduced_motion=True)
    _fill(dialog)

    preview = dialog.build_preview()
    encoded = json.dumps(asdict(preview))

    assert "VERY-PRIVATE-SERIAL" not in encoded
    assert "SM-S928B" in encoded
    assert "serial excluded" in dialog.device_status.text()
    assert "OPTED OUT" in dialog.privacy_state.text()
    assert dialog.preview_button.isEnabled()
    assert not dialog.constellation._timer.isActive()
    dialog.close()
    app.processEvents()


def test_galaxy_preview_requires_review_and_queues_locally_without_upload(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    service = GalaxyIntelligenceService(workspace, sharing_enabled=True)
    chamber = GalaxyIntelligenceDialog(service, (_device(),), reduced_motion=True)
    _fill(chamber)
    preview = chamber.build_preview()
    dialog = GalaxyContributionPreviewDialog(service, preview)

    assert not dialog.queue_button.isEnabled()
    assert "NOT UPLOADED" in dialog.status.text()
    assert "VERY-PRIVATE-SERIAL" not in dialog.review.toPlainText()
    dialog.confirm.setChecked(True)
    assert dialog.queue_button.isEnabled()
    dialog.queue_button.click()
    app.processEvents()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.queued_contribution is not None
    assert not dialog.queued_contribution.uploaded
    assert dialog.queued_contribution.execution_authority == "none"
    chamber.refresh()
    assert chamber.contribution_list.count() == 1
    assert "EXPERIMENTAL" in chamber.contribution_list.item(0).text()
    dialog.close()
    chamber.close()


def test_galaxy_center_relays_settings_and_archive_routes_and_live_device(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = GalaxyCenter(tmp_path, contribution_opt_in=True, reduced_motion=True)
    center.set_devices([_device()])
    routes: list[str] = []
    settings: list[bool] = []
    center.route_requested.connect(routes.append)
    center.settings_requested.connect(lambda: settings.append(True))

    dialog = GalaxyIntelligenceDialog(center.intelligence, center._devices)
    center.intelligence_dialog = dialog
    center._leave_for_archives()
    assert routes == ["archives"]
    center.intelligence_dialog = dialog
    center._leave_for_settings()
    assert settings == [True]

    center.set_contribution_opt_in(False)
    assert not center.intelligence.sharing_enabled
    center.set_reduced_motion(True)
    center.close()
    app.processEvents()
