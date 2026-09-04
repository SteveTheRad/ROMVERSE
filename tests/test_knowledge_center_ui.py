from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from romverse.device.catalog import DeviceCatalogStatus
from romverse.diagnostics.analyzer import DiagnosticAnalyzer
from romverse.intelligence.synapse import (
    SynapseContribution,
    SynapseKnowledgeState,
    SynapseScope,
    SynapseStore,
)
from romverse.knowledge.resolution_memory import ArchivesResolutionMemory
from romverse.repair.knowledge import knowledge_for
from romverse.repair.sessions import RepairSessionStore
from romverse.repair.templates import RepairConcern
from romverse.ui.knowledge_center import (
    KnowledgeCenter,
    KnowledgeGuideDialog,
    SynapseLearningDialog,
)

from .test_diagnostics import device


def test_archives_search_selects_a_verified_guide_and_routes_to_rom_studio() -> None:
    app = QApplication.instance() or QApplication([])
    center = KnowledgeCenter()
    routes: list[str] = []
    center.route_requested.connect(routes.append)

    center.search.setText("firmware source")
    app.processEvents()
    assert "guide" in center.search_status.text().casefold()
    assert "payload.bin" in center.detail.toPlainText().casefold()
    assert center.open_route.isVisibleTo(center)
    center.open_route.click()
    assert routes == ["rom_studio"]
    center.close()


def test_archives_shows_verified_official_device_id_coverage() -> None:
    QApplication.instance() or QApplication([])

    class Catalog:
        @staticmethod
        def status() -> DeviceCatalogStatus:
            return DeviceCatalogStatus(
                True,
                True,
                "Official Google Play device IDs are current and integrity checked",
                53_623,
                "2026-09-03T10:18:26+00:00",
                "a" * 64,
            )

    center = KnowledgeCenter(device_catalog=Catalog())  # type: ignore[arg-type]

    assert "53,623 OFFICIAL ANDROID DEVICE ID ROWS" in center.device_catalog_status.text()
    assert "NOT BUILD OR FLASH AUTHORITY" in center.device_catalog_status.text()
    center.close()


def test_archives_never_leaves_stale_advice_when_search_has_no_match() -> None:
    app = QApplication.instance() or QApplication([])
    center = KnowledgeCenter()
    center.search.setText("definitely-not-a-real-romverse-topic")
    app.processEvents()

    assert "no verified guide matched" in center.search_status.text().casefold()
    assert "will not invent a fix" in center.detail.toPlainText().casefold()
    assert not center.open_route.isVisible()
    center.close()


def test_archives_accepts_a_bounded_contextual_query_from_guided_workflows() -> None:
    app = QApplication.instance() or QApplication([])
    center = KnowledgeCenter()
    center.show()

    center.open_query("  Incremental debloat safety  ")
    app.processEvents()

    assert center.search.text() == "Incremental debloat safety"
    assert "dependency failures" in center.detail.toPlainText()
    assert center.search.hasFocus()
    center.close()


def test_archives_opens_one_exact_typed_article_identity() -> None:
    app = QApplication.instance() or QApplication([])
    center = KnowledgeCenter()
    center.show()

    assert center.open_article("device-temperature-elevated")
    app.processEvents()

    assert center.list.count() == 1
    assert center.list.currentItem().data(Qt.ItemDataRole.UserRole) == "device-temperature-elevated"
    assert "temperature exceeds" in center.detail.toPlainText()
    assert "PIXEL-SCOPED" in center.detail.toPlainText()
    assert not center.open_article("not-a-real-article")
    assert center.list.count() == 0
    assert "could not be resolved" in center.detail.toPlainText()
    assert not center.open_route.isVisible()
    assert not center.open_source.isVisible()
    center.close()


def test_archives_returns_to_the_unchanged_source_workflow() -> None:
    app = QApplication.instance() or QApplication([])
    center = KnowledgeCenter()
    routes: list[str] = []
    center.route_requested.connect(routes.append)
    center.show()

    assert center.open_article("apk-version-downgrade", source_route="app_launchpad")
    app.processEvents()

    assert center.source_context.isVisibleTo(center)
    assert center.source_return.text() == "Return to App Launchpad"
    assert "starts no worker" in center.source_context_detail.text()
    center.source_return.click()
    assert routes == ["app_launchpad"]

    center.clear_source_context()
    assert not center.source_context.isVisible()
    center.close()


