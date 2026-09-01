from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from romverse.device.catalog import (
    DeviceCatalogMatch,
    DeviceCatalogStatus,
    GooglePlayDeviceCatalog,
)
from romverse.device.models import AndroidDevice
from romverse.device_packs.attestations import DevicePackAttestationStore
from romverse.device_packs.drafts import DevicePackDraftService
from romverse.device_packs.models import CapabilityStatus, DevicePack
from romverse.device_packs.registry import DevicePackRegistry
from romverse.device_packs.source_audit import export_source_audit, summarize_sources
from romverse.device_packs.validation import (
    DevicePackNextAction,
    DevicePackValidationReport,
    DevicePackValidationService,
    ValidationState,
)


class DevicePacksCenter(QWidget):
    rom_studio_requested = Signal()
    catalog_refresh_requested = Signal()
    next_action_requested = Signal(str, str, str, str)
    toolchain_requested = Signal(str, str, str)
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
        self.draft_service = DevicePackDraftService()
        self.active_report: DevicePackValidationReport | None = None
        self.active_next_action: DevicePackNextAction | None = None
        self.active_pack: DevicePack | None = None
        self.active_device: AndroidDevice | None = None
        self.validation_rows: dict[str, QFrame] = {}
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
            "Search Device Atlas by brand, model, codename, capability, or source…"
        )
        self.catalog_search.setToolTip(
            "Searches only ROMVERSE's integrity-checked local Pack catalog. It performs no "
            "network request and grants no device authority."
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
        self.continue_button.clicked.connect(self.rom_studio_requested.emit)
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
            return None
        match = self.device_catalog.match(device)
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

        contract = pack.build_contract
        if contract is not None:
            toolchain = QFrame()
            toolchain.setObjectName("DiagnosticHandoffBar")
            toolchain_layout = QVBoxLayout(toolchain)
            toolchain_layout.setContentsMargins(16, 13, 16, 13)
            toolchain_layout.setSpacing(8)
            toolchain_top = QHBoxLayout()
            toolchain_copy = QVBoxLayout()
            toolchain_eyebrow = QLabel("EXACT BUILD TOOLCHAIN  •  DECLARED BY THIS DEVICE PACK")
            toolchain_eyebrow.setObjectName("Eyebrow")
            self.toolchain_title = QLabel(
                f"{len(contract.required_tools)} host requirements for {pack.display_name}"
            )
            self.toolchain_title.setObjectName("SectionTitle")
            self.toolchain_detail = QLabel(
                " • ".join(contract.required_tools)
                + "\nForge Arsenal can verify and prepare only this ordered requirement set. "
                "Tool availability is separate from Device Pack build readiness, Guardian "
                "approval, and the independently locked flash contract."
            )
            self.toolchain_detail.setObjectName("Muted")
            self.toolchain_detail.setWordWrap(True)
            toolchain_copy.addWidget(toolchain_eyebrow)
            toolchain_copy.addWidget(self.toolchain_title)
            toolchain_copy.addWidget(self.toolchain_detail)
            toolchain_top.addLayout(toolchain_copy, 1)
            toolchain_badge = QLabel("BUILD TOOLS ONLY  •  FLASH AUTHORITY NONE")
            toolchain_badge.setObjectName("Warning")
            toolchain_top.addWidget(toolchain_badge)
            self.toolchain_button = QPushButton("Inspect exact build tools")
            self.toolchain_button.setObjectName("Primary")
            self.toolchain_button.setToolTip(
                "Carry this exact report digest, Pack hash, and declared host-tool set into "
                "Forge Arsenal. No installer, build, approval, or device-changing operation "
                "starts automatically."
            )
            self.toolchain_button.clicked.connect(self._request_toolchain)
            toolchain_top.addWidget(self.toolchain_button)
            toolchain_layout.addLayout(toolchain_top)
            self.toolchain_feedback = QLabel("")
            self.toolchain_feedback.setObjectName("Muted")
            self.toolchain_feedback.setWordWrap(True)
            toolchain_layout.addWidget(self.toolchain_feedback)
            roadmap_layout.addWidget(toolchain)

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

    def next_action_handoff_stopped(self, reason: str) -> None:
        """Keep a refused readiness handoff visible without relying on a toast."""

        if not hasattr(self, "next_action_feedback"):
            return
        self.next_action_feedback.setText(
            f"NEXT ACTION STOPPED  •  {reason}  •  NO WORKER OR PHONE ACTION STARTED"
        )
        self.next_action_feedback.setObjectName("Danger")
        self._repolish(self.next_action_feedback)

    def _request_toolchain(self) -> None:
        report = self.active_report
        pack = self.active_pack
        if report is None or pack is None or pack.build_contract is None:
            return
        self.toolchain_requested.emit(pack.pack_id, pack.sha256, report.report_digest)

    def toolchain_handoff_stopped(self, reason: str) -> None:
        """Keep a refused exact-toolchain handoff visible in Device Atlas."""

        if not hasattr(self, "toolchain_feedback"):
            return
        self.toolchain_feedback.setText(
            f"EXACT TOOLCHAIN HANDOFF STOPPED  •  {reason}  •  NO INSTALL, BUILD, OR PHONE ACTION STARTED"
        )
        self.toolchain_feedback.setObjectName("Danger")
        self._repolish(self.toolchain_feedback)

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

    def _show_installed(self) -> None:
        self._clear()
        query = self.catalog_search.text().strip()
        packs = self._matching_packs(query)
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
