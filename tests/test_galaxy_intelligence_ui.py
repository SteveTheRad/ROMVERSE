from __future__ import annotations

import base64
import json
import os
from dataclasses import asdict
from datetime import UTC, datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from PySide6.QtWidgets import QApplication, QDialog

from romverse.device.models import AndroidDevice, DeviceState
from romverse.galaxy.intelligence import GalaxyIntelligenceService, GalaxyModerationKey
from romverse.galaxy.network import GalaxyNetworkService, GalaxyReceiptKey, GalaxyServiceTrust
from romverse.knowledge.updates import KnowledgePublisherKey
from romverse.members.client import MemberProfile, MemberSession
from romverse.ui.galaxy_center import GalaxyCenter
from romverse.ui.galaxy_intelligence import (
    GalaxyContributionPreviewDialog,
    GalaxyIntelligenceDialog,
    GalaxyNetworkPreviewDialog,
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


def _network_trust(private_key: Ed25519PrivateKey) -> GalaxyServiceTrust:
    public_key = base64.b64encode(
        private_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
    ).decode("ascii")
    return GalaxyServiceTrust(
        True,
        "Fixture trust.",
        "https://galaxy.example.test/v1",
        "https://members.example.test",
        (GalaxyReceiptKey("fixture-key", public_key),),
        (GalaxyModerationKey("fixture-key", public_key),),
        (KnowledgePublisherKey("fixture-key", public_key),),
    )


def _member_session() -> MemberSession:
    return MemberSession(
        "fixture-access-token-which-stays-in-memory",
        "Bearer",
        int(datetime.now(UTC).timestamp()) + 3600,
        MemberProfile("fixture-user", "Fixture user", "", "Fixture", "active"),
    )


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
    assert "PUBLIC GALAXY UNAVAILABLE" in dialog.network_state.text()
    assert dialog.preview_button.isEnabled()
    assert not dialog.constellation._timer.isActive()
    dialog.close()
    app.processEvents()


def test_galaxy_intelligence_compact_layout_preserves_readable_evidence_actions(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    dialog = GalaxyIntelligenceDialog(
        GalaxyIntelligenceService(workspace),
        reduced_motion=True,
    )
    dialog.resize(1040, 720)
    dialog.show()
    app.processEvents()

    assert not dialog.constellation.isVisible()
    assert dialog.detail.geometry().bottom() < dialog.network_button.geometry().top()
    assert dialog.network_state.isVisible()
    assert dialog.update_button.isVisible()

    dialog.resize(1220, 900)
    app.processEvents()
    assert dialog.constellation.isVisible()
    dialog.close()
    app.processEvents()


def test_galaxy_network_ui_shows_trusted_ready_state_and_exact_submission_action(
    tmp_path,
) -> None:
    app = QApplication.instance() or QApplication([])
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    intelligence = GalaxyIntelligenceService(workspace, sharing_enabled=True)
    preparation = GalaxyIntelligenceDialog(intelligence, (_device(),), reduced_motion=True)
    _fill(preparation)
    preview = preparation.build_preview()
    queued = intelligence.queue(preview, preview.preview_digest)
    preparation.close()
    trust = _network_trust(Ed25519PrivateKey.generate())
    network = GalaxyNetworkService(
        workspace,
        intelligence,
        trust,
        member_issuer="https://members.example.test",
    )
    dialog = GalaxyIntelligenceDialog(
        intelligence,
        (_device(),),
        network_service=network,
        member_session_provider=_member_session,
        reduced_motion=True,
    )

    assert "PUBLIC GALAXY READY" in dialog.network_state.text()
    assert dialog.network_button.isEnabled()
    assert dialog.network_button.text() == "Preview secure submission"
    assert "Galaxy S24 Ultra projection result" in dialog.detail.toPlainText()
    assert "Not submitted" in dialog.detail.toPlainText()
    network_preview = network.preview_submission(queued)
    submission = GalaxyNetworkPreviewDialog(
        network,
        network_preview,
        _member_session(),
    )
    assert not submission.submit_button.isEnabled()
    assert "VERY-PRIVATE-SERIAL" not in submission.payload.toPlainText()
    assert "fixture-access-token" not in submission.payload.toPlainText()
    submission.confirm.setChecked(True)
    assert submission.submit_button.isEnabled()
    submission.close()
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
    center.intelligence_dialog = dialog
    center._leave_for_members()
    assert routes == ["archives", "members"]

    center.set_contribution_opt_in(False)
    assert not center.intelligence.sharing_enabled
    center.set_reduced_motion(True)
    center.close()
    app.processEvents()