def test_archives_resolves_each_ascension_stage_to_one_authoritative_guide() -> None:
    app = QApplication.instance() or QApplication([])
    center = KnowledgeCenter()
    center.show()

    center.open_query("Ascension stage 4")
    app.processEvents()

    assert "1 verified guide found" in center.search_status.text()
    assert "Guardian review" in center.detail.toPlainText()
    assert "relocking is always prohibited" in center.detail.toPlainText()
    assert center.open_route.property("route") == "rom_studio"
    center.close()


def test_focused_recipe_guide_uses_the_authoritative_archives_article() -> None:
    QApplication.instance() or QApplication([])
    guide = KnowledgeGuideDialog(
        "Recipe Forger stage 3",
        "Stage 3 of 6  •  Target",
    )

    assert guide.match_count == 1
    assert guide.article_title == "Recipe Forger beginner journey"
    assert "protected firmware and connected phone can never be targets" in guide.article_body
    labels = "\n".join(label.text() for label in guide.findChildren(QLabel))
    assert "Guardian authority stays locked" in labels
    guide.close()


def test_archives_category_filter_and_source_evidence_stay_connected() -> None:
    app = QApplication.instance() or QApplication([])
    center = KnowledgeCenter()
    center.show()

    category_index = center.category.findData("APPS & PACKAGES")
    center.category.setCurrentIndex(category_index)
    center.search.setText("install_failed")
    app.processEvents()

    assert center.list.count() >= 7
    assert center.list.item(0).text() == "APK install error: INSTALL_FAILED_INVALID_APK"
    assert "KNOWN SAFE FIX" in center.detail.toPlainText()
    assert "AUTOMATION BOUNDARY" in center.detail.toPlainText()
    assert "AOSP SOURCE" in center.detail.toPlainText()
    assert center.open_source.isVisibleTo(center)
    assert center.open_source.property("source_url").startswith("https://android.googlesource.com/")
    assert center.open_route.property("route") == "app_launchpad"
    center.close()


def test_archives_labels_and_filters_official_maintainer_and_community_sources() -> None:
    app = QApplication.instance() or QApplication([])
    center = KnowledgeCenter()
    center.show()

    community_index = center.evidence_lane.findData("community")
    center.evidence_lane.setCurrentIndex(community_index)
    center.search.setText("community slot switch bootloop")
    app.processEvents()
    assert center.list.currentItem().data(Qt.ItemDataRole.UserRole) == (
        "community-slot-switch-bootloop-caution"
    )
    assert center.open_source.text() == "Open community report"
    assert center.open_source.accessibleName() == "Open community report"
    assert "COMMUNITY" in center.detail.toPlainText()

    center.search.setText("lineageos exact device install evidence")
    app.processEvents()
    assert center.open_source.text() == "Open maintainer source"

    official_index = center.evidence_lane.findData("official")
    center.evidence_lane.setCurrentIndex(official_index)
    center.search.setText("samsung smart switch emergency recovery")
    app.processEvents()
    assert center.list.count() == 1
    assert center.open_source.text() == "Open official source"
    assert "OFFICIAL SAMSUNG" in center.detail.toPlainText()

    center.evidence_lane.setCurrentIndex(community_index)
    app.processEvents()
    assert center.list.count() == 0
    assert "will not invent a fix" in center.detail.toPlainText().casefold()
    center.close()


def test_exact_archive_handoff_resets_a_previous_evidence_filter() -> None:
    app = QApplication.instance() or QApplication([])
    center = KnowledgeCenter()
    center.show()
    center.evidence_lane.setCurrentIndex(center.evidence_lane.findData("community"))

    assert center.open_article("samsung-smart-switch-update-recovery")
    app.processEvents()

    assert center.evidence_lane.currentData() == "all"
    assert center.list.currentItem().data(Qt.ItemDataRole.UserRole) == (
        "samsung-smart-switch-update-recovery"
    )
    center.close()


