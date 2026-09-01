from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
from romverse.device.models import AndroidDevice
from romverse.device_packs.attestations import DevicePackAttestationStore
from romverse.device_packs.drafts import DevicePackDraftService
from romverse.device_packs.models import CapabilityStatus, DevicePack
from romverse.device_packs.registry import DevicePackRegistry
from romverse.device_packs.requirements import (
    DeviceRequirementsBlueprint,
    DeviceRequirementsService,
    RequirementState,
)
from romverse.device_packs.source_audit import export_source_audit, summarize_sources
from romverse.device_packs.validation import (
    DevicePackNextAction,
    DevicePackValidationReport,
    DevicePackValidationService,
    ValidationState,
)


class DevicePacksCenter(QWidget):
    rom_studio_requested = Signal(str, str)
    catalog_refresh_requested = Signal()
    knowledge_article_requested = Signal(str)
    next_action_requested = Signal(str, str, str, str)
    requirement_requested = Signal(str, str, str, str)
    readiness_changed = Signal(object)

    def __init__(
        self,
        registry: DevicePackRegistry,
        workspace: Path | None = None,
        attestation_store: DevicePackAttestationStore | None = None,
        device_catalog: GooglePlayDeviceCatalog | None = None,
        online_catalog_enabled: bool = True,
    ) -> None:
        super().__init__()
        self.registry = registry
        self.workspace = workspace
        self.attestation_store = attestation_store
        self.device_catalog = device_catalog
        self.online_catalog_enabled = online_catalog_enabled
        self.validation_service = DevicePackValidationService()
        self.requirements_service = DeviceRequirementsService()
        self.draft_service = DevicePackDraftService()
        self.active_report: DevicePackValidationReport | None = None
        self.active_next_action: DevicePackNextAction | None = None
        self.active_requirements: DeviceRequirementsBlueprint | None = None
        self.active_catalog_match: DeviceCatalogMatch | None = None
        self.active_pack: DevicePack | None = None
        self.active_device: AndroidDevice | None = None
        self.validation_rows: dict[str, QFrame] = {}
        self.requirement_buttons: dict[str, QPushButton] = {}
        self.requirement_badges: dict[str, QLabel] = {}
        self.official_result_buttons: list[QPushButton] = []
        self.official_missing_pack_guide_button: QPushButton | None = None
        self.devices: list[AndroidDevice] = []
        self.source_summary = summarize_sources(registry)

        page = QVBoxLayout(self)
        page.setContentsMargins(30, 26, 30, 30)
        page.setSpacing(18)
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
        self.continue_button = QPushButton("Continue to ROM Studio")
        self.continue_button.setObjectName("Primary")
        self.continue_button.setVisible(False)
        self.continue_button.setToolTip(
            "Open ROM Studio. Genesis Sequence will continue source and safety checks automatically."
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

        self.body = QScrollArea()
        self.body.setWidgetResizable(True)
        self.body_content = QWidget()
        self.body_content.setObjectName("ScrollContent")
        self.body_layout = QVBoxLayout(self.body_content)
        self.body_layout.setContentsMargins(0, 0, 6, 0)
        self.body_layout.setSpacing(12)
        self.body.setWidget(self.body_content)
        page.addWidget(self.body, 1)

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
            self._repolish(self.pack_badge)
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
                if self.active_catalog_match is not None
                and self.active_catalog_match.matched
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
        """Explain the exact Studio project's Pack relationship without guessing a phone."""

        normalized_id = str(project_id).strip()
        clean_name = " ".join(str(project_name).replace("\x00", "").split())[:100]
        normalized_pack = str(pack_id).strip()
        source = str(source_sha256).strip().casefold()
        source_label = source[:16] + "…" if source else "not imported"
        if not normalized_id or not clean_name:
            return False
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
        if not normalized_pack:
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
            detail + " NO SCAN, BUILD, APPROVAL, FLASH, OR PHONE ACTION STARTED.",
            badge,
            ready=ready,
            eyebrow="ROM STUDIO HANDOFF  •  EXACT PROJECT / DEVICE PACK CONTRACT",
        )
        if ready and hasattr(self, "requirements_blueprint_frame"):
            self.body.ensureWidgetVisible(self.requirements_blueprint_frame, 0, 24)
        return True

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
            self._render_device(self.devices[index])

    def _render_device(self, device: AndroidDevice) -> None:
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
                False,
            )
        elif generic:
            self._set_guidance(
                "Phone connected — model-specific build support is limited",
                "ROMVERSE can run safe generic diagnostics, but this match does not contain an "
                "exact build contract. ROM building and device-changing work remain locked.",
                "Warning",
                False,
            )
        else:
            self._set_guidance(
                "Phone recognized — safe diagnostics are ready",
                "ROMVERSE has model-specific knowledge, but not a complete verified build contract "
                "for this exact firmware. The evidence roadmap below explains what is still needed.",
                "Warning",
                False,
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
        self.active_next_action = self.validation_service.next_safe_action(report)
        roadmap = QFrame()
        roadmap.setObjectName("Card")
        roadmap_layout = QVBoxLayout(roadmap)
        roadmap_layout.setContentsMargins(18, 16, 18, 16)
        roadmap_layout.setSpacing(10)
        roadmap_header = QHBoxLayout()
        roadmap_copy = QVBoxLayout()
        roadmap_title = QLabel("MODEL-SPECIFIC VALIDATION ROADMAP")
        roadmap_title.setObjectName("Eyebrow")
        roadmap_description = QLabel(
            f"Evidence contract for {report.model} / {report.codename}. "
            "Checks measure readiness; they never grant execution authority."
        )
        roadmap_description.setObjectName("Muted")
        roadmap_description.setWordWrap(True)
        roadmap_copy.addWidget(roadmap_title)
        roadmap_copy.addWidget(roadmap_description)
        roadmap_header.addLayout(roadmap_copy, 1)
        build_state = QLabel(
            f"{report.passed_count} / {len(report.checks)} VERIFIED  •  "
            + ("BUILD READY" if report.build_contract_ready else "BUILD LOCKED")
            + "  •  "
            + ("FLASH CONTRACT READY" if report.flash_contract_ready else "FLASH LOCKED")
        )
        build_state.setObjectName(
            "Good"
            if report.flash_contract_ready
            else "Warning"
            if report.build_contract_ready
            else "Danger"
        )
        roadmap_header.addWidget(build_state)
        roadmap_layout.addLayout(roadmap_header)

        next_action = QFrame()
        next_action.setObjectName("DiagnosticHandoffBar")
        next_layout = QHBoxLayout(next_action)
        next_layout.setContentsMargins(16, 13, 16, 13)
        next_copy = QVBoxLayout()
        next_eyebrow = QLabel("NEXT SAFE ACTION  •  DETERMINISTIC FROM CURRENT EVIDENCE")
        next_eyebrow.setObjectName("Eyebrow")
        self.next_action_title = QLabel(self.active_next_action.title)
        self.next_action_title.setObjectName("SectionTitle")
        self.next_action_detail = QLabel(self.active_next_action.detail)
        self.next_action_detail.setObjectName("Muted")
        self.next_action_detail.setWordWrap(True)
        next_copy.addWidget(next_eyebrow)
        next_copy.addWidget(self.next_action_title)
        next_copy.addWidget(self.next_action_detail)
        next_layout.addLayout(next_copy, 1)
        scope = self.active_next_action.scope
        self.next_action_badge = QLabel(
            "READY • GUARDIAN ACTIVE"
            if scope == "ready"
            else f"{scope.upper()} GATE • ZERO AUTHORITY"
        )
        self.next_action_badge.setObjectName(
            "Good" if scope == "ready" else "Danger" if scope == "build" else "Warning"
        )
        next_layout.addWidget(self.next_action_badge)
        self.next_action_button = QPushButton(self.active_next_action.button_label)
        self.next_action_button.setObjectName("Primary")
        self.next_action_button.setToolTip(
            "Opens the exact ROMVERSE page or verified guide selected from this current "
            "readiness report. It starts no worker, approval, build, or phone action."
        )
        self.next_action_button.clicked.connect(self._request_next_action)
        next_layout.addWidget(self.next_action_button)
        roadmap_layout.addWidget(next_action)
        self.next_action_feedback = QLabel("")
        self.next_action_feedback.setObjectName("Muted")
        self.next_action_feedback.setWordWrap(True)
        roadmap_layout.addWidget(self.next_action_feedback)

        self.active_requirements = self.requirements_service.assess(
            pack,
            report,
            self.active_catalog_match,
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
        )
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
        detail = QLabel(
            f"Bound to {blueprint.model} / {blueprint.codename}  •  Pack "
            f"{blueprint.pack_id}  •  SHA-256 {blueprint.pack_sha256[:12]}…"
        )
        detail.setObjectName("Muted")
        detail.setWordWrap(True)
        copy.addWidget(eyebrow)
        copy.addWidget(title)
        copy.addWidget(detail)
        header.addLayout(copy, 1)
        digest = QLabel(f"REPORT {blueprint.report_digest[:12]}…  •  ZERO AUTHORITY")
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
        try:
            return self.requirements_service.assess(
                pack,
                report,
                self.active_catalog_match,
            )
        except ValueError:
            return None

    def _request_requirement(self, lane_id: str) -> None:
        blueprint = self.current_requirements()
        if blueprint is None:
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
            self.export_status.setText(
                f"Prepared review-only model draft {exported.output_path}  •  SHA-256 "
                f"{exported.sha256[:16]}…  •  serial excluded  •  execution authority: none."
            )
            self.export_status.setObjectName("Good")
        self._repolish(self.export_status)

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
                " ".join(value.casefold().split())
                for value in pack.manufacturers
                if value != "*"
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
        packs_title = QLabel(
            f"Exact local Pack evidence  •  {len(packs)} candidate(s)"
        )
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
            self.official_missing_pack_guide_button = QPushButton(
                "Open missing Device Pack guide"
            )
            self.official_missing_pack_guide_button.setObjectName("Primary")
            self.official_missing_pack_guide_button.setToolTip(
                "Open the exact verified Archives diagnosis for an official identity with no "
                "local Pack. Navigation only; no target, scan, build, approval, flash, network, "
                "or phone action starts."
            )
            self.official_missing_pack_guide_button.clicked.connect(
                lambda: self.knowledge_article_requested.emit(
                    "official-device-id-without-pack"
                )
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
