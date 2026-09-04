from __future__ import annotations

import html
import shutil
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from romverse.device.catalog import (
    DeviceCatalogEntry,
    DeviceCatalogMatch,
    DeviceCatalogStatus,
    GooglePlayDeviceCatalog,
)
from romverse.device.dna import DeviceDnaProfile, EvidenceConfidence
from romverse.device.intelligence import (
    DeviceIntelligenceError,
    DeviceIntelligenceHistoryStore,
)
from romverse.device.models import AndroidDevice
from romverse.device_packs.attestations import DevicePackAttestationStore
from romverse.device_packs.drafts import DevicePackDraftReview, DevicePackDraftService
from romverse.device_packs.foundry import (
    DevicePackFoundryInventory,
    DevicePackFoundryService,
    FoundryDraftRevision,
    FoundryEvidenceState,
)
from romverse.device_packs.models import CapabilityStatus, DevicePack
from romverse.device_packs.registry import DevicePackRegistry
from romverse.device_packs.requirements import (
    DeviceRequirementsBlueprint,
    DeviceRequirementsService,
    ProjectSourceRequirements,
    RequirementState,
)
from romverse.device_packs.source_audit import export_source_audit, summarize_sources
from romverse.device_packs.validation import (
    DevicePackNextAction,
    DevicePackValidationReport,
    DevicePackValidationService,
    ValidationState,
)
from romverse.guardian.execution_result_receipt import VerifiedGuardianExecutionResult
from romverse.infrastructure.process import SubprocessRunner
from romverse.infrastructure.provisioning import required_tools_for_source
from romverse.infrastructure.tools import ToolStatus
from romverse.knowledge.models import KnowledgeLookupReport
from romverse.repair.sessions import RepairSessionStore
from romverse.rom.avb_evidence import SourceAvbEvidenceService, SourceAvbTopologyReceipt
from romverse.rom.models import ProjectError
from romverse.rom.payloads import PayloadService
from romverse.rom.projects import RomProjectStore
from romverse.rom.source_intelligence import FirmwareSourceIntelligenceService
from romverse.ui.formatters import human_bytes
from romverse.ui.process_progress import ProcessProgressBar