def test_archives_displays_integrity_verified_local_resolution_memory(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    analyzer = DiagnosticAnalyzer()
    store = RepairSessionStore(tmp_path)
    source = device(battery_percent=8)
    session = store.start(
        RepairConcern.BATTERY_HEAT,
        source,
        analyzer.analyze(source),
        knowledge_for(RepairConcern.BATTERY_HEAT).recommended_steps,
        ("device-battery-low",),
    )
    store.verify(
        session.session_id,
        source,
        analyzer.analyze(device(battery_percent=70)),
    )
    center = KnowledgeCenter(ArchivesResolutionMemory(store))
    center.show()

    assert center.open_article("device-battery-low")
    app.processEvents()

    assert center.resolution_status.isVisibleTo(center)
    assert "1 IMPROVED" in center.resolution_status.text()
    assert "CORRELATION, NOT CAUSATION" in center.resolution_status.text()
    assert "LOCAL RESOLUTION MEMORY" in center.detail.toPlainText()
    assert "does not prove" in center.detail.toPlainText()
    assert source.serial not in center.detail.toPlainText()
    center.close()


def test_archives_exposes_searchable_private_synapse_learning_and_retired_evidence(
    tmp_path,
) -> None:
    app = QApplication.instance() or QApplication([])
    store = SynapseStore(tmp_path)
    verified_scope = SynapseScope.create(
        operation="payload extraction",
        source_kind="payload-bin",
        device_codename="popsicle",
        build_family="os4-xpbcnxm",
        tool_name="payload-dumper-go",
        tool_version="2.0.2",
    )
    retired_scope = SynapseScope.create(operation="avb inspection", tool_name="avbtool")

    def contribute(
        scope: SynapseScope,
        source: str,
        *,
        successful: bool = True,
        drift: bool = False,
    ) -> None:
        store.contribute(
            SynapseContribution.create(
                fingerprint_id="a" * 64,
                solution_id="inspect-payload-source",
                scope=scope,
                source_family=source,
                summary="Verified without retaining /home/private/project or token=secret.",
                successful=successful,
                locally_verified=True,
                action_receipt_digest="b" * 64,
                verification_evidence_digest="c" * 64,
                version_drift=drift,
            )
        )

    contribute(verified_scope, "official-aosp")
    contribute(verified_scope, "maintainer-tool")
    contribute(verified_scope, "official-aosp")
    contribute(retired_scope, "official-aosp", successful=False, drift=True)
    center = KnowledgeCenter(synapse_store=store)
    center.show()
    app.processEvents()

    assert len(center.synapse_knowledge) == 2
    assert center.synapse_knowledge[0].state is SynapseKnowledgeState.TRUSTED
    assert center.synapse_knowledge[1].state is SynapseKnowledgeState.RETIRED
    assert "2 LOCAL KNOWLEDGE RECORD(S)" in center.learning_status.text()
    assert "1 TRUSTED" in center.learning_status.text()
    assert "1 RETIRED" in center.learning_status.text()
    assert center.learning_panel.property("learningState") == "attention"

    center.learning_button.click()
    app.processEvents()
    dialog = center.learning_dialog
    assert isinstance(dialog, SynapseLearningDialog)
    assert dialog.isVisible()
    assert dialog.list.count() == 2
    assert "payload extraction" in dialog.detail.toPlainText().casefold()
    assert "guidance-only" in dialog.detail.toPlainText().casefold()
    assert "private" not in dialog.detail.toPlainText().casefold()
    dialog.search.setText("avbtool")
    app.processEvents()
    assert dialog.list.count() == 1
    assert "RETIRED" in dialog.detail.toPlainText()
    assert "failed or drifted" in dialog.detail.toPlainText()
    dialog.close()
    center.close()


def test_archives_rejects_modified_synapse_memory_and_opens_its_exact_safety_guide(
    tmp_path,
) -> None:
    app = QApplication.instance() or QApplication([])
    store = SynapseStore(tmp_path)
    scope = SynapseScope.create(operation="source inspection")
    store.contribute(
        SynapseContribution.create(
            fingerprint_id="a" * 64,
            solution_id="inspect-source",
            scope=scope,
            source_family="official-aosp",
            summary="Verified source inspection.",
            successful=True,
            locally_verified=True,
            action_receipt_digest="b" * 64,
            verification_evidence_digest="c" * 64,
        )
    )
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    payload["contributions"][0]["summary"] = "modified"
    store.path.write_text(json.dumps(payload), encoding="utf-8")

    center = KnowledgeCenter(synapse_store=store)
    center.show()
    app.processEvents()

    assert center.synapse_knowledge == ()
    assert "LOCAL LEARNING UNAVAILABLE" in center.learning_status.text()
    assert center.learning_panel.property("learningState") == "unavailable"
    center.learning_button.click()
    app.processEvents()
    assert center.list.currentItem().data(Qt.ItemDataRole.UserRole) == (
        "archives-local-learning-boundary"
    )
    assert "cannot become learned knowledge" in center.detail.toPlainText()
    center.close()