class DevicePacksCenter(QWidget):
    rom_studio_requested = Signal(str, str)
    catalog_refresh_requested = Signal()
    knowledge_article_requested = Signal(str)
    next_action_requested = Signal(str, str, str, str)
    requirement_requested = Signal(str, str, str, str)
    readiness_changed = Signal(object)
    knowledge_query_requested = Signal(str)

    def __init__(
        self,
        registry: DevicePackRegistry,
        workspace: Path | None = None,
        attestation_store: DevicePackAttestationStore | None = None,
        device_catalog: GooglePlayDeviceCatalog | None = None,
        online_catalog_enabled: bool = True,
        tool_statuses: tuple[ToolStatus, ...] | None = None,
    ) -> None:
        super().__init__()
        self.registry = registry
        self.workspace = workspace
        self.attestation_store = attestation_store
        self.device_catalog = device_catalog
        self.online_catalog_enabled = online_catalog_enabled
        self.tool_statuses = tool_statuses
        self.validation_service = DevicePackValidationService()
        self.requirements_service = DeviceRequirementsService()
        self.draft_service = DevicePackDraftService()
        self.foundry_service = DevicePackFoundryService()
        self.active_report: DevicePackValidationReport | None = None
        self.active_next_action: DevicePackNextAction | None = None
        self.active_requirements: DeviceRequirementsBlueprint | None = None
        self.active_project_source: ProjectSourceRequirements | None = None
        self.active_project_draft: DevicePackDraftReview | None = None
        self.active_foundry_revision: FoundryDraftRevision | None = None
        self.foundry_inventory: DevicePackFoundryInventory | None = None
        self.active_catalog_match: DeviceCatalogMatch | None = None
        self.active_pack: DevicePack | None = None
        self.active_device: AndroidDevice | None = None
        self.active_device_dna: DeviceDnaProfile | None = None
        self.active_knowledge_report: KnowledgeLookupReport | None = None
        self.active_knowledge_device_serial = ""
        self.knowledge_lookup_error = ""
        self.intelligence_history = (
            DeviceIntelligenceHistoryStore(workspace) if workspace is not None else None
        )
        self.repair_history = RepairSessionStore(workspace) if workspace is not None else None
        self.intelligence_history_error = ""
        self._timeline_rows: tuple[tuple[str, str, str, str, str], ...] = ()
        self._timeline_dialog: QDialog | None = None
        self.validation_rows: dict[str, QFrame] = {}
        self.requirement_buttons: dict[str, QPushButton] = {}
        self.requirement_badges: dict[str, QLabel] = {}
        self.official_result_buttons: list[QPushButton] = []
        self.official_missing_pack_guide_button: QPushButton | None = None
        self.devices: list[AndroidDevice] = []
        self.source_summary = summarize_sources(registry)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.body = QScrollArea()
        self.body.setObjectName("DeviceAtlasScroll")
        self.body.setWidgetResizable(True)
        self.body_content = QWidget()
        self.body_content.setObjectName("ScrollContent")
        page = QVBoxLayout(self.body_content)
        page.setContentsMargins(30, 26, 30, 30)
        page.setSpacing(18)
        self.body.setWidget(self.body_content)
        root.addWidget(self.body)
        header = QHBoxLayout()
        text = QVBoxLayout()
        eyebrow = QLabel("DEVICE ATLAS  •  MULTI-OEM BY DESIGN")
        eyebrow.setObjectName("Eyebrow")
        title = QLabel("Device Atlas")
        title.setObjectName("Title")
        subtitle = QLabel(
            "Versioned OEM knowledge extends compatibility metadata without granting execution authority."
        )
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        text.addWidget(eyebrow)
        text.addWidget(title)
        text.addWidget(subtitle)
        header.addLayout(text, 1)
        self.selector = QComboBox()
        self.selector.setMinimumWidth(240)
        self.selector.setVisible(False)
        self.selector.currentIndexChanged.connect(self._select)
        header.addWidget(self.selector)
        self.audit_button = QPushButton("Export source audit")
        self.audit_button.setEnabled(workspace is not None)
        self.audit_button.setToolTip(
            "Exports a privacy-safe, tamper-evident inventory of Pack hashes, official sources, "
            "and review status. It contains no device identifiers and grants no execution authority."
        )
        self.audit_button.clicked.connect(self._export_source_audit)
        header.addWidget(self.audit_button)
        page.addLayout(header)

        page.addWidget(self._device_passport())

        catalog_row = QHBoxLayout()
        self.catalog_search = QLineEdit()
        self.catalog_search.setClearButtonEnabled(True)
        self.catalog_search.setPlaceholderText(
            "Search Packs and official Android IDs by brand, retail name, model, or codename…"
        )
        self.catalog_search.setToolTip(
            "Searches ROMVERSE's integrity-checked Pack catalog and its verified local mirror "
            "of Google's public Android device IDs. It performs no network request and grants "
            "no build, flash, or device authority."
        )
        self.catalog_search.textChanged.connect(self._catalog_query_changed)
        catalog_row.addWidget(self.catalog_search, 1)
        self.catalog_button = QPushButton("Browse all Packs")
        self.catalog_button.setToolTip(
            "Show every integrity-checked Device Pack and review its declared evidence."
        )
        self.catalog_button.clicked.connect(self._show_installed)
        catalog_row.addWidget(self.catalog_button)
        page.addLayout(catalog_row)

        self.dashboard_handoff = QFrame()
        self.dashboard_handoff.setObjectName("DiagnosticHandoffBar")
        self.dashboard_handoff.setMinimumHeight(118)
        dashboard_handoff_layout = QHBoxLayout(self.dashboard_handoff)
        dashboard_handoff_layout.setContentsMargins(18, 13, 18, 13)
        dashboard_handoff_layout.setSpacing(14)
        dashboard_handoff_copy = QVBoxLayout()
        self.dashboard_handoff_eyebrow = QLabel(
            "COMMAND DECK HANDOFF  •  CURRENT DEVICE DNA EVIDENCE"
        )
        self.dashboard_handoff_eyebrow.setObjectName("Eyebrow")
        self.dashboard_handoff_title = QLabel()
        self.dashboard_handoff_title.setObjectName("SectionTitle")
        self.dashboard_handoff_detail = QLabel()
        self.dashboard_handoff_detail.setObjectName("Muted")
        self.dashboard_handoff_detail.setWordWrap(True)
        self.dashboard_handoff_detail.setMinimumHeight(20)
        self.dashboard_handoff_detail.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        dashboard_handoff_copy.addWidget(self.dashboard_handoff_eyebrow)
        dashboard_handoff_copy.addWidget(self.dashboard_handoff_title)
        dashboard_handoff_copy.addWidget(self.dashboard_handoff_detail)
        dashboard_handoff_layout.addLayout(dashboard_handoff_copy, 1)
        self.dashboard_handoff_badge = QLabel()
        dashboard_handoff_layout.addWidget(self.dashboard_handoff_badge)
        self.dashboard_handoff.setVisible(False)
        page.addWidget(self.dashboard_handoff)

        self.identity_catalog = QFrame()
        self.identity_catalog.setObjectName("DiagnosticHandoffBar")
        identity_layout = QHBoxLayout(self.identity_catalog)
        identity_layout.setContentsMargins(20, 14, 20, 14)
        identity_copy = QVBoxLayout()
        self.identity_catalog_title = QLabel("Official Android device IDs")
        self.identity_catalog_title.setObjectName("SectionTitle")
        self.identity_catalog_detail = QLabel()
        self.identity_catalog_detail.setObjectName("Muted")
        self.identity_catalog_detail.setWordWrap(True)
        identity_copy.addWidget(self.identity_catalog_title)
        identity_copy.addWidget(self.identity_catalog_detail)
        identity_layout.addLayout(identity_copy, 1)
        self.identity_catalog_badge = QLabel()
        identity_layout.addWidget(self.identity_catalog_badge)
        self.identity_catalog_button = QPushButton("Sync official IDs")
        self.identity_catalog_button.setToolTip(
            "Downloads Google's public supported-device catalog in the background. It can label "
            "an exact Build.BRAND + Build.DEVICE pair, but cannot enable building, flashing, or "
            "any phone action."
        )
        self.identity_catalog_button.clicked.connect(self.catalog_refresh_requested)
        identity_layout.addWidget(self.identity_catalog_button)
        page.addWidget(self.identity_catalog)

        self.hero = QFrame()
        self.hero.setObjectName("HeroCard")
        hero_layout = QHBoxLayout(self.hero)
        hero_layout.setContentsMargins(24, 20, 24, 20)
        state = QVBoxLayout()
        self.pack_name = QLabel("Waiting for Device Engine…")
        self.pack_name.setObjectName("HeroTitle")
        self.match_reason = QLabel(
            f"{len(registry.packs)} integrity-checked built-in packs are available."
        )
        self.match_reason.setObjectName("Muted")
        self.match_reason.setWordWrap(True)
        state.addWidget(self.pack_name)
        state.addWidget(self.match_reason)
        hero_layout.addLayout(state, 1)
        self.pack_badge = QLabel("NO DEVICE")
        self.pack_badge.setObjectName("Warning")
        hero_layout.addWidget(self.pack_badge)
        page.addWidget(self.hero)

        self.guidance = QFrame()
        self.guidance.setObjectName("Card")
        guidance_layout = QHBoxLayout(self.guidance)
        guidance_layout.setContentsMargins(20, 16, 20, 16)
        guidance_copy = QVBoxLayout()
        self.guidance_title = QLabel("Connect a phone and ROMVERSE will identify its support level")
        self.guidance_title.setObjectName("SectionTitle")
        self.guidance_detail = QLabel(
            "Device Atlas checks the model, codename, firmware knowledge, and verified build "
            "contract. It will not guess or unlock device-changing work from a generic match."
        )
        self.guidance_detail.setObjectName("Muted")
        self.guidance_detail.setWordWrap(True)
        guidance_copy.addWidget(self.guidance_title)
        guidance_copy.addWidget(self.guidance_detail)
        guidance_layout.addLayout(guidance_copy, 1)
        self.continue_button = QPushButton("Start ROM Mission")
        self.continue_button.setObjectName("Primary")
        self.continue_button.setVisible(False)
        self.continue_button.setToolTip(
            "Send the current verified device evidence to ROM Studio and begin or resume Genesis. "
            "This does not build, flash, wipe, unlock, relock, or change the phone."
        )
        self.continue_button.clicked.connect(self._request_rom_studio)
        guidance_layout.addWidget(self.continue_button)
        page.addWidget(self.guidance)

        metrics = QHBoxLayout()
        self.installed_card, self.installed_value = self._metric(
            "VALID PACKS", str(len(registry.packs))
        )
        self.issue_card, self.issue_value = self._metric("LOAD ISSUES", str(len(registry.issues)))
        self.version_card, self.version_value = self._metric("ACTIVE VERSION", "—")
        source_health = (
            f"{self.source_summary.current_source_count} current"
            if self.source_summary.review_due_count == 0
            else f"{self.source_summary.review_due_count} review due"
        )
        self.source_card, self.source_value = self._metric("SOURCE HEALTH", source_health)
        self.source_value.setObjectName(
            "HeroTitle" if self.source_summary.review_due_count == 0 else "Warning"
        )
        metrics.addWidget(self.installed_card, 1)
        metrics.addWidget(self.issue_card, 1)
        metrics.addWidget(self.version_card, 1)
        metrics.addWidget(self.source_card, 1)
        page.addLayout(metrics)

        self.results_content = QWidget()
        self.results_content.setObjectName("ScrollContent")
        self.body_layout = QVBoxLayout(self.results_content)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(12)
        page.addWidget(self.results_content)

        boundary = QLabel(
            "Pack integrity is verified against the bundled SHA-256 index. Imported physical-test "
            "evidence additionally requires an unrevoked release key from ROMVERSE's integrity-checked "
            "publisher catalog and is reverified whenever used. Packs and evidence cannot bypass Guardian."
        )
        boundary.setObjectName("Muted")
        boundary.setWordWrap(True)
        page.addWidget(boundary)
        self.set_catalog_status(
            device_catalog.status()
            if device_catalog is not None
            else DeviceCatalogStatus(False, False, "Official device catalog is unavailable")
        )
        self._show_installed()

    def _device_passport(self) -> QFrame:
        passport = QFrame()
        passport.setObjectName("DevicePassport")
        passport.setAccessibleName("Live Device Intelligence passport")
        passport.setMinimumHeight(310)
        outer = QHBoxLayout(passport)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.setSpacing(18)

        hologram = QLabel("◇\nDNA")
        hologram.setObjectName("DevicePassportHologram")
        hologram.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hologram.setFixedSize(88, 118)
        hologram.setAccessibleName("Holographic device DNA emblem")
        outer.addWidget(hologram, 0, Qt.AlignmentFlag.AlignTop)

        content = QVBoxLayout()
        content.setSpacing(7)
        title_row = QHBoxLayout()
        heading = QLabel("DEVICE INTELLIGENCE HUB  •  LIVE PASSPORT")
        heading.setObjectName("DevicePassportEyebrow")
        title_row.addWidget(heading)
        title_row.addStretch()
        self.passport_state = QLabel("AWAITING DEVICE")
        self.passport_state.setObjectName("Warning")
        title_row.addWidget(self.passport_state)
        content.addLayout(title_row)
        self.passport_name = QLabel("Connect an Android phone to unfold its Device DNA")
        self.passport_name.setObjectName("DevicePassportTitle")
        self.passport_name.setWordWrap(True)
        content.addWidget(self.passport_name)
        self.passport_scan_progress = ProcessProgressBar()
        self.passport_scan_progress.setAccessibleName("Animated Device DNA scan progress")
        content.addWidget(self.passport_scan_progress)

        facts = QGridLayout()
        facts.setHorizontalSpacing(16)
        facts.setVerticalSpacing(8)
        self.passport_identity = self._passport_fact(facts, 0, 0, "IDENTITY")
        self.passport_platform = self._passport_fact(facts, 0, 1, "CHIPSET / REGION")
        self.passport_firmware = self._passport_fact(facts, 0, 2, "ANDROID / FIRMWARE")
        self.passport_boot = self._passport_fact(facts, 1, 0, "BOOT / SLOTS")
        self.passport_partitions = self._passport_fact(facts, 1, 1, "PARTITIONS")
        self.passport_health = self._passport_fact(facts, 1, 2, "LIVE HEALTH")
        self.passport_upgrade = self._passport_fact(facts, 2, 0, "UPGRADE VERDICT")
        self.passport_knowledge = self._passport_fact(facts, 2, 1, "MATCHED KNOWLEDGE")
        self.passport_history = self._passport_fact(facts, 2, 2, "LOCAL TIMELINE")
        content.addLayout(facts)
        outer.addLayout(content, 1)

        actions = QVBoxLayout()
        actions.setSpacing(8)
        self.passport_refresh_note = QLabel("READ-ONLY • PRIVATE • OFFLINE-FIRST")
        self.passport_refresh_note.setObjectName("DevicePassportBoundary")
        self.passport_refresh_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        actions.addWidget(self.passport_refresh_note)
        self.passport_knowledge_button = QPushButton("Review best knowledge match")
        self.passport_knowledge_button.setObjectName("KnowledgeBrainAction")
        self.passport_knowledge_button.setVisible(False)
        self.passport_knowledge_button.setToolTip(
            "Open the best current offline Archives match. No command or phone action is started."
        )
        self.passport_knowledge_button.clicked.connect(self._request_passport_knowledge)
        actions.addWidget(self.passport_knowledge_button)
        self.passport_timeline_button = QPushButton("Open private timeline")
        self.passport_timeline_button.setObjectName("KnowledgeBrainAction")
        self.passport_timeline_button.setVisible(False)
        self.passport_timeline_button.setToolTip(
            "Review integrity-checked scans, verified Guardian flashes, and repair sessions "
            "for this pseudonymous device. Nothing is uploaded or executed."
        )
        self.passport_timeline_button.clicked.connect(self._open_private_timeline)
        actions.addWidget(self.passport_timeline_button)
        actions.addStretch()
        outer.addLayout(actions)
        return passport

    @staticmethod
    def _passport_fact(
        grid: QGridLayout,
        row: int,
        column: int,
        title: str,
    ) -> QLabel:
        card = QFrame()
        card.setObjectName("DevicePassportFact")
        card.setMinimumHeight(70)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(11, 8, 11, 8)
        layout.setSpacing(2)
        label = QLabel(title)
        label.setObjectName("DevicePassportFactLabel")
        value = QLabel("Unconfirmed")
        value.setObjectName("DevicePassportFactValue")
        value.setWordWrap(True)
        value.setMinimumHeight(34)
        value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(label)
        layout.addWidget(value)
        grid.addWidget(card, row, column)
        return value

    def set_scanning(self, scanning: bool) -> None:
        """Animate only while Device Engine is performing a genuine read-only scan."""

        if scanning:
            self.passport_scan_progress.begin()
            self.passport_state.setText("SCANNING DEVICE DNA")
            self.passport_state.setObjectName("Warning")
            self.passport_refresh_note.setText("READ-ONLY PROBES ACTIVE • NOTHING UPLOADED")
        else:
            self.passport_scan_progress.finish()
            if self.active_device is not None:
                self._render_live_passport(self.active_device, self.active_pack, record=False)
            else:
                self.passport_state.setText("AWAITING DEVICE")
                self.passport_state.setObjectName("Warning")
                self.passport_refresh_note.setText("READ-ONLY • PRIVATE • OFFLINE-FIRST")
        self._repolish(self.passport_state)

    def set_knowledge_lookup(
        self,
        device_serial: str,
        report: KnowledgeLookupReport | None,
        error: str = "",
    ) -> None:
        """Bind one offline Archives result to the exact current live passport."""

        device = self.active_device
        if device is None or device.serial != device_serial:
            self.active_knowledge_report = None
            self.knowledge_lookup_error = ""
            return
        self.active_knowledge_report = report
        self.active_knowledge_device_serial = device_serial
        self.knowledge_lookup_error = " ".join(str(error).replace("\x00", " ").split())[:500]
        self._render_live_passport(device, self.active_pack, record=False)

    def set_device_dna(self, profile: DeviceDnaProfile | None) -> None:
        """Show source-bound mission DNA only when it includes this exact live device."""

        device = self.active_device
        self.active_device_dna = (
            profile
            if profile is not None
            and device is not None
            and self._profile_matches_device(profile, device)
            else None
        )
        if device is not None:
            self._render_live_passport(device, self.active_pack, record=False)
        if self.active_pack is not None and self.active_report is not None:
            self._render_pack(self.active_pack, self.active_report)

    @staticmethod
    def _profile_matches_device(profile: DeviceDnaProfile, device: AndroidDevice) -> bool:
        codename = profile.fact("identity.codename")
        model = profile.fact("identity.model")
        live_facts = tuple(
            fact
            for fact in (codename, model)
            if fact is not None
            and "device.live" in fact.evidence_ids
            and fact.confidence is not EvidenceConfidence.UNCONFIRMED
        )
        if not live_facts:
            return False
        if codename in live_facts and device.codename:
            aliases = {
                value.strip().casefold()
                for value in codename.value.replace("|", ",").split(",")
                if value.strip()
            }
            if device.codename.casefold() not in aliases:
                return False
        return not (
            model in live_facts
            and device.model
            and model.value.strip().casefold() != device.model.strip().casefold()
        )

    def _request_passport_knowledge(self) -> None:
        report = self.active_knowledge_report
        if report is not None and report.matches:
            self.knowledge_query_requested.emit(report.matches[0].record.title[:160])

    def record_verified_flash(
        self,
        device_serial: str,
        project_name: str,
        result: VerifiedGuardianExecutionResult,
    ) -> bool:
        """Add one Guardian-verified flash to the private device timeline."""

        if self.intelligence_history is None:
            return False
        try:
            self.intelligence_history.record_verified_flash(
                device_serial,
                project_name,
                result,
            )
        except DeviceIntelligenceError as exc:
            self.intelligence_history_error = str(exc)
            return False
        if self.active_device is not None and self.active_device.serial == device_serial:
            self._render_live_passport(self.active_device, self.active_pack, record=False)
        return True

    def refresh_history(self) -> None:
        """Refresh timeline projections without probing or changing the phone."""

        if self.active_device is not None:
            self._render_live_passport(self.active_device, self.active_pack, record=False)

    def _render_live_passport(
        self,
        device: AndroidDevice,
        pack: DevicePack | None,
        *,
        match_reason: str = "",
        record: bool = False,
    ) -> None:
        snapshot = None
        history = ()
        if self.intelligence_history is not None:
            try:
                if record:
                    snapshot = self.intelligence_history.record_scan(
                        device,
                        pack,
                        match_reason,
                    )
                history = self.intelligence_history.load(
                    device_serial=device.serial,
                    limit=20,
                )
                snapshot = snapshot or (history[0] if history else None)
                self.intelligence_history_error = ""
            except DeviceIntelligenceError as exc:
                self.intelligence_history_error = str(exc)

        self.passport_name.setText(device.display_name)
        state = device.state.value.replace("_", " ").upper()
        self.passport_state.setText(
            "CONNECTED • PASSPORT CURRENT"
            if device.state.value == "device"
            else f"{state} • PARTIAL PASSPORT"
        )
        self.passport_state.setObjectName(
            "Good" if device.state.value == "device" and not device.errors else "Warning"
        )
        self.passport_identity.setText(
            f"{device.model or 'Model unconfirmed'}\n{device.codename or 'Codename unconfirmed'}"
        )
        region = snapshot.region if snapshot is not None else ""
        self.passport_platform.setText(
            f"{device.soc_platform or device.hardware or 'Chipset unconfirmed'}\n"
            f"{region or 'Region unconfirmed'}"
        )
        self.passport_firmware.setText(
            f"Android {device.android_version or 'unconfirmed'}\n"
            f"{device.rom_display or device.build_id or 'Firmware unconfirmed'}"
        )
        bootloader = (
            "Locked"
            if device.bootloader_locked is True
            else "Unlocked"
            if device.bootloader_locked is False
            else "Bootloader unconfirmed"
        )
        slot = device.slot_suffix.removeprefix("_").upper() or "unconfirmed"
        scheme = (
            "Virtual A/B"
            if device.virtual_ab is True
            else "A/B"
            if device.ab_update is True
            else "Single-slot reported"
            if device.ab_update is False
            else "scheme unconfirmed"
        )
        self.passport_boot.setText(f"{bootloader}\nSlot {slot} • {scheme}")

        dna = self.active_device_dna
        architecture = dna.fact("partition.architecture") if dna is not None else None
        if architecture is not None and architecture.confirmed:
            partition_text = architecture.value
            if dna.partitions:
                partition_text += f" • {len(dna.partitions)} mapped"
        elif snapshot is not None:
            partition_text = snapshot.partition_summary
        else:
            partition_text = "Exact partition inventory unconfirmed"
        self.passport_partitions.setText(partition_text)

        battery = (
            f"Battery {device.battery_percent}%"
            if device.battery_percent is not None
            else "Battery unconfirmed"
        )
        storage = (
            f"{human_bytes(device.storage.available_bytes)} free"
            if device.storage.available_bytes is not None
            else "storage unconfirmed"
        )
        health = snapshot.health_summary if snapshot is not None else "Live health unconfirmed"
        self.passport_health.setText(f"{battery} • {storage}\n{health}")

        upgrade = dna.fact("firmware.upgrade_relationship") if dna is not None else None
        self.passport_upgrade.setText(
            upgrade.value
            if upgrade is not None and upgrade.confirmed
            else "Select protected firmware in ROM Studio for an upgrade/downgrade verdict"
        )

        report = self.active_knowledge_report
        if self.knowledge_lookup_error:
            self.passport_knowledge.setText("Offline lookup needs attention")
            self.passport_knowledge_button.setVisible(False)
        elif report is not None and report.conflicts:
            self.passport_knowledge.setText(
                f"{len(report.conflicts)} conflicting guidance record(s)\n"
                f"STOP AND REVIEW • {report.safest_answer}"
            )
            self.passport_knowledge_button.setVisible(True)
        elif report is not None and report.matches:
            leading = report.matches[0]
            self.passport_knowledge.setText(
                f"{len(report.matches)} local match(es)\n"
                f"{leading.confidence.value.upper()} • {leading.record.title}"
            )
            self.passport_knowledge_button.setVisible(True)
        elif report is not None:
            self.passport_knowledge.setText("No compatible local record yet")
            self.passport_knowledge_button.setVisible(False)
        else:
            self.passport_knowledge.setText("Matching current evidence…")
            self.passport_knowledge_button.setVisible(False)

        counts = self._collect_timeline(device, history)
        if self.intelligence_history_error:
            self.passport_history.setText("Timeline integrity needs attention")
        else:
            latest = self._timeline_rows[0][2] if self._timeline_rows else "No history yet"
            self.passport_history.setText(
                f"{counts['scan']} scans • {counts['flash']} flashes • "
                f"{counts['repair']} repairs\nLatest: {latest}"
            )
        self.passport_timeline_button.setVisible(bool(self._timeline_rows))
        self.passport_refresh_note.setText(
            "READ-ONLY • PRIVATE • OFFLINE-FIRST"
            if not self.intelligence_history_error
            else "TIMELINE PRESERVED • INVALID DATA NOT OVERWRITTEN"
        )
        self._repolish(self.passport_state)

    def _collect_timeline(
        self,
        device: AndroidDevice,
        scans: tuple,
    ) -> dict[str, int]:
        rows: list[tuple[str, str, str, str, str]] = []
        for item in scans:
            rows.append(
                (
                    item.observed_at,
                    "SCAN",
                    "Device DNA scan",
                    f"{item.display_name} • {item.firmware_version or 'firmware unconfirmed'} • "
                    f"{item.connection_state}",
                    "verified",
                )
            )
        operations = ()
        if self.intelligence_history is not None:
            try:
                operations = self.intelligence_history.load_operations(
                    device_serial=device.serial,
                    limit=40,
                )
            except DeviceIntelligenceError as exc:
                self.intelligence_history_error = str(exc)
        for item in operations:
            rows.append(
                (
                    item.occurred_at,
                    item.event_type.upper(),
                    item.title,
                    item.detail,
                    item.outcome,
                )
            )
        repairs = ()
        if self.repair_history is not None and self.intelligence_history is not None:
            device_key = self.intelligence_history.privacy.pseudonym(device.serial)
            repairs = tuple(
                item for item in self.repair_history.list_recent() if item.device_key == device_key
            )[:40]
        for item in repairs:
            detail = item.verification_summary or (
                f"{len(item.reviewed_steps)}/{len(item.recommendations)} guided checkpoints reviewed; "
                "no repair success claimed"
            )
            rows.append(
                (
                    item.updated_at,
                    "REPAIR",
                    f"{item.concern.replace('_', ' ').title()} repair session",
                    detail,
                    "verified" if item.status == "verified" else "attention",
                )
            )
        self._timeline_rows = tuple(
            sorted(
                rows,
                key=lambda row: datetime.fromisoformat(row[0].replace("Z", "+00:00")),
                reverse=True,
            )[:60]
        )
        return {
            "scan": len(scans),
            "flash": len(operations),
            "repair": len(repairs),
        }

    def _open_private_timeline(self) -> None:
        if not self._timeline_rows:
            return
        dialog = QDialog(self)
        dialog.setObjectName("DeviceTimelineDialog")
        dialog.setWindowTitle("Private device timeline")
        dialog.setMinimumSize(760, 520)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        eyebrow = QLabel("DEVICE INTELLIGENCE HUB  •  LOCAL EVIDENCE TIMELINE")
        eyebrow.setObjectName("DevicePassportEyebrow")
        layout.addWidget(eyebrow)
        title = QLabel(self.passport_name.text())
        title.setObjectName("DialogTitle")
        layout.addWidget(title)
        boundary = QLabel(
            "Pseudonymous local history only. Flash entries appear only after a successful "
            "Guardian result; repair entries describe recorded evidence without inventing success."
        )
        boundary.setObjectName("DevicePassportBoundary")
        boundary.setWordWrap(True)
        layout.addWidget(boundary)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName("ScrollContent")
        timeline = QVBoxLayout(content)
        timeline.setContentsMargins(0, 0, 6, 0)
        timeline.setSpacing(8)
        for occurred_at, kind, event_title, detail, outcome in self._timeline_rows:
            card = QFrame()
            card.setObjectName("DeviceTimelineEvent")
            card.setProperty("timelineState", outcome)
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(14, 11, 14, 11)
            stamp = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
            marker = QLabel(f"{kind}\n{stamp.astimezone().strftime('%d %b %Y • %H:%M')}")
            marker.setObjectName("DeviceTimelineMarker")
            marker.setMinimumWidth(150)
            card_layout.addWidget(marker)
            copy = QVBoxLayout()
            heading = QLabel(event_title)
            heading.setObjectName("SectionTitle")
            description = QLabel(detail)
            description.setObjectName("Muted")
            description.setWordWrap(True)
            copy.addWidget(heading)
            copy.addWidget(description)
            card_layout.addLayout(copy, 1)
            timeline.addWidget(card)
        timeline.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        self._timeline_dialog = dialog
        dialog.finished.connect(lambda _result: setattr(self, "_timeline_dialog", None))
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _clear_live_passport(self) -> None:
        self.passport_name.setText("Connect an Android phone to unfold its Device DNA")
        self.passport_state.setText("AWAITING DEVICE")
        self.passport_state.setObjectName("Warning")
        for label in (
            self.passport_identity,
            self.passport_platform,
            self.passport_firmware,
            self.passport_boot,
            self.passport_partitions,
            self.passport_health,
            self.passport_upgrade,
            self.passport_knowledge,
            self.passport_history,
        ):
            label.setText("Unconfirmed")
        self.passport_knowledge_button.setVisible(False)
        self.passport_timeline_button.setVisible(False)
        self._timeline_rows = ()
        self.passport_refresh_note.setText("READ-ONLY • PRIVATE • OFFLINE-FIRST")
        self._repolish(self.passport_state)

    def set_catalog_checking(self) -> None:
        self.identity_catalog_title.setText("Checking official Android device IDs…")
        self.identity_catalog_detail.setText(
            "Google's public supported-device catalog is downloading in the background. "
            "Existing Device Packs and all Guardian locks remain unchanged."
        )
        self.identity_catalog_badge.setText("CHECKING • ZERO AUTHORITY")
        self.identity_catalog_badge.setObjectName("Warning")
        self.identity_catalog_button.setText("Syncing…")
        self.identity_catalog_button.setEnabled(False)
        self._repolish(self.identity_catalog_badge)

    def set_catalog_status(self, status: DeviceCatalogStatus) -> None:
        self.identity_catalog_button.setText("Refresh official IDs")
        self.identity_catalog_button.setEnabled(self.online_catalog_enabled)
        if not self.online_catalog_enabled:
            self.identity_catalog_title.setText(
                "Official Android device IDs • online sync disabled"
            )
            self.identity_catalog_detail.setText(
                "Enable verified online diagnostics and sources in Settings to refresh. Any "
                "already verified local catalog remains available for read-only recognition."
            )
            self.identity_catalog_badge.setText("LOCAL ONLY • ZERO AUTHORITY")
            self.identity_catalog_badge.setObjectName("Warning")
        elif status.valid:
            freshness = "CURRENT" if status.fresh else "UPDATE DUE"
            self.identity_catalog_title.setText(
                f"Official Android device IDs • {status.entry_count:,} verified rows"
            )
            self.identity_catalog_detail.setText(
                f"{status.reason}  •  SHA-256 {status.content_sha256[:16]}…  •  "
                "identity only; build authority: none; flash authority: none"
            )
            self.identity_catalog_badge.setText(f"{freshness} • READ ONLY")
            self.identity_catalog_badge.setObjectName("Good" if status.fresh else "Warning")
        else:
            self.identity_catalog_title.setText("Official Android device IDs • sync needed")
            self.identity_catalog_detail.setText(
                f"{status.reason}. Connect to the internet and sync; ROMVERSE will keep unknown "
                "identities explicit and will not guess."
            )
            self.identity_catalog_badge.setText("NOT SYNCED • ZERO AUTHORITY")
            self.identity_catalog_badge.setObjectName("Warning")
        self._repolish(self.identity_catalog_badge)
        if self.active_device is not None:
            self._render_catalog_identity(self.active_device)
            if self.active_pack is not None and self.active_report is not None:
                self._render_pack(self.active_pack, self.active_report)

    def catalog_refresh_failed(self, reason: str) -> None:
        self.identity_catalog_title.setText("Official Android device ID sync stopped safely")
        self.identity_catalog_detail.setText(
            f"{reason}. No unverified download was activated; any prior local catalog is reused "
            "only if it still passes every integrity check. No build, flash, approval, or phone "
            "action was created."
        )
        self.identity_catalog_badge.setText("SYNC FAILED • ZERO AUTHORITY")
        self.identity_catalog_badge.setObjectName("Danger")
        self.identity_catalog_button.setText("Retry official ID sync")
        self.identity_catalog_button.setEnabled(self.online_catalog_enabled)
        self._repolish(self.identity_catalog_badge)

    def _render_catalog_identity(self, device: AndroidDevice | None) -> DeviceCatalogMatch | None:
        if device is None or self.device_catalog is None:
            self.active_catalog_match = None
            return None
        match = self.device_catalog.match(device)
        self.active_catalog_match = match
        if match.matched:
            self.identity_catalog_title.setText(
                f"Official identity recognized • {match.marketing_name}"
            )
            model = f" • model {match.model}" if match.model else ""
            self.identity_catalog_detail.setText(
                f"Exact Build.BRAND / Build.DEVICE: {device.brand} / {device.codename}{model}  •  "
                f"{match.variant_count} matching catalog row(s)  •  retail identity only; "
                "an exact signed Device Pack is still required for build or flash readiness"
            )
            self.identity_catalog_badge.setText("EXACT ID • READ ONLY")
            self.identity_catalog_badge.setObjectName("Good")
        elif match.ambiguous:
            self.identity_catalog_title.setText("Official identity is ambiguous")
            self.identity_catalog_detail.setText(
                f"{match.reason}. Build.BRAND={device.brand or 'unknown'}  •  "
                f"Build.DEVICE={device.codename or 'unknown'}  •  model={device.model or 'unknown'}"
            )
            self.identity_catalog_badge.setText("NO GUESS • BUILD LOCKED")
            self.identity_catalog_badge.setObjectName("Danger")
        else:
            self.identity_catalog_title.setText("Official identity not confirmed")
            self.identity_catalog_detail.setText(
                f"{match.reason}. Build.BRAND={device.brand or 'unknown'}  •  "
                f"Build.DEVICE={device.codename or 'unknown'}  •  model={device.model or 'unknown'}  •  "
                "safe diagnostics remain available; model-specific build and flash stay locked"
            )
            self.identity_catalog_badge.setText("UNCONFIRMED • BUILD LOCKED")
            self.identity_catalog_badge.setObjectName("Warning")
        self._repolish(self.identity_catalog_badge)
        return match

    def _export_source_audit(self) -> None:
        if self.workspace is None:
            return
        exported = export_source_audit(self.registry, self.workspace)
        self.match_reason.setText(
            f"Source audit saved to {exported.output_path}  •  SHA-256 "
            f"{exported.sha256[:16]}…  •  execution authority: none"
        )

    @staticmethod
    def _metric(label: str, initial: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        value = QLabel(initial)
        value.setObjectName("HeroTitle")
        title = QLabel(label)
        title.setObjectName("Eyebrow")
        layout.addWidget(value)
        layout.addWidget(title)
        return card, value

    def set_devices(self, devices: list[AndroidDevice]) -> None:
        self.dashboard_handoff.setVisible(False)
        self.active_project_source = None
        self.active_project_draft = None
        self.devices = devices
        self.selector.blockSignals(True)
        self.selector.clear()
        for device in devices:
            self.selector.addItem(f"{device.display_name}  •  {device.masked_serial()}")
        self.selector.setVisible(len(devices) > 1)
        self.selector.blockSignals(False)
        if devices:
            self._render_device(devices[0])
        else:
            self.pack_name.setText("No active Device Pack")
            self.match_reason.setText("Connect a device to resolve the best matching pack.")
            self.pack_badge.setText("NO DEVICE")
            self.pack_badge.setObjectName("Warning")
            self.version_value.setText("—")
            self.active_report = None
            self.active_next_action = None
            self.active_requirements = None
            self.active_catalog_match = None
            self.active_pack = None
            self.active_device = None
            self.active_knowledge_report = None
            self.active_knowledge_device_serial = ""
            self.knowledge_lookup_error = ""
            self._repolish(self.pack_badge)
            self._clear_live_passport()
            self._set_guidance(
                "Connect a phone and ROMVERSE will identify its support level",
                "Device Atlas checks model, codename, firmware knowledge, and verified build "
                "contracts automatically. No phone operation is performed.",
                "Muted",
                False,
            )
            if self.device_catalog is not None:
                self.set_catalog_status(self.device_catalog.status())
            self._show_installed()

    def open_dashboard_intent(self, action: str) -> bool:
        """Explain the exact Device DNA evidence already owned by Device Atlas."""

        if str(action).strip() != "Device DNA":
            return False
        if self.active_project_source is not None:
            self.active_project_source = None
            self.active_project_draft = None
            if self.active_pack is not None and self.active_report is not None:
                self._render_pack(self.active_pack, self.active_report)
        device = self.active_device
        report = self.active_report
        pack = self.active_pack
        if device is None:
            self._show_dashboard_handoff(
                "Device DNA needs a current Android identity",
                "Connect and authorize one phone, then use Scan so Device Engine can collect "
                "read-only identity evidence. ROMVERSE will not choose a model or capability "
                "from an empty connection. NO SCAN, BUILD, FLASH, OR PHONE ACTION STARTED.",
                "EVIDENCE NEEDED",
                ready=False,
            )
            return True
        if report is None or pack is None:
            identity = (
                self.active_catalog_match.marketing_name
                if self.active_catalog_match is not None and self.active_catalog_match.matched
                else device.display_name
            )
            self._show_dashboard_handoff(
                f"Device DNA identity only • {identity}",
                f"Current Build.BRAND / Build.DEVICE evidence is "
                f"{device.brand or 'unknown'} / {device.codename or 'unknown'}, but no "
                "integrity-checked Device Pack produced a capability report. Build and flash "
                "remain locked; NO SCAN OR PHONE ACTION STARTED.",
                "IDENTITY ONLY",
                ready=False,
            )
            return True
        unresolved = len(report.checks) - report.passed_count
        build = "READY" if report.build_contract_ready else "LOCKED"
        flash = "READY" if report.flash_contract_ready else "LOCKED"
        self._show_dashboard_handoff(
            f"Device DNA • {report.model} / {report.codename}",
            f"Current Pack {report.pack_id} v{report.pack_version}  •  report "
            f"{report.report_digest[:16]}…  •  {report.passed_count}/{len(report.checks)} "
            f"readiness checks pass  •  {unresolved} unresolved  •  build {build}  •  flash "
            f"{flash}. Review the Requirements Blueprint below; NO SCAN, APPROVAL, BUILD, "
            "FLASH, OR PHONE ACTION STARTED.",
            "CURRENT EVIDENCE",
            ready=True,
        )
        if hasattr(self, "requirements_blueprint_frame"):
            self.body.ensureWidgetVisible(self.requirements_blueprint_frame, 0, 24)
        return True

    def open_rom_studio_project(
        self,
        project_id: str,
        project_name: str,
        pack_id: str,
        source_sha256: str,
    ) -> bool:
        """Bind one exact Studio source blueprint to the current phone requirements."""

        normalized_id = str(project_id).strip()
        clean_name = " ".join(str(project_name).replace("\x00", "").split())[:100]
        normalized_pack = str(pack_id).strip()
        source = str(source_sha256).strip().casefold()
        source_label = source[:16] + "…" if source else "not imported"
        if not normalized_id or not clean_name:
            return False
        project_source = self._load_project_source_requirements(
            normalized_id,
            str(project_name),
            normalized_pack,
            source,
        )
        expected = next(
            (item for item in self.registry.packs if item.pack_id == normalized_pack),
            None,
        )
        active_matches = bool(
            expected is not None
            and self.active_pack is not None
            and self.active_report is not None
            and self.active_pack.pack_id == expected.pack_id
            and self.active_report.pack_id == expected.pack_id
            and self.active_report.pack_version == expected.version
            and self.active_report.pack_sha256 == expected.sha256
        )
        source_matches = bool(
            expected is not None
            and expected.build_contract is not None
            and source
            and expected.build_contract.source.archive_sha256 == source
        )
        ready = bool(
            active_matches
            and source_matches
            and self.active_report is not None
            and self.active_report.build_contract_ready
        )
        project_phone_bound = False
        if (
            project_source is not None
            and self.active_pack is not None
            and self.active_report is not None
        ):
            try:
                self.requirements_service.assess(
                    self.active_pack,
                    self.active_report,
                    self.active_catalog_match,
                    self.tool_statuses,
                    project_source,
                )
            except ValueError:
                pass
            else:
                project_phone_bound = True
        self.active_project_source = project_source if project_phone_bound else None
        if project_phone_bound and self.active_pack is not None and self.active_report is not None:
            self._render_pack(self.active_pack, self.active_report)

        if project_phone_bound and project_source is not None:
            source_pack_bound = bool(
                expected is not None
                and expected.build_contract is not None
                and expected.build_contract.source.archive_sha256 == project_source.source_sha256
                and active_matches
            )
            effective_tools = (
                expected.build_contract.required_tools
                if source_pack_bound
                and expected is not None
                and expected.build_contract is not None
                else project_source.required_tools
            )
            exact_pack_ready = bool(
                source_pack_bound
                and self.active_report is not None
                and self.active_report.build_contract_ready
            )
            self._set_guidance(
                (
                    "✓ Phone and exact project source recognized — build planning is ready"
                    if exact_pack_ready
                    else "✓ Phone and project source recognized — local build preparation is ready"
                ),
                (
                    "The strict project source blueprint and this phone's exact Device Pack "
                    "agree. Build planning may continue; Guardian still revalidates every "
                    "artifact and phone-writing gate."
                    if exact_pack_ready
                    else "The strict project source blueprint matches this phone, but no exact "
                    "source-matched Device Pack contract is present. Use the project Build or "
                    "Compile lane below; flash remains locked."
                ),
                "Good" if exact_pack_ready else "Warning",
                True,
            )
            if not source_pack_bound and self.active_pack is not None:
                self.pack_name.setText(f"Phone Pack reference • {self.active_pack.display_name}")
                self.match_reason.setText(
                    f"Phone Pack {self.active_pack.pack_id} is for a different source; project "
                    f"{project_source.build_id} controls Build and Compile."
                )
                self.pack_badge.setText("REFERENCE ONLY • PROJECT SOURCE ACTIVE")
                self.pack_badge.setObjectName("Warning")
                self._repolish(self.pack_badge)
            detail = (
                f"{clean_name}  •  {project_source.build_id}  •  "
                f"LOCAL BUILD READY  •  FLASH "
                f"{'READY' if source_pack_bound and self.active_report is not None and self.active_report.flash_contract_ready else 'LOCKED'}  •  "
                f"EXACT PACK {'READY' if source_pack_bound else 'ABSENT'}  •  "
                f"{project_source.source_kind.upper()} VERIFIED  •  "
                f"{project_source.partition_count} PARTITIONS  •  "
                f"{project_source.codename.upper()} MATCHED  •  "
                f"{len(effective_tools)} HOST TOOLS."
            )
            badge = "PROJECT SOURCE BOUND"
            ready = True
        elif project_source is not None:
            current_target = (
                f"{self.active_report.manufacturer} / {self.active_report.codename}"
                if self.active_report is not None
                else "no current phone"
            )
            detail = (
                f"Exact project {normalized_id} has a strict {project_source.source_kind} "
                f"blueprint for {project_source.manufacturer} / {project_source.codename} / "
                f"{project_source.build_id} and protected source {source_label}, but Device Atlas "
                f"currently has {current_target}. Reconnect and scan the exact target; ROMVERSE "
                "will not apply this project's build or compile requirements to another phone."
            )
            badge = "TARGET REVALIDATION"
            ready = False
        elif not normalized_pack:
            detail = (
                f"Exact project {normalized_id} has protected source {source_label} and no Device "
                "Pack binding. Connect and scan the intended phone, then bind only an "
                "integrity-checked exact Pack; ROMVERSE will not infer one from a project name or "
                "firmware filename."
            )
            badge = "PACK REQUIRED"
        elif expected is None:
            detail = (
                f"Exact project {normalized_id} requests Pack {normalized_pack}, but that Pack is "
                f"not present in the integrity-checked registry  •  protected source "
                f"{source_label}. Install or restore the exact reviewed Pack before continuing."
            )
            badge = "PACK MISSING"
        elif ready and self.active_report is not None:
            detail = (
                f"Exact project {normalized_id} is source-bound to Pack {expected.pack_id} "
                f"v{expected.version}  •  source {source_label}  •  current phone report "
                f"{self.active_report.report_digest[:16]}… matches  •  build READY  •  flash "
                f"{'READY' if self.active_report.flash_contract_ready else 'LOCKED'}. Review the "
                "Requirements Blueprint below before returning to Forge Control."
            )
            badge = "EXACT MATCH"
        elif active_matches and source_matches and self.active_report is not None:
            unresolved = len(self.active_report.checks) - self.active_report.passed_count
            detail = (
                f"Exact project {normalized_id} and protected source {source_label} match Pack "
                f"{expected.pack_id} v{expected.version} and current phone report "
                f"{self.active_report.report_digest[:16]}…. {unresolved} readiness check(s) remain "
                f"unresolved  •  build LOCKED  •  flash "
                f"{'READY' if self.active_report.flash_contract_ready else 'LOCKED'}. Review the "
                "Requirements Blueprint below; ROMVERSE will not promote identity evidence into "
                "build or flash authority."
            )
            badge = "CURRENT • GATES REMAIN"
        else:
            active = self.active_pack.pack_id if self.active_pack is not None else "none"
            source_state = "matches" if source_matches else "does not match"
            detail = (
                f"Exact project {normalized_id} requests Pack {expected.pack_id} v{expected.version} "
                f"and its protected source {source_label} {source_state} that Pack's build "
                f"contract. The current Device Atlas phone context is {active}; connect and scan "
                "the exact target before accepting any capability or flash conclusion."
            )
            badge = "REVALIDATE DEVICE"
        self._show_dashboard_handoff(
            f"ROM Studio → {clean_name}",
            detail
            + (
                " NO ACTION STARTED."
                if project_phone_bound
                else " NO SCAN, BUILD, APPROVAL, FLASH, OR PHONE ACTION STARTED."
            ),
            badge,
            ready=ready,
            eyebrow="ROM STUDIO HANDOFF  •  EXACT PROJECT / SOURCE REQUIREMENTS",
        )
        if project_phone_bound and hasattr(self, "requirements_blueprint_frame"):
            # A source mismatch used to land on a requirements grid whose Flash button
            # only opened a guide. Put the new, actionable exact-source Pack draft at
            # the top of the handoff so the user has an immediate next step.
            focus = (
                self.requirements_blueprint_frame
                if source_pack_bound
                else getattr(self, "project_next_action_frame", self.requirements_blueprint_frame)
            )
            self.body.ensureWidgetVisible(focus, 0, 24)
        return True

    def _load_project_source_requirements(
        self,
        project_id: str,
        project_name: str,
        device_pack_id: str,
        source_sha256: str,
    ) -> ProjectSourceRequirements | None:
        """Reload one strict source receipt; retained UI text is never trusted."""

        if self.workspace is None:
            return None
        try:
            store = RomProjectStore(self.workspace)
            project = store.get(project_id)
            if (
                project.name != project_name
                or project.device_pack_id != device_pack_id
                or project.original is None
                or project.original.sha256 != source_sha256
            ):
                return None
            blueprint = FirmwareSourceIntelligenceService(
                store,
                self.tool_statuses or (),
                SubprocessRunner(),
            ).load(project_id)
            if (
                blueprint is None
                or blueprint.project_id != project_id
                or blueprint.source_archive_sha256 != source_sha256
                or not blueprint.baseline_candidate_ready
                or blueprint.phone_changed
                or not blueprint.manufacturer.strip()
                or not blueprint.codename.strip()
                or not blueprint.build_id.strip()
            ):
                return None
            signals = {
                "ota-payload": ("ota_payload",),
                "fastboot-super": ("super",),
                "partition-bundle": ("partition_bundle",),
            }.get(blueprint.source_kind)
            if signals is None:
                return None
            return ProjectSourceRequirements(
                project_id=project.project_id,
                project_name=project.name,
                source_sha256=project.original.sha256,
                device_pack_id=project.device_pack_id,
                source_kind=blueprint.source_kind,
                blueprint_digest=blueprint.blueprint_digest,
                plan_digest=blueprint.plan_digest,
                authority=blueprint.authority,
                manufacturer=blueprint.manufacturer,
                codename=blueprint.codename,
                build_id=blueprint.build_id,
                partition_count=len(blueprint.partitions),
                required_tools=required_tools_for_source(None, signals),
            )
        except (OSError, ProjectError, TypeError, ValueError):
            return None

    def _validated_active_project_source(self) -> ProjectSourceRequirements | None:
        source = self.active_project_source
        if source is None:
            return None
        current = self._load_project_source_requirements(
            source.project_id,
            source.project_name,
            source.device_pack_id,
            source.source_sha256,
        )
        return current if current == source else None

    def _load_project_source_avb(
        self, source: ProjectSourceRequirements
    ) -> SourceAvbTopologyReceipt | None:
        """Reload optional strict OEM-source AVB evidence for a private Pack draft."""

        if self.workspace is None:
            return None

        def resolved_tool(status_name: str, executable: str) -> Path | None:
            configured = next(
                (
                    Path(item.path)
                    for item in (self.tool_statuses or ())
                    if item.name == status_name and item.available and item.path
                ),
                None,
            )
            found = shutil.which(executable)
            return configured or (Path(found) if found else None)

        payload_tool = resolved_tool("Payload Dumper", "payload-dumper-go")
        avbtool = resolved_tool("AVBTool", "avbtool")
        if payload_tool is None or avbtool is None:
            return None
        try:
            store = RomProjectStore(self.workspace)
            runner = SubprocessRunner()
            payloads = PayloadService(store, payload_tool, runner)
            receipt = SourceAvbEvidenceService(
                store,
                payloads,
                avbtool,
                runner,
            ).load(source.project_id)
        except (OSError, ProjectError, TypeError, ValueError):
            return None
        if (
            receipt is None
            or receipt.source_original_sha256 != source.source_sha256
            or receipt.phone_changed
        ):
            return None
        return receipt

    def open_forge_return(
        self,
        pack_id: str,
        pack_sha256: str,
        report_digest: str,
    ) -> bool:
        """Restore one freshly verified Forge context to its exact Device Atlas report."""

        pack = self.active_pack
        report = self.active_report
        if (
            pack is None
            or report is None
            or pack.pack_id != pack_id
            or pack.sha256 != pack_sha256
            or report.pack_id != pack.pack_id
            or report.pack_version != pack.version
            or report.pack_sha256 != pack.sha256
            or report.report_digest != report_digest
        ):
            return False
        if self.active_project_source is not None:
            self.active_project_source = None
            self._render_pack(pack, report)
        build = "READY" if report.build_contract_ready else "LOCKED"
        flash = "READY" if report.flash_contract_ready else "LOCKED"
        self._show_dashboard_handoff(
            f"Forge Arsenal → {pack.display_name}",
            f"Pack {pack.pack_id} v{pack.version}  •  SHA-256 {pack.sha256[:16]}…  •  report "
            f"{report.report_digest[:16]}…  •  build {build}  •  flash {flash}  •  "
            "AUTHORITY NONE  •  NO ACTION STARTED.",
            "EXACT REPORT RESTORED",
            ready=report.build_contract_ready,
            eyebrow="FORGE ARSENAL HANDOFF  •  EXACT DEVICE PACK REPORT",
        )
        if hasattr(self, "requirements_blueprint_frame"):
            self.body.ensureWidgetVisible(self.requirements_blueprint_frame, 0, 24)
        return True

    def _show_dashboard_handoff(
        self,
        title: str,
        detail: str,
        badge: str,
        *,
        ready: bool,
        eyebrow: str = "COMMAND DECK HANDOFF  •  CURRENT DEVICE DNA EVIDENCE",
    ) -> None:
        self.dashboard_handoff_eyebrow.setText(eyebrow)
        self.dashboard_handoff_title.setText(title)
        self.dashboard_handoff_detail.setText(detail)
        self.dashboard_handoff_badge.setText(badge)
        self.dashboard_handoff_badge.setObjectName("Good" if ready else "Warning")
        self._repolish(self.dashboard_handoff_badge)
        self.dashboard_handoff.setVisible(True)

    def _select(self, index: int) -> None:
        if 0 <= index < len(self.devices):
            self.active_project_source = None
            self.active_project_draft = None
            self._render_device(self.devices[index])

    def _render_device(self, device: AndroidDevice) -> None:
        self.active_foundry_revision = None
        self.foundry_inventory = None
        if self.active_knowledge_device_serial != device.serial:
            self.active_knowledge_report = None
            self.active_knowledge_device_serial = ""
            self.knowledge_lookup_error = ""
        if self.active_device_dna is not None and not self._profile_matches_device(
            self.active_device_dna,
            device,
        ):
            self.active_device_dna = None
        official_identity = self._render_catalog_identity(device)
        resolution = self.registry.resolve(device)
        if resolution.pack is None:
            self.pack_name.setText("No valid pack matched")
            self.match_reason.setText(resolution.reason)
            self.pack_badge.setText("UNMATCHED")
            self.pack_badge.setObjectName("Danger")
            self.version_value.setText("—")
            self.active_report = None
            self.active_next_action = None
            self.active_requirements = None
            self.active_pack = None
            self.active_device = device
            self._repolish(self.pack_badge)
            self._render_live_passport(
                device,
                None,
                match_reason=resolution.reason,
                record=True,
            )
            self._set_guidance(
                "This phone is not yet supported for ROM building",
                "Safe device diagnostics remain available, but ROMVERSE found no integrity-checked "
                "model contract and will not guess. Device-changing work stays locked.",
                "Danger",
                False,
            )
            self._show_installed()
            return
        pack = resolution.pack
        self.pack_name.setText(pack.display_name)
        self.match_reason.setText(
            f"{resolution.reason}  •  {pack.pack_id}  •  SHA-256 {pack.sha256[:12]}…"
        )
        if pack.build_contract is not None:
            self.pack_badge.setText("EXACT BUILD PACK • DEVICE ACTIONS LOCKED")
        elif pack.model_patterns or pack.product_patterns:
            self.pack_badge.setText("EXACT IDENTITY • READ ONLY")
        else:
            self.pack_badge.setText("OEM KNOWLEDGE • READ ONLY")
        self.pack_badge.setObjectName("Good")
        self.version_value.setText(pack.version)
        self._repolish(self.pack_badge)
        self.active_pack = pack
        self.active_device = device
        attestation = (
            self.attestation_store.load_exact(pack, device)
            if self.attestation_store is not None
            else None
        )
        self.active_report = self.validation_service.assess(pack, device, attestation)
        self._render_live_passport(
            device,
            pack,
            match_reason=resolution.reason,
            record=True,
        )
        generic = pack.priority <= 0 or pack.manufacturers == ("*",)
        if self.active_report.build_contract_ready:
            self._set_guidance(
                "✓ Phone recognized — ROM build planning is ready",
                "ROMVERSE verified an exact model/build contract. Continue to ROM Studio; "
                "Genesis Sequence will still fingerprint the chosen firmware and diagnose every "
                "stage before any Guardian handoff.",
                "Good",
                True,
            )
        elif generic and official_identity is not None and official_identity.matched:
            self._set_guidance(
                "✓ Phone identity recognized — exact build support is still locked",
                f"Google's official catalog identifies {official_identity.marketing_name}, but "
                "identity data is not a partition map or flash contract. ROMVERSE can diagnose "
                "the phone while Device Atlas gathers a signed exact model/source contract.",
                "Warning",
                True,
            )
        elif generic:
            self._set_guidance(
                "Phone connected — model-specific build support is limited",
                "ROMVERSE can run safe generic diagnostics, but this match does not contain an "
                "exact build contract. ROM building and device-changing work remain locked.",
                "Warning",
                True,
            )
        else:
            self._set_guidance(
                "Phone recognized — safe diagnostics are ready",
                "ROMVERSE has model-specific knowledge, but not a complete verified build contract "
                "for this exact firmware. The evidence roadmap below explains what is still needed.",
                "Warning",
                True,
            )
        self._render_pack(pack, self.active_report)
        self.readiness_changed.emit(self.active_report)

    def _set_guidance(
        self,
        title: str,
        detail: str,
        object_name: str,
        can_continue: bool,
    ) -> None:
        self.guidance_title.setText(title)
        self.guidance_title.setObjectName(object_name)
        self.guidance_detail.setText(detail)
        self.continue_button.setVisible(can_continue)
        self.continue_button.setEnabled(can_continue)
        self._repolish(self.guidance_title)

    def _render_pack(self, pack: DevicePack, report: DevicePackValidationReport) -> None:
        self._clear()
        self.validation_rows.clear()
        self.requirement_buttons.clear()
        self.requirement_badges.clear()
        project_source = self._validated_active_project_source()
        project_source_stale = self.active_project_source is not None and project_source is None
        project_contract_bound = bool(
            project_source is not None
            and pack.build_contract is not None
            and report.build_contract_ready
            and pack.build_contract.source.archive_sha256 == project_source.source_sha256
        )
        project_override = project_source is not None and not project_contract_bound
        project_routes_suppressed = project_source_stale or project_override
        self.active_project_draft = (
            self._load_current_project_draft(project_source) if project_override else None
        )
        prepared_draft = self.active_project_draft
        current_dna = self.active_device_dna
        dna_matches_project = bool(
            current_dna is not None
            and project_source is not None
            and current_dna.project_id == project_source.project_id
            and current_dna.source_sha256 == project_source.source_sha256
        )
        dna_revision_ready = bool(
            project_override
            and dna_matches_project
            and (
                prepared_draft is None
                or prepared_draft.device_dna_profile_digest != current_dna.profile_digest
            )
        )
        self.active_next_action = (
            None if project_routes_suppressed else self.validation_service.next_safe_action(report)
        )
        roadmap = QFrame()
        roadmap.setObjectName("Card")
        roadmap_layout = QVBoxLayout(roadmap)
        roadmap_layout.setContentsMargins(10, 16, 10, 16)
        roadmap_layout.setSpacing(10)
        roadmap_header = QHBoxLayout()
        roadmap_copy = QVBoxLayout()
        roadmap_title = QLabel(
            "PROJECT SOURCE CHANGED  •  REOPEN FROM ROM STUDIO"
            if project_source_stale
            else "PHONE PACK REFERENCE  •  PROJECT SOURCE DIFFERS"
            if project_override
            else "MODEL-SPECIFIC VALIDATION ROADMAP"
        )
        roadmap_title.setObjectName("Eyebrow")
        roadmap_description = QLabel(
            "The retained project source receipt no longer revalidates. All project routes "
            "are locked until the exact project is reopened from ROM Studio."
            if project_source_stale
            else f"The phone matched Pack {pack.pack_id}, but its source contract is not the "
            f"current project {project_source.source_kind} baseline. Use the project-scoped "
            "Requirements Blueprint below; these Pack rows remain reference evidence only."
            if project_override and project_source is not None
            else f"Evidence contract for {report.model} / {report.codename}. Checks measure "
            "readiness; they never grant execution authority."
        )
        roadmap_description.setObjectName("Muted")
        roadmap_description.setWordWrap(True)
        roadmap_copy.addWidget(roadmap_title)
        roadmap_copy.addWidget(roadmap_description)
        roadmap_header.addLayout(roadmap_copy, 1)
        build_state = QLabel(
            "PROJECT BLUEPRINT STALE  •  ROUTES LOCKED"
            if project_source_stale
            else f"PHONE PACK {report.passed_count}/{len(report.checks)}  •  "
            "PROJECT BLUEPRINT ACTIVE  •  FLASH LOCKED"
            if project_override
            else f"{report.passed_count} / {len(report.checks)} VERIFIED  •  "
            + ("BUILD READY" if report.build_contract_ready else "BUILD LOCKED")
            + "  •  "
            + ("FLASH CONTRACT READY" if report.flash_contract_ready else "FLASH LOCKED")
        )
        build_state.setObjectName(
            "Warning"
            if project_routes_suppressed
            else "Good"
            if report.flash_contract_ready
            else "Warning"
            if report.build_contract_ready
            else "Danger"
        )
        roadmap_header.addWidget(build_state)
        roadmap_layout.addLayout(roadmap_header)

        next_action = QFrame()
        next_action.setObjectName("DiagnosticHandoffBar")
        self.project_next_action_frame = next_action
        next_layout = QHBoxLayout(next_action)
        next_layout.setContentsMargins(16, 13, 16, 13)
        next_copy = QVBoxLayout()
        next_eyebrow = QLabel("NEXT SAFE ACTION  •  DETERMINISTIC FROM CURRENT EVIDENCE")
        next_eyebrow.setObjectName("Eyebrow")
        self.next_action_title = QLabel(
            "Reopen the exact project from ROM Studio"
            if project_source_stale
            else "Attach the current sealed Device DNA revision"
            if dna_revision_ready
            else "Exact-source Pack draft prepared"
            if prepared_draft is not None
            else "Prepare the exact-source Device Pack draft"
            if project_override
            else self.active_next_action.title
        )
        self.next_action_title.setObjectName("SectionTitle")
        self.next_action_detail = QLabel(
            "The retained source receipt changed, so ROMVERSE removed every project action."
            if project_source_stale
            else f"The exact project now has sealed Device DNA {current_dna.profile_digest[:16]}…; "
            "record its privacy-safe hardware, firmware, slot and partition facts as a new immutable "
            "draft revision. The existing revision is retained and no authority changes."
            if dna_revision_ready and current_dna is not None
            else f"ROMVERSE reloaded the private draft for {prepared_draft.build_id} and its "
            f"{prepared_draft.partition_count}-partition source blueprint. This step is complete; "
            f"review the {len(prepared_draft.missing_flash_contracts)} genuinely missing flash "
            "contracts instead of creating the same draft again."
            if prepared_draft is not None
            else "Local build preparation is ready, but the installed phone Pack describes a "
            "different firmware source. Create a private draft that binds this exact source, "
            "phone identity, partition blueprint, required tools, and every still-missing flash "
            "contract for review."
            if project_override
            else self.active_next_action.detail
        )
        self.next_action_detail.setObjectName("Muted")
        self.next_action_detail.setWordWrap(True)
        next_copy.addWidget(next_eyebrow)
        next_copy.addWidget(self.next_action_title)
        next_copy.addWidget(self.next_action_detail)
        next_layout.addLayout(next_copy, 1)
        scope = (
            "stale"
            if project_source_stale
            else "project"
            if project_override
            else self.active_next_action.scope
        )
        self.next_action_badge = QLabel(
            "ROUTES LOCKED"
            if project_source_stale
            else "DNA EVIDENCE READY • NEW REVISION"
            if dna_revision_ready
            else "DRAFT VERIFIED • FLASH EVIDENCE NEXT"
            if prepared_draft is not None
            else "BUILD READY • PACK DRAFT NEXT"
            if project_override
            else "READY • GUARDIAN ACTIVE"
            if scope == "ready"
            else f"{scope.upper()} GATE • ZERO AUTHORITY"
        )
        self.next_action_badge.setObjectName(
            "Good" if scope == "ready" else "Danger" if scope == "build" else "Warning"
        )
        next_layout.addWidget(self.next_action_badge)
        self.next_action_button = QPushButton(
            "Reopen from ROM Studio"
            if project_source_stale
            else "Attach sealed Device DNA revision"
            if dna_revision_ready
            else "Review draft and missing evidence"
            if prepared_draft is not None
            else "Prepare exact-source Pack draft"
            if project_override
            else self.active_next_action.button_label
        )
        self.next_action_button.setObjectName("Primary")
        self.next_action_button.setToolTip(
            "Reviews the integrity-reloaded draft and its exact missing-contract checklist. "
            "It does not recreate the file, activate flashing, or make a public claim."
            if prepared_draft is not None and not dna_revision_ready
            else "Creates a new immutable draft revision from the current sealed Device DNA. It "
            "excludes serials and personal data, retains region as observation only, and grants no authority."
            if dna_revision_ready
            else "Creates a private, source-bound Device Pack development draft with a precise "
            "missing-contract checklist. It cannot activate flashing or make a public claim."
            if project_override
            else "Opens the exact ROMVERSE page or verified guide selected from this current "
            "readiness report. It starts no worker, approval, build, or phone action."
        )
        self.next_action_button.setEnabled(not project_source_stale)
        if dna_revision_ready:
            self.next_action_button.clicked.connect(self._export_project_pack_draft)
        elif prepared_draft is not None:
            self.next_action_button.clicked.connect(self._review_project_pack_draft)
        elif project_override:
            self.next_action_button.clicked.connect(self._export_project_pack_draft)
        elif not project_routes_suppressed:
            self.next_action_button.clicked.connect(self._request_next_action)
        next_layout.addWidget(self.next_action_button)
        roadmap_layout.addWidget(next_action)
        self.next_action_feedback = QLabel("")
        self.next_action_feedback.setObjectName("Muted")
        self.next_action_feedback.setWordWrap(True)
        roadmap_layout.addWidget(self.next_action_feedback)
        self._render_foundry_blueprint(roadmap_layout)

        if project_source_stale:
            self.active_requirements = None
        else:
            self.active_requirements = self.requirements_service.assess(
                pack,
                report,
                self.active_catalog_match,
                self.tool_statuses,
                project_source,
            )
        self._render_requirements_blueprint(roadmap_layout)

        for check in report.checks:
            row = QFrame()
            row.setObjectName("Card")
            tooltip = (
                f"{check.label}\n\nCurrent evidence:\n{check.evidence}\n\n"
                f"Possible fix:\n{check.resolution}"
            )
            row.setToolTip(tooltip)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(12, 10, 12, 10)
            symbol = QLabel(
                {
                    ValidationState.PASS: "✓",
                    ValidationState.ATTENTION: "!",
                    ValidationState.BLOCKED: "×",
                }[check.state]
            )
            symbol.setObjectName(
                "Good"
                if check.state is ValidationState.PASS
                else "Warning"
                if check.state is ValidationState.ATTENTION
                else "Danger"
            )
            symbol.setFixedWidth(24)
            symbol.setToolTip(tooltip)
            copy_layout = QVBoxLayout()
            label = QLabel(check.label)
            label.setObjectName("SectionTitle")
            label.setToolTip(tooltip)
            evidence = QLabel(check.evidence)
            evidence.setObjectName("Muted")
            evidence.setWordWrap(True)
            evidence.setToolTip(tooltip)
            copy_layout.addWidget(label)
            copy_layout.addWidget(evidence)
            badge = QLabel(check.state.value.upper())
            badge.setObjectName(
                "Good"
                if check.state is ValidationState.PASS
                else "Warning"
                if check.state is ValidationState.ATTENTION
                else "Danger"
            )
            badge.setToolTip(tooltip)
            row_layout.addWidget(symbol)
            row_layout.addLayout(copy_layout, 1)
            row_layout.addWidget(badge)
            roadmap_layout.addWidget(row)
            self.validation_rows[check.check_id] = row

        export_line = QHBoxLayout()
        export_explanation = QLabel(
            "Need a missing model contract? Export a privacy-safe maintainer request containing "
            "only pack, model, codename, and failed-check evidence."
        )
        export_explanation.setObjectName("Muted")
        export_explanation.setWordWrap(True)
        export_line.addWidget(export_explanation, 1)
        self.export_button = QPushButton("Export validation request")
        self.export_button.setEnabled(self.workspace is not None)
        self.export_button.setToolTip(
            "Creates an evidence-only JSON request. It contains no serial, IMEI, accounts, "
            "user files, signing keys, or authority to enable capabilities."
        )
        self.export_button.clicked.connect(self._export_validation_request)
        export_line.addWidget(self.export_button)
        self.physical_request_button = QPushButton("Export physical test request")
        self.physical_request_button.setEnabled(
            self.workspace is not None and pack.build_contract is not None
        )
        self.physical_request_button.setToolTip(
            "Creates a privacy-safe, exact-device challenge for an independent recovery lab. "
            "It does not certify the Pack or unlock Guardian."
        )
        self.physical_request_button.clicked.connect(self._export_physical_request)
        export_line.addWidget(self.physical_request_button)
        roadmap_layout.addLayout(export_line)
        draft_line = QHBoxLayout()
        draft_explanation = QLabel(
            "Missing an exact model contract? ROMVERSE can prepare a privacy-safe review draft "
            "from this phone's Android identity and the Pack's existing authoritative sources. "
            "It cannot activate or unlock any capability."
        )
        draft_explanation.setObjectName("Muted")
        draft_explanation.setWordWrap(True)
        draft_line.addWidget(draft_explanation, 1)
        self.draft_button = QPushButton("Prepare model Pack draft")
        self.draft_button.setEnabled(
            self.workspace is not None
            and self.active_device is not None
            and bool(pack.knowledge_sources)
            and not report.build_contract_ready
            and self.active_foundry_revision is None
        )
        if self.active_foundry_revision is not None:
            self.draft_button.setText("Model Pack draft recorded")
        self.draft_button.setToolTip(
            "Creates a private, content-addressed draft with exact reported model/product "
            "patterns and reviewed source starting points. It excludes the serial and remains "
            "publication_status: draft, so Device Atlas rejects it as an active Pack."
        )
        self.draft_button.clicked.connect(self._export_model_draft)
        draft_line.addWidget(self.draft_button)
        roadmap_layout.addLayout(draft_line)
        import_line = QHBoxLayout()
        import_explanation = QLabel(
            "Received a signed physical-test envelope? ROMVERSE verifies its release key, "
            "exact Pack and firmware binding, expiry, hardware identity, and required scenarios "
            "before storing it."
        )
        import_explanation.setObjectName("Muted")
        import_explanation.setWordWrap(True)
        import_line.addWidget(import_explanation, 1)
        self.import_attestation_button = QPushButton("Import signed test evidence…")
        self.import_attestation_button.setEnabled(
            self.attestation_store is not None and pack.build_contract is not None
        )
        self.import_attestation_button.setToolTip(
            "Untrusted, expired, mismatched, altered, or oversized envelopes are rejected and "
            "never persisted. Importing a file cannot bypass another Guardian gate."
        )
        self.import_attestation_button.clicked.connect(self._import_physical_attestation)
        import_line.addWidget(self.import_attestation_button)
        roadmap_layout.addLayout(import_line)
        self.export_status = QLabel("")
        self.export_status.setObjectName("Muted")
        self.export_status.setWordWrap(True)
        roadmap_layout.addWidget(self.export_status)
        self.body_layout.addWidget(roadmap)

        if pack.knowledge_sources:
            sources_title = QLabel("Authoritative knowledge sources")
            sources_title.setObjectName("SectionTitle")
            self.body_layout.addWidget(sources_title)
            for source in pack.knowledge_sources:
                card = QFrame()
                card.setObjectName("Card")
                layout = QVBoxLayout(card)
                layout.setContentsMargins(18, 14, 18, 14)
                link = QLabel(
                    f'<a style="color:#43DDF2" href="{html.escape(source.url, quote=True)}">'
                    f"{html.escape(source.label)}</a>"
                )
                link.setObjectName("SectionTitle")
                link.setOpenExternalLinks(True)
                detail = QLabel(
                    f"{source.authority}  •  {source.scope}  •  source checked {source.verified_on}"
                )
                detail.setObjectName("Warning" if source.is_stale() else "Muted")
                detail.setWordWrap(True)
                freshness = QLabel("REVIEW DUE" if source.is_stale() else "SOURCE CURRENT")
                freshness.setObjectName("Warning" if source.is_stale() else "Good")
                layout.addWidget(link)
                layout.addWidget(detail)
                layout.addWidget(freshness)
                self.body_layout.addWidget(card)

        title = QLabel("Declared capabilities")
        title.setObjectName("SectionTitle")
        self.body_layout.addWidget(title)
        for capability in pack.capabilities:
            card = QFrame()
            card.setObjectName("Card")
            layout = QHBoxLayout(card)
            layout.setContentsMargins(18, 14, 18, 14)
            detail = QVBoxLayout()
            name = QLabel(capability.label)
            name.setObjectName("SectionTitle")
            copy = QLabel(capability.detail)
            copy.setObjectName("Muted")
            copy.setWordWrap(True)
            scope = QLabel(f"Scope  •  {capability.scope.replace('_', ' ')}")
            scope.setObjectName("Muted")
            detail.addWidget(name)
            detail.addWidget(copy)
            detail.addWidget(scope)
            badge = QLabel(capability.status.value.upper())
            badge.setObjectName(
                "Good"
                if capability.status is CapabilityStatus.SUPPORTED
                else "Warning"
                if capability.status is CapabilityStatus.LIMITED
                else "Muted"
            )
            layout.addLayout(detail, 1)
            layout.addWidget(badge)
            self.body_layout.addWidget(card)
        if pack.notes:
            notes = QFrame()
            notes.setObjectName("Card")
            layout = QVBoxLayout(notes)
            heading = QLabel("Pack boundaries")
            heading.setObjectName("SectionTitle")
            copy = QLabel("\n".join(f"• {note}" for note in pack.notes))
            copy.setObjectName("Muted")
            copy.setWordWrap(True)
            layout.addWidget(heading)
            layout.addWidget(copy)
            self.body_layout.addWidget(notes)
        self.body_layout.addStretch()

    def _render_requirements_blueprint(self, parent: QVBoxLayout) -> None:
        blueprint = self.active_requirements
        if blueprint is None:
            return
        self.requirement_buttons.clear()
        self.requirement_badges.clear()
        frame = QFrame()
        frame.setObjectName("RequirementsBlueprint")
        self.requirements_blueprint_frame = frame
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 15, 18, 15)
        layout.setSpacing(11)
        header = QHBoxLayout()
        copy = QVBoxLayout()
        eyebrow = QLabel("AUTOMATIC REQUIREMENTS BLUEPRINT  •  CURRENT EVIDENCE ONLY")
        eyebrow.setObjectName("Eyebrow")
        title = QLabel("What this phone needs to identify, build, compile, and flash")
        title.setObjectName("SectionTitle")
        if blueprint.project_scoped:
            detail_text = (
                f"Project {blueprint.project_name}  •  {blueprint.model} / "
                f"{blueprint.codename}  •  source {blueprint.project_source_sha256[:12]}…  •  "
                f"{blueprint.source_kind} / {blueprint.source_build_id}  •  "
                f"{blueprint.source_partition_count} partition records"
            )
        else:
            detail_text = (
                f"Bound to {blueprint.model} / {blueprint.codename}  •  Pack "
                f"{blueprint.pack_id}  •  SHA-256 {blueprint.pack_sha256[:12]}…"
            )
        detail = QLabel(detail_text)
        detail.setObjectName("Muted")
        detail.setWordWrap(True)
        copy.addWidget(eyebrow)
        copy.addWidget(title)
        copy.addWidget(detail)
        header.addLayout(copy, 1)
        digest_text = f"REPORT {blueprint.report_digest[:12]}…"
        if blueprint.project_scoped:
            digest_text += f"  •  SOURCE PLAN {blueprint.source_plan_digest[:12]}…"
        digest = QLabel(digest_text + "  •  ZERO AUTHORITY")
        digest.setObjectName("Warning")
        header.addWidget(digest)
        layout.addLayout(header)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        for index, lane in enumerate(blueprint.lanes):
            card = QFrame()
            card.setObjectName("RequirementLane")
            card.setProperty("state", lane.state.value)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 12, 14, 12)
            card_layout.setSpacing(7)
            lane_header = QHBoxLayout()
            lane_title = QLabel(lane.title)
            lane_title.setObjectName("SectionTitle")
            lane_header.addWidget(lane_title, 1)
            badge = QLabel(lane.badge)
            badge.setObjectName(
                "Good"
                if lane.state is RequirementState.VERIFIED
                else "Warning"
                if lane.state in {RequirementState.DECLARED, RequirementState.NEEDS_EVIDENCE}
                else "Danger"
            )
            lane_header.addWidget(badge)
            card_layout.addLayout(lane_header)
            summary = QLabel(lane.summary)
            summary.setObjectName("Muted")
            summary.setWordWrap(True)
            card_layout.addWidget(summary)
            requirements = QLabel(
                "REQUIRES\n" + " • ".join(lane.requirements)
                if lane.requirements
                else "REQUIRES\nNo additional evidence reported"
            )
            requirements.setObjectName("RequirementNeeds")
            requirements.setWordWrap(True)
            requirements.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            card_layout.addWidget(requirements, 1)
            button = QPushButton(lane.button_label)
            button.setObjectName("Primary" if lane.state is RequirementState.VERIFIED else "")
            button.setToolTip(
                "Revalidates this lane against the current report before opening its connected "
                "Desktop feature. It starts no approval, build, flash, or device-changing action."
            )
            button.clicked.connect(
                lambda _checked=False, lane_id=lane.lane_id: self._request_requirement(lane_id)
            )
            card_layout.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)
            grid.addWidget(card, index // 2, index % 2)
            self.requirement_buttons[lane.lane_id] = button
            self.requirement_badges[lane.lane_id] = badge
        layout.addLayout(grid)
        self.requirements_feedback = QLabel("")
        self.requirements_feedback.setObjectName("Muted")
        self.requirements_feedback.setWordWrap(True)
        layout.addWidget(self.requirements_feedback)
        parent.addWidget(frame)

    def _request_next_action(self) -> None:
        action = self.active_next_action
        report = self.active_report
        if action is None or report is None:
            return
        self.next_action_requested.emit(
            action.route,
            action.article_key,
            action.check_id,
            report.report_digest,
        )

    def _request_rom_studio(self) -> None:
        report = self.active_report
        if report is not None:
            self.rom_studio_requested.emit(report.report_id, report.report_digest)

    def next_action_handoff_stopped(self, reason: str) -> None:
        """Keep a refused readiness handoff visible without relying on a toast."""

        if not hasattr(self, "next_action_feedback"):
            return
        self.next_action_feedback.setText(
            f"NEXT ACTION STOPPED  •  {reason}  •  NO WORKER OR PHONE ACTION STARTED"
        )
        self.next_action_feedback.setObjectName("Danger")
        self._repolish(self.next_action_feedback)

    def current_requirements(self) -> DeviceRequirementsBlueprint | None:
        report = self.active_report
        pack = self.active_pack
        if report is None or pack is None:
            return None
        project_source = self._validated_active_project_source()
        if self.active_project_source is not None and project_source is None:
            return None
        try:
            blueprint = self.requirements_service.assess(
                pack,
                report,
                self.active_catalog_match,
                self.tool_statuses,
                project_source,
            )
        except ValueError:
            return None
        self.active_requirements = blueprint
        return blueprint

    def set_tool_statuses(self, statuses: tuple[ToolStatus, ...]) -> None:
        """Refresh the visible compile lane from Forge Arsenal's current evidence."""

        if not isinstance(statuses, tuple) or not all(
            isinstance(status, ToolStatus) for status in statuses
        ):
            return
        self.tool_statuses = statuses
        if self.active_pack is None or self.active_report is None:
            return
        self._render_pack(self.active_pack, self.active_report)

    def _request_requirement(self, lane_id: str) -> None:
        blueprint = self.current_requirements()
        if blueprint is None:
            self.requirement_handoff_stopped(
                lane_id,
                "The project, protected source, or source blueprint changed",
            )
            return
        lane = blueprint.lane(lane_id)
        if lane is None:
            return
        self.requirement_requested.emit(
            lane.lane_id,
            lane.route,
            lane.article_key,
            blueprint.report_digest,
        )

    def requirement_handoff_stopped(self, lane_id: str, reason: str) -> None:
        """Keep a refused blueprint route visible without substituting another lane."""

        if not hasattr(self, "requirements_feedback"):
            return
        label = lane_id.replace("-", " ").upper() or "REQUIREMENT"
        self.requirements_feedback.setText(
            f"{label} HANDOFF STOPPED  •  {reason}  •  NO APPROVAL, BUILD, FLASH, OR DEVICE-CHANGING ACTION STARTED"
        )
        self.requirements_feedback.setObjectName("Danger")
        self._repolish(self.requirements_feedback)

    def _export_validation_request(self) -> None:
        if self.active_report is None or self.workspace is None:
            return
        exported = self.validation_service.export_request(self.active_report, self.workspace)
        self.export_status.setText(
            f"Saved {exported.output_path}  •  SHA-256 {exported.sha256[:16]}…  •  "
            "evidence request only; no capability was enabled."
        )
        self.export_status.setObjectName("Good")
        self._repolish(self.export_status)

    def _export_physical_request(self) -> None:
        if self.active_report is None or self.active_pack is None or self.workspace is None:
            return
        exported = self.validation_service.export_physical_attestation_request(
            self.active_pack,
            self.active_report,
            self.workspace,
        )
        self.export_status.setText(
            f"Saved physical-test challenge {exported.output_path}  •  SHA-256 "
            f"{exported.sha256[:16]}…  •  independent signed testing is still required."
        )
        self.export_status.setObjectName("Good")
        self._repolish(self.export_status)

    def _render_foundry_blueprint(self, parent: QVBoxLayout) -> None:
        self.active_foundry_revision = None
        self.foundry_inventory = None
        card = QFrame()
        card.setObjectName("DevicePackFoundryCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 15, 18, 15)
        layout.setSpacing(9)
        top = QHBoxLayout()
        copy = QVBoxLayout()
        eyebrow = QLabel("DEVICE PACK FOUNDRY  •  EXPERIMENTAL BLUEPRINT VAULT")
        eyebrow.setObjectName("Eyebrow")
        title = QLabel("Connected identity blueprint")
        title.setObjectName("SectionTitle")
        copy.addWidget(eyebrow)
        copy.addWidget(title)
        top.addLayout(copy, 1)
        badge = QLabel("NO DRAFT")
        badge.setObjectName("Muted")
        top.addWidget(badge)
        layout.addLayout(top)
        if self.workspace is None or self.active_device is None:
            detail = QLabel(
                "Choose a workspace and connect one identified phone to begin a private draft."
            )
            detail.setObjectName("Muted")
            detail.setWordWrap(True)
            layout.addWidget(detail)
            parent.addWidget(card)
            return
        try:
            inventory = self.foundry_service.inspect(
                self.workspace / "device_pack_drafts",
                boundary=self.workspace,
            )
        except ValueError as exc:
            detail = QLabel(f"Foundry inventory stopped safely: {exc}")
            detail.setObjectName("Danger")
            detail.setWordWrap(True)
            layout.addWidget(detail)
            badge.setText("INVENTORY BLOCKED")
            badge.setObjectName("Danger")
            parent.addWidget(card)
            return
        self.foundry_inventory = inventory
        device = self.active_device
        revision = inventory.best_for_identity(
            device.brand or device.manufacturer,
            device.model,
            device.product,
            device.codename,
        )
        self.active_foundry_revision = revision
        if revision is None:
            detail = QLabel(
                f"No experimental blueprint matches {device.display_name}. Prepare one private "
                "model draft, then attach a genuine firmware source and measured partition evidence."
            )
            detail.setObjectName("Muted")
            detail.setWordWrap(True)
            layout.addWidget(detail)
        else:
            title.setText(revision.display_name)
            badge.setText(
                f"{revision.evidenced_lane_count}/{len(revision.lanes)} LANES  •  EXPERIMENTAL"
            )
            badge.setObjectName("Warning")
            revision_copy = QLabel(
                f"Pack lineage {revision.pack_id} v{revision.version}  •  revision "
                f"{revision.sha256[:16]}…  •  "
                f"{'source-bound' if revision.source_bound else 'identity-only'}  •  "
                f"{'sealed DNA attached' if revision.device_dna_attached else 'DNA pending'}  •  "
                "region is never used as the compatibility matcher"
            )
            revision_copy.setObjectName("Muted")
            revision_copy.setWordWrap(True)
            revision_copy.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            layout.addWidget(revision_copy)
            grid = QGridLayout()
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(10)
            for index, lane in enumerate(revision.lanes):
                tile = QFrame()
                tile.setObjectName("FoundryLane")
                tile_layout = QVBoxLayout(tile)
                tile_layout.setContentsMargins(12, 10, 12, 10)
                lane_state = QLabel(lane.state.value.upper())
                lane_state.setObjectName(
                    "Good"
                    if lane.state is FoundryEvidenceState.EVIDENCED
                    else "Warning"
                    if lane.state is FoundryEvidenceState.PARTIAL
                    else "Muted"
                )
                lane_title = QLabel(lane.title)
                lane_title.setObjectName("SectionTitle")
                lane_detail = QLabel(lane.detail)
                lane_detail.setObjectName("Muted")
                lane_detail.setWordWrap(True)
                tile_layout.addWidget(lane_state)
                tile_layout.addWidget(lane_title)
                tile_layout.addWidget(lane_detail)
                grid.addWidget(tile, index // 3, index % 3)
            layout.addLayout(grid)
        inventory_state = QLabel(
            f"FOUNDRY VAULT  •  {inventory.pack_count} experimental Pack lineage(s)  •  "
            f"{len(inventory.revisions)} immutable revision(s)  •  "
            f"{len(inventory.conflicts)} identity conflict(s)  •  "
            f"{len(inventory.issues)} rejected artifact(s)"
        )
        inventory_state.setObjectName(
            "Danger" if inventory.conflicts or inventory.issues else "Good"
        )
        inventory_state.setWordWrap(True)
        layout.addWidget(inventory_state)
        if inventory.conflicts:
            conflict = inventory.conflicts[0]
            conflict_copy = QLabel(
                f"CONFLICT • {conflict.identity_kind} '{conflict.identity}' is claimed by "
                f"{', '.join(conflict.pack_ids)}. {conflict.safest_action}"
            )
            conflict_copy.setObjectName("Danger")
            conflict_copy.setWordWrap(True)
            layout.addWidget(conflict_copy)
        boundary = QLabel(
            "DRAFTS STAY OUTSIDE THE PRODUCTION REGISTRY  •  PUBLICATION AUTHORITY: NONE  •  "
            "BUILD / FLASH / PHONE AUTHORITY: NONE"
        )
        boundary.setObjectName("Muted")
        boundary.setWordWrap(True)
        layout.addWidget(boundary)
        parent.addWidget(card)

    def _export_model_draft(self) -> None:
        if self.active_pack is None or self.active_device is None or self.workspace is None:
            return
        try:
            request = self.draft_service.request_from_device(
                self.active_pack,
                self.active_device,
            )
            exported = self.draft_service.export(
                request,
                self.workspace / "device_pack_drafts",
                boundary=self.workspace,
            )
        except ValueError as exc:
            self.export_status.setText(
                f"Model Pack draft needs attention: {exc}. No capability was enabled."
            )
            self.export_status.setObjectName("Danger")
        else:
            if self.active_pack is not None and self.active_report is not None:
                self._render_pack(self.active_pack, self.active_report)
            self.export_status.setText(
                f"Prepared review-only model draft {exported.output_path}  •  SHA-256 "
                f"{exported.sha256[:16]}…  •  serial excluded  •  execution authority: none."
            )
            self.export_status.setObjectName("Good")
        self._repolish(self.export_status)

    def _export_project_pack_draft(self) -> None:
        source = self._validated_active_project_source()
        if (
            self.active_pack is None
            or self.active_device is None
            or self.workspace is None
            or source is None
        ):
            self.next_action_feedback.setText(
                "EXACT-SOURCE DRAFT STOPPED  •  Reopen the unchanged project with its matching "
                "phone  •  NO BUILD, FLASH, OR PHONE ACTION STARTED"
            )
            self.next_action_feedback.setObjectName("Danger")
            self._repolish(self.next_action_feedback)
            return
        try:
            seed_pack = next(
                (
                    pack
                    for pack in self.registry.packs
                    if pack.pack_id == source.device_pack_id and pack.knowledge_sources
                ),
                self.active_pack,
            )
            request = self.draft_service.request_from_project_source(
                seed_pack,
                self.active_device,
                source,
                self._load_project_source_avb(source),
                (
                    self.active_device_dna
                    if self.active_device_dna is not None
                    and self.active_device_dna.project_id == source.project_id
                    and self.active_device_dna.source_sha256 == source.source_sha256
                    else None
                ),
            )
            exported = self.draft_service.export(
                request,
                self.workspace / "device_pack_drafts",
                boundary=self.workspace,
            )
        except ValueError as exc:
            self.next_action_feedback.setText(
                f"EXACT-SOURCE DRAFT STOPPED  •  {exc}  •  NO BUILD, FLASH, OR PHONE ACTION STARTED"
            )
            self.next_action_feedback.setObjectName("Danger")
        else:
            if self.active_pack is not None and self.active_report is not None:
                self._render_pack(self.active_pack, self.active_report)
            self.next_action_feedback.setText(
                f"EXACT-SOURCE PACK DRAFT READY  •  {exported.output_path}  •  SHA-256 "
                f"{exported.sha256[:16]}…  •  "
                + (
                    "sealed privacy-safe Device DNA attached  •  "
                    if self.active_device_dna is not None
                    and self.active_device_dna.project_id == source.project_id
                    and self.active_device_dna.source_sha256 == source.source_sha256
                    else ""
                )
                + "review required  •  execution authority: none"
            )
            self.next_action_feedback.setObjectName("Good")
        self._repolish(self.next_action_feedback)

    def _load_current_project_draft(
        self,
        source: ProjectSourceRequirements | None,
    ) -> DevicePackDraftReview | None:
        if self.workspace is None or source is None:
            return None
        try:
            return self.draft_service.load_project_draft(
                self.workspace / "device_pack_drafts",
                boundary=self.workspace,
                project_id=source.project_id,
                source_sha256=source.source_sha256,
                blueprint_digest=source.blueprint_digest,
            )
        except ValueError:
            return None

    def _review_project_pack_draft(self) -> None:
        review = self.active_project_draft
        source = self._validated_active_project_source()
        if (
            review is None
            or source is None
            or review.project_id != source.project_id
            or review.source_sha256 != source.source_sha256
            or review.blueprint_digest != source.blueprint_digest
        ):
            self.next_action_handoff_stopped(
                "The prepared draft no longer matches the exact project source"
            )
            return
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Device Atlas • exact-source Pack draft")
        dialog.setIcon(QMessageBox.Icon.Information)
        dialog.setText("This Pack-draft step is complete")
        dialog.setInformativeText(
            f"Build: {review.build_id}\n"
            f"Partitions observed: {review.partition_count}\n"
            f"Source AVB evidence attached: {'yes' if review.source_avb_attached else 'no'}\n"
            f"Draft SHA-256: {review.sha256[:20]}…\n\n"
            "The draft is safely stored and does not need to be created again. The remaining "
            "work is exact flash engineering and physical recovery validation—not another "
            "Guided Setup pass."
        )
        dialog.setDetailedText(
            "Still required before this source can support a governed flash:\n"
            + "\n".join(f"• {item}" for item in review.missing_flash_contracts)
            + "\n\nExecution authority: NONE\nPhone changed: NO"
        )
        guide = dialog.addButton(
            "Open flash-readiness guide",
            QMessageBox.ButtonRole.ActionRole,
        )
        dialog.addButton(QMessageBox.StandardButton.Close)
        dialog.exec()
        if dialog.clickedButton() is guide:
            self.knowledge_article_requested.emit("device-pack-readiness-roadmap")

    def _import_physical_attestation(self) -> None:
        if self.attestation_store is None or self.active_pack is None or self.active_device is None:
            return
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Import signed physical-test evidence",
            "",
            "ROMVERSE evidence (*.romverse *.json);;All files (*)",
        )
        if not selected:
            return
        result = self.attestation_store.import_envelope(self.active_pack, Path(selected))
        if result.report.verified:
            device = self.active_device
            self._render_device(device)
            self.export_status.setText(
                f"Verified and stored {result.stored_path}  •  signer "
                f"{result.report.signer_id}. Remaining Guardian gates still apply."
            )
            self.export_status.setObjectName("Good")
        else:
            self.export_status.setText(f"Evidence rejected: {result.report.reason}")
            self.export_status.setObjectName("Danger")
        self._repolish(self.export_status)

    def _catalog_query_changed(self, _query: str) -> None:
        self._show_installed()

    def _matching_packs(self, query: str) -> tuple[DevicePack, ...]:
        terms = tuple(part for part in query.casefold().split() if part)
        if not terms:
            return self.registry.packs
        matches: list[DevicePack] = []
        for pack in self.registry.packs:
            searchable = " ".join(
                (
                    pack.pack_id,
                    pack.display_name,
                    *pack.manufacturers,
                    *pack.model_patterns,
                    *pack.product_patterns,
                    *(capability.label for capability in pack.capabilities),
                    *(capability.detail for capability in pack.capabilities),
                    *(source.label for source in pack.knowledge_sources),
                    *(source.scope for source in pack.knowledge_sources),
                )
            ).casefold()
            if all(term in searchable for term in terms):
                matches.append(pack)
        return tuple(matches)

    def _official_catalog_matches(self, query: str) -> tuple[DeviceCatalogEntry, ...]:
        if self.device_catalog is None:
            return ()
        return self.device_catalog.search_entries(query, limit=12)

    def _exact_packs_for_official_entry(
        self,
        entry: DeviceCatalogEntry,
    ) -> tuple[DevicePack, ...]:
        """Connect a retail identity only to exact declared local Pack patterns."""

        brand = " ".join(entry.retail_branding.casefold().split())
        identity_values = {
            " ".join(entry.device.casefold().split()),
            " ".join(entry.model.casefold().split()),
        } - {""}
        matches: list[DevicePack] = []
        for pack in self.registry.packs:
            manufacturers = {
                " ".join(value.casefold().split()) for value in pack.manufacturers if value != "*"
            }
            if not manufacturers or (brand and brand not in manufacturers):
                continue
            patterns = (*pack.model_patterns, *pack.product_patterns)
            declared = {
                " ".join(pattern.casefold().split())
                for pattern in patterns
                if not any(token in pattern for token in "*?[")
            }
            if identity_values & declared:
                matches.append(pack)
        return tuple(matches)

    def _show_official_identity(self, entry: DeviceCatalogEntry) -> None:
        """Review one still-current official retail identity and its exact local Packs."""

        if self.device_catalog is None or not self.device_catalog.contains(entry):
            self.identity_catalog_title.setText("Official identity review stopped safely")
            self.identity_catalog_detail.setText(
                "The selected row is no longer present in the current integrity-checked mirror. "
                "Refresh official IDs before reviewing it again. No Device Pack, project, build, "
                "flash, approval, or phone state changed."
            )
            self.identity_catalog_badge.setText("STALE RESULT • ZERO AUTHORITY")
            self.identity_catalog_badge.setObjectName("Danger")
            self._repolish(self.identity_catalog_badge)
            self._show_installed()
            return

        self._clear()
        name = entry.marketing_name or entry.device or entry.model or "Unnamed Android identity"
        header = QFrame()
        header.setObjectName("HeroCard")
        header_layout = QHBoxLayout(header)
        header_copy = QVBoxLayout()
        eyebrow = QLabel("GOOGLE PLAY DEVICE ID  •  VERIFIED LOCAL MIRROR")
        eyebrow.setObjectName("Eyebrow")
        title = QLabel(name)
        title.setObjectName("HeroTitle")
        detail = QLabel(
            f"Retail brand: {entry.retail_branding or 'not listed'}  •  "
            f"Build.DEVICE: {entry.device or 'not listed'}  •  "
            f"Model: {entry.model or 'not listed'}"
        )
        detail.setObjectName("Muted")
        detail.setWordWrap(True)
        detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        boundary = QLabel("RETAIL IDENTITY ONLY  •  BUILD / FLASH / EXECUTION AUTHORITY: NONE")
        boundary.setObjectName("Good")
        boundary.setWordWrap(True)
        header_copy.addWidget(eyebrow)
        header_copy.addWidget(title)
        header_copy.addWidget(detail)
        header_copy.addWidget(boundary)
        header_layout.addLayout(header_copy, 1)
        back = QPushButton("Back to Device Atlas search")
        back.clicked.connect(self._show_installed)
        header_layout.addWidget(back)
        self.body_layout.addWidget(header)

        explanation = QFrame()
        explanation.setObjectName("Card")
        explanation_layout = QVBoxLayout(explanation)
        explanation_title = QLabel("How ROMVERSE uses this identity")
        explanation_title.setObjectName("SectionTitle")
        explanation_copy = QLabel(
            "A connected-device scan independently reads Build.BRAND, Build.DEVICE, and the "
            "reported model, then requires an exact catalog match before using the retail name. "
            "This manual review does not select a phone and cannot promote an official name into "
            "partition knowledge, compile requirements, a build contract, or a flash contract."
        )
        explanation_copy.setObjectName("Muted")
        explanation_copy.setWordWrap(True)
        explanation_layout.addWidget(explanation_title)
        explanation_layout.addWidget(explanation_copy)
        self.body_layout.addWidget(explanation)

        self.official_missing_pack_guide_button = None
        packs = self._exact_packs_for_official_entry(entry)
        packs_title = QLabel(f"Exact local Pack evidence  •  {len(packs)} candidate(s)")
        packs_title.setObjectName("SectionTitle")
        self.body_layout.addWidget(packs_title)
        if not packs:
            missing = QFrame()
            missing.setObjectName("Card")
            missing_layout = QVBoxLayout(missing)
            missing_title = QLabel("No exact Device Pack is declared for this official identity")
            missing_title.setObjectName("Warning")
            missing_copy = QLabel(
                "ROMVERSE can still recognize and diagnose a connected phone, but model-specific "
                "build, compile, recovery, and flash planning stays locked until an "
                "integrity-checked exact Pack supplies those contracts."
            )
            missing_copy.setObjectName("Muted")
            missing_copy.setWordWrap(True)
            missing_layout.addWidget(missing_title)
            missing_layout.addWidget(missing_copy)
            self.official_missing_pack_guide_button = QPushButton("Open missing Device Pack guide")
            self.official_missing_pack_guide_button.setObjectName("Primary")
            self.official_missing_pack_guide_button.setToolTip(
                "Open the exact verified Archives diagnosis for an official identity with no "
                "local Pack. Navigation only; no target, scan, build, approval, flash, network, "
                "or phone action starts."
            )
            self.official_missing_pack_guide_button.clicked.connect(
                lambda: self.knowledge_article_requested.emit("official-device-id-without-pack")
            )
            missing_layout.addWidget(
                self.official_missing_pack_guide_button,
                0,
                Qt.AlignmentFlag.AlignLeft,
            )
            self.body_layout.addWidget(missing)
        for pack in packs:
            card = QFrame()
            card.setObjectName("Card")
            layout = QHBoxLayout(card)
            copy = QVBoxLayout()
            pack_name = QLabel(pack.display_name)
            pack_name.setObjectName("SectionTitle")
            pack_detail = QLabel(
                f"{pack.pack_id}  •  v{pack.version}  •  exact declared model/codename pattern"
            )
            pack_detail.setObjectName("Muted")
            copy.addWidget(pack_name)
            copy.addWidget(pack_detail)
            review = QPushButton("Review exact Pack evidence")
            review.clicked.connect(
                lambda _checked=False, item=pack: self._show_pack_knowledge(item)
            )
            layout.addLayout(copy, 1)
            layout.addWidget(review)
            self.body_layout.addWidget(card)
        self.body_layout.addStretch()

    def _show_installed(self) -> None:
        self._clear()
        self.official_result_buttons.clear()
        self.official_missing_pack_guide_button = None
        query = self.catalog_search.text().strip()
        packs = self._matching_packs(query)
        official_matches = self._official_catalog_matches(query) if query else ()
        if query and self.device_catalog is not None:
            status = self.device_catalog.status()
            official_title = QLabel(
                f"Official Android identities  •  {len(official_matches)} verified result(s) shown"
            )
            official_title.setObjectName("SectionTitle")
            self.body_layout.addWidget(official_title)
            if status.valid and len(query.casefold().strip()) < 2:
                official_note = QLabel(
                    "Type at least two characters to search the verified official ID mirror."
                )
                official_note.setObjectName("Muted")
                self.body_layout.addWidget(official_note)
            elif status.valid and not official_matches:
                official_note = QLabel(
                    "No official retail identity row matches this search. ROMVERSE will not "
                    "infer a device name from a partial or unrelated result."
                )
                official_note.setObjectName("Warning")
                official_note.setWordWrap(True)
                self.body_layout.addWidget(official_note)
            elif not status.valid:
                official_note = QLabel(
                    "Official ID search needs an integrity-checked local mirror. Use Sync "
                    "official IDs above; the search itself never starts a network request."
                )
                official_note.setObjectName("Warning")
                official_note.setWordWrap(True)
                self.body_layout.addWidget(official_note)
            for entry in official_matches:
                card = QFrame()
                card.setObjectName("OfficialIdentityCard")
                layout = QHBoxLayout(card)
                copy = QVBoxLayout()
                name = QLabel(entry.marketing_name or entry.device or entry.model)
                name.setObjectName("SectionTitle")
                detail = QLabel(
                    f"{entry.retail_branding or 'Brand not listed'}  •  "
                    f"Build.DEVICE {entry.device or 'not listed'}  •  "
                    f"Model {entry.model or 'not listed'}"
                )
                detail.setObjectName("Muted")
                detail.setWordWrap(True)
                copy.addWidget(name)
                copy.addWidget(detail)
                badge = QLabel("OFFICIAL ID • BUILD LOCKED")
                badge.setObjectName("Good")
                review = QPushButton("Review identity")
                review.setToolTip(
                    "Revalidates this row against the current mirror, then shows any exact local "
                    "Pack evidence. No device, project, build, flash, or approval is selected."
                )
                review.clicked.connect(
                    lambda _checked=False, item=entry: self._show_official_identity(item)
                )
                layout.addLayout(copy, 1)
                layout.addWidget(badge)
                layout.addWidget(review)
                self.body_layout.addWidget(card)
                self.official_result_buttons.append(review)
        title = QLabel(
            f"Device Atlas catalog  •  {len(packs)} of {len(self.registry.packs)} Pack(s)"
        )
        title.setObjectName("SectionTitle")
        self.body_layout.addWidget(title)
        if not packs:
            empty = QFrame()
            empty.setObjectName("Card")
            empty_layout = QVBoxLayout(empty)
            empty_title = QLabel("No integrity-checked Pack matches this search")
            empty_title.setObjectName("Warning")
            empty_copy = QLabel(
                "Try a manufacturer, model family, codename, capability, or authoritative "
                "source name. ROMVERSE will not invent compatibility from an unknown match."
            )
            empty_copy.setObjectName("Muted")
            empty_copy.setWordWrap(True)
            empty_layout.addWidget(empty_title)
            empty_layout.addWidget(empty_copy)
            self.body_layout.addWidget(empty)
        for pack in packs:
            card = QFrame()
            card.setObjectName("Card")
            layout = QHBoxLayout(card)
            name = QLabel(pack.display_name)
            name.setObjectName("SectionTitle")
            detail = QLabel(
                f"{pack.pack_id}  •  v{pack.version}  •  {len(pack.knowledge_sources)} source(s)"
            )
            detail.setObjectName("Muted")
            valid = QLabel("INTEGRITY VERIFIED")
            valid.setObjectName("Good")
            review = QPushButton("Review Pack evidence")
            review.setToolTip(
                f"Review {pack.display_name}'s declared capabilities, sources, and boundaries. "
                "This is read-only and grants no execution authority."
            )
            review.clicked.connect(
                lambda _checked=False, item=pack: self._show_pack_knowledge(item)
            )
            layout.addWidget(name)
            layout.addWidget(detail, 1)
            layout.addWidget(valid)
            layout.addWidget(review)
            self.body_layout.addWidget(card)
        for issue in self.registry.issues:
            card = QFrame()
            card.setObjectName("Card")
            layout = QHBoxLayout(card)
            name = QLabel(issue.filename)
            detail = QLabel(issue.reason)
            detail.setObjectName("Danger")
            layout.addWidget(name)
            layout.addWidget(detail, 1)
            self.body_layout.addWidget(card)
        self.body_layout.addStretch()

    def _show_pack_knowledge(self, pack: DevicePack) -> None:
        self._clear()
        header = QFrame()
        header.setObjectName("HeroCard")
        header_layout = QHBoxLayout(header)
        header_copy = QVBoxLayout()
        title = QLabel(pack.display_name)
        title.setObjectName("HeroTitle")
        detail = QLabel(f"{pack.pack_id}  •  v{pack.version}  •  SHA-256 {pack.sha256[:16]}…")
        detail.setObjectName("Muted")
        detail.setTextInteractionFlags(
            detail.textInteractionFlags() | Qt.TextInteractionFlag.TextSelectableByMouse
        )
        boundary = QLabel("READ-ONLY KNOWLEDGE  •  EXECUTION AUTHORITY: NONE")
        boundary.setObjectName("Good")
        header_copy.addWidget(title)
        header_copy.addWidget(detail)
        header_copy.addWidget(boundary)
        header_layout.addLayout(header_copy, 1)
        back = QPushButton("Back to catalog")
        back.clicked.connect(self._show_installed)
        header_layout.addWidget(back)
        self.body_layout.addWidget(header)

        identity = QFrame()
        identity.setObjectName("Card")
        identity_layout = QVBoxLayout(identity)
        identity_title = QLabel("Declared identity scope")
        identity_title.setObjectName("SectionTitle")
        identity_copy = QLabel(
            "Manufacturers: "
            + ", ".join(pack.manufacturers)
            + "\nModel patterns: "
            + (", ".join(pack.model_patterns) or "none")
            + "\nProduct / codename patterns: "
            + (", ".join(pack.product_patterns) or "none")
        )
        identity_copy.setObjectName("Muted")
        identity_copy.setWordWrap(True)
        identity_copy.setTextInteractionFlags(
            identity_copy.textInteractionFlags() | Qt.TextInteractionFlag.TextSelectableByMouse
        )
        contract = QLabel(
            "Exact local build contract included"
            if pack.build_contract is not None
            else "No exact local build contract — diagnostics knowledge only"
        )
        contract.setObjectName("Good" if pack.build_contract is not None else "Warning")
        identity_layout.addWidget(identity_title)
        identity_layout.addWidget(identity_copy)
        identity_layout.addWidget(contract)
        self.body_layout.addWidget(identity)

        sources_title = QLabel("Authoritative knowledge sources")
        sources_title.setObjectName("SectionTitle")
        self.body_layout.addWidget(sources_title)
        if not pack.knowledge_sources:
            missing = QLabel("No current external knowledge source is declared for this Pack.")
            missing.setObjectName("Warning")
            self.body_layout.addWidget(missing)
        for source in pack.knowledge_sources:
            card = QFrame()
            card.setObjectName("Card")
            layout = QVBoxLayout(card)
            link = QLabel(
                f'<a style="color:#43DDF2" href="{html.escape(source.url, quote=True)}">'
                f"{html.escape(source.label)}</a>"
            )
            link.setOpenExternalLinks(True)
            link.setObjectName("SectionTitle")
            source_detail = QLabel(
                f"{source.authority}  •  {source.scope}  •  checked {source.verified_on}"
            )
            source_detail.setObjectName("Warning" if source.is_stale() else "Muted")
            source_detail.setWordWrap(True)
            layout.addWidget(link)
            layout.addWidget(source_detail)
            self.body_layout.addWidget(card)

        capabilities_title = QLabel("Declared capabilities and boundaries")
        capabilities_title.setObjectName("SectionTitle")
        self.body_layout.addWidget(capabilities_title)
        for capability in pack.capabilities:
            card = QFrame()
            card.setObjectName("Card")
            layout = QHBoxLayout(card)
            copy = QVBoxLayout()
            name = QLabel(capability.label)
            name.setObjectName("SectionTitle")
            description = QLabel(
                f"{capability.detail}\nScope: {capability.scope.replace('_', ' ')}"
            )
            description.setObjectName("Muted")
            description.setWordWrap(True)
            badge = QLabel(capability.status.value.upper())
            badge.setObjectName(
                "Good"
                if capability.status is CapabilityStatus.SUPPORTED
                else "Warning"
                if capability.status is CapabilityStatus.LIMITED
                else "Muted"
            )
            copy.addWidget(name)
            copy.addWidget(description)
            layout.addLayout(copy, 1)
            layout.addWidget(badge)
            self.body_layout.addWidget(card)
        if pack.notes:
            notes = QFrame()
            notes.setObjectName("Card")
            notes_layout = QVBoxLayout(notes)
            notes_title = QLabel("Pack boundaries")
            notes_title.setObjectName("SectionTitle")
            notes_copy = QLabel("\n".join(f"• {note}" for note in pack.notes))
            notes_copy.setObjectName("Muted")
            notes_copy.setWordWrap(True)
            notes_layout.addWidget(notes_title)
            notes_layout.addWidget(notes_copy)
            self.body_layout.addWidget(notes)
        self.body_layout.addStretch()

    def _clear(self) -> None:
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
