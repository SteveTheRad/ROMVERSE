from __future__ import annotations

import re
import socket
from dataclasses import replace
from datetime import UTC, datetime
from math import ceil
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from romverse.ascension.companion import AscensionCompanionStatus
from romverse.companion.pairing import PairingCode, create_pairing_code
from romverse.companion.raw_terminal import RawTerminalFeed
from romverse.companion.telemetry import (
    CompanionTelemetry,
    DeviceDnaCapabilityTelemetry,
    LiveConsoleTelemetryEvent,
    RawTerminalTelemetryRecord,
)
from romverse.companion.transfers import (
    CompanionTransferError,
    CompanionTransferKind,
    CompanionTransferOffer,
    CompanionTransferPreview,
    CompanionTransferService,
)
from romverse.companion.transport import CompanionTransport
from romverse.companion.usb_assist import UsbPairingAssistPlan, UsbPairingAssistService
from romverse.device.dna import CapabilityState, DeviceDnaProfile
from romverse.device.models import AndroidDevice, DeviceState
from romverse.nexus.events import (
    LiveConsoleEventStore,
    LiveConsoleStoreError,
    MissionConfidence,
    MissionState,
)
from romverse.nexus.planning import NexusPlan, NexusPlanStatus, RouteStageState
from romverse.ui.background import ManagedRunnable, start_background


class _CompanionTransferSignals(QObject):
    completed = Signal(object)
    failed = Signal(str)


class _CompanionTransferWorker(ManagedRunnable):
    def __init__(self, operation) -> None:
        super().__init__()
        self.operation = operation
        self.signals = _CompanionTransferSignals()

    @Slot()
    def execute(self) -> None:
        try:
            self.signals.completed.emit(self.operation())
        except Exception as exc:  # converted to a bounded visible transfer failure
            self.signals.failed.emit(str(exc)[:800])


class CompanionCenter(QWidget):
    remote_snapshot_updated = Signal(object)

    def __init__(
        self,
        live_console_store: LiveConsoleEventStore | None = None,
        raw_terminal_feed: RawTerminalFeed | None = None,
        workspace: Path | None = None,
        usb_pairing_service: UsbPairingAssistService | None = None,
    ) -> None:
        super().__init__()
        self._pairing: PairingCode | None = None
        self._approved = False
        self._approved_restored = False
        self._usb_ready = False
        self._usb_serial = ""
        self._usb_companion_installed = False
        self._usb_auto_approve = False
        self._usb_assist_plan: UsbPairingAssistPlan | None = None
        self._usb_pairing_service = usb_pairing_service
        self._last_remote_capture = 0
        self._pending_announced = False
        self._telemetry = CompanionTelemetry()
        self._live_console_store = live_console_store
        self._raw_terminal_feed = raw_terminal_feed
        self._nexus_plan: NexusPlan | None = None
        self._transfer_worker: _CompanionTransferWorker | None = None
        self.transfer_service: CompanionTransferService | None = None
        self._transfer_availability_error = ""
        if workspace is not None:
            try:
                self.transfer_service = CompanionTransferService(workspace)
            except CompanionTransferError as exc:
                self._transfer_availability_error = str(exc)
        identity_root = workspace / "config" / "companion-link" if workspace is not None else None
        self.transport = CompanionTransport(
            lambda: self._pairing,
            self._telemetry_snapshot,
            identity_root,
            self.transfer_service,
        )
        self._approved = self.transport.approved
        self._approved_restored = self._approved
        if self._approved and not self.transport.start():
            self._approved = False
            self._approved_restored = False
        self._record_link_availability()
        application = QApplication.instance()
        if application is not None:
            application.aboutToQuit.connect(self.shutdown)
        self._expiry_timer = QTimer(self)
        self._expiry_timer.setInterval(1000)
        self._expiry_timer.timeout.connect(self._update_expiry)
        self._remote_timer = QTimer(self)
        self._remote_timer.setInterval(1000)
        self._remote_timer.timeout.connect(self._update_remote_snapshot)
        self._remote_timer.start()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("CompanionScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("ScrollContent")
        page = QVBoxLayout(content)
        page.setContentsMargins(30, 26, 30, 30)
        page.setSpacing(16)
        self.scroll.setWidget(content)
        root.addWidget(self.scroll)
        eyebrow = QLabel("ROMVERSE LINK  •  SECURE LOCAL PAIRING")
        eyebrow.setObjectName("Eyebrow")
        title = QLabel("ROMVERSE Link")
        title.setObjectName("Title")
        subtitle = QLabel(
            "Pair the Android sidekick with this desktop workspace using a short-lived one-time code."
        )
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        page.addWidget(eyebrow)
        page.addWidget(title)
        page.addWidget(subtitle)
        self.device_status = QLabel("Desktop device link: waiting for a read-only scan")
        self.device_status.setObjectName("Muted")
        page.addWidget(self.device_status)
        if self.transport.running:
            network_text = (
                f"Encrypted pairing endpoint: https://{self._local_address()}:{self.transport.port}"
                "  •  TLS 1.2+  •  same trusted network required"
            )
        elif self.transport.available:
            network_text = "Link endpoint idle  •  Choose Generate wireless code to start."
        else:
            network_text = "Wireless pairing unavailable on this computer  •  USB read-only features remain active"
        self.network_status = QLabel(network_text)
        self.network_status.setObjectName("Muted")
        self.network_status.setWordWrap(True)
        page.addWidget(self.network_status)
        self.identity_status = QLabel(
            (
                "LINK SAFETY CODE\n"
                f"{self.transport.safety_code}\n"
                "Compare this code with Companion before approving.\n"
                f"Certificate SHA-256: {self.transport.certificate_sha256}"
            )
            if self.transport.available
            else "LINK SAFETY CODE\nUnavailable until encrypted wireless Link is restored."
        )
        self.identity_status.setObjectName("LinkIdentityStatus")
        self.identity_status.setWordWrap(True)
        self.identity_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.identity_status.setToolTip(
            "The PC and phone must show the same safety code. A mismatch can mean you discovered the wrong computer or the network path was intercepted."
        )
        page.addWidget(self.identity_status)
        card = QFrame()
        card.setObjectName("CompanionPairingCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 24, 24, 24)
        self.state = QLabel("Not paired")
        self.state.setObjectName("HeroTitle")
        self.instructions = QLabel(
            "Generate a code, then enter it in ROMVERSE Companion on your Android phone."
        )
        self.instructions.setObjectName("Muted")
        self.instructions.setWordWrap(True)
        self.code = QLabel("------")
        self.code.setObjectName("LinkPairingCode")
        self.code.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.expiry = QLabel("Codes expire after 10 minutes and are never reused.")
        self.expiry.setObjectName("Muted")
        self.expiry.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.state)
        layout.addWidget(self.instructions)
        layout.addWidget(self.code)
        layout.addWidget(self.expiry)
        self.summary = QLabel("No phone summary imported yet.")
        self.summary.setObjectName("Muted")
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.summary)
        self.remote_summary = QLabel(
            "LIVE COMPANION HEALTH\nWaiting for an authenticated phone snapshot."
        )
        self.remote_summary.setObjectName("CompanionHealthCard")
        self.remote_summary.setWordWrap(True)
        self.remote_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.remote_summary.setToolTip(
            "A paired phone may share battery, storage, memory, Android version, and a local health score. "
            "ROMVERSE never requests its serial, IMEI, accounts, files, or app list through this channel."
        )
        layout.addWidget(self.remote_summary)
        self.usb_pair = QPushButton("Pair connected phone with USB assist")
        self.usb_pair.setObjectName("Primary")
        self.usb_pair.setMinimumHeight(36)
        self.usb_pair.setEnabled(False)
        self.usb_pair.setToolTip(
            "Connect and authorize one phone by USB. The phone must still confirm the matching safety code."
        )
        self.usb_pair.clicked.connect(self.pair_connected_usb)
        self.generate = QPushButton("Generate wireless code")
        self.generate.setObjectName("Primary")
        self.generate.setMinimumHeight(36)
        self.generate.setEnabled(self.transport.available)
        if not self.transport.available:
            self.generate.setToolTip(
                "This environment denied ROMVERSE permission to open a local pairing endpoint."
            )
        self.generate.clicked.connect(self.generate_code)
        self.copy_button = QPushButton("Copy code")
        self.copy_button.setMinimumHeight(36)
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(self.copy_code)
        self.approve = QPushButton("Approve device")
        self.approve.setObjectName("Primary")
        self.approve.setMinimumHeight(36)
        self.approve.setEnabled(False)
        self.approve.setToolTip(
            "Approve only after the six-digit code was entered and the Link safety code matches on both screens."
        )
        self.approve.clicked.connect(self.approve_device)
        self.safety_confirm = QCheckBox(
            "I confirmed the Link safety code matches on the PC and phone"
        )
        self.safety_confirm.setEnabled(False)
        self.safety_confirm.setToolTip(
            "This comparison binds the one-time pairing request to this PC's exact TLS certificate."
        )
        self.safety_confirm.toggled.connect(self._update_approval_button)
        self.reset_link = QPushButton("Reset wireless pairing")
        self.reset_link.setMinimumHeight(36)
        self.reset_link.setEnabled(False)
        self.reset_link.setToolTip(
            "Immediately revoke the remembered wireless session and pending handoff offers on this computer. USB evidence and original files are not changed."
        )
        self.reset_link.clicked.connect(self.reset_pairing)
        import_summary = QPushButton("Import phone summary")
        import_summary.setMinimumHeight(36)
        import_summary.setToolTip(
            "Read a ROMVERSE health summary from the clipboard. This is display-only and never executes commands."
        )
        import_summary.clicked.connect(self.import_summary)
        start_actions = QHBoxLayout()
        start_actions.setSpacing(10)
        start_actions.addWidget(self.usb_pair, 1)
        start_actions.addWidget(self.generate, 1)
        layout.addLayout(start_actions)

        approval_bar = QFrame()
        approval_bar.setObjectName("PairingApprovalBar")
        approval_layout = QHBoxLayout(approval_bar)
        approval_layout.setContentsMargins(13, 9, 10, 9)
        approval_layout.addWidget(self.safety_confirm, 1)
        approval_layout.addWidget(self.approve)
        layout.addWidget(approval_bar)

        supporting_actions = QHBoxLayout()
        supporting_actions.setSpacing(10)
        supporting_actions.addWidget(self.copy_button)
        supporting_actions.addWidget(import_summary)
        supporting_actions.addStretch()
        supporting_actions.addWidget(self.reset_link)
        layout.addLayout(supporting_actions)
        page.addWidget(card)

        transfer_card = QFrame()
        transfer_card.setObjectName("CompanionTransferCard")
        transfer_layout = QVBoxLayout(transfer_card)
        transfer_layout.setContentsMargins(22, 20, 22, 20)
        transfer_layout.setSpacing(9)
        transfer_eyebrow = QLabel("SECURE HANDOFF  •  DESKTOP ↔ COMPANION")
        transfer_eyebrow.setObjectName("Eyebrow")
        transfer_title = QLabel("Send verified files without surrendering control")
        transfer_title.setObjectName("HeroTitle")
        transfer_copy = QLabel(
            "Offer an APK, report, recovery capsule, emergency guide, or approved package to "
            "this trusted phone. Companion verifies the exact fingerprint and asks where to "
            "save it. Nothing installs, opens, flashes, or executes automatically."
        )
        transfer_copy.setObjectName("Muted")
        transfer_copy.setWordWrap(True)
        self.transfer_status = QLabel("Pair Companion to open the encrypted handoff bridge.")
        self.transfer_status.setObjectName("CompanionTransferStatus")
        self.transfer_status.setWordWrap(True)
        self.transfer_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.transfer_button = QPushButton("Choose file for Companion")
        self.transfer_button.setObjectName("Primary")
        self.transfer_button.setMinimumHeight(38)
        self.transfer_button.setEnabled(False)
        self.transfer_button.clicked.connect(self.choose_companion_transfer)
        self.transfer_clear = QPushButton("Revoke pending handoffs")
        self.transfer_clear.setMinimumHeight(38)
        self.transfer_clear.setEnabled(False)
        self.transfer_clear.clicked.connect(self.revoke_companion_transfers)
        transfer_actions = QHBoxLayout()
        transfer_actions.setSpacing(10)
        transfer_actions.addWidget(self.transfer_button, 1)
        transfer_actions.addWidget(self.transfer_clear)
        transfer_layout.addWidget(transfer_eyebrow)
        transfer_layout.addWidget(transfer_title)
        transfer_layout.addWidget(transfer_copy)
        transfer_layout.addWidget(self.transfer_status)
        transfer_layout.addLayout(transfer_actions)
        page.addWidget(transfer_card)
        boundary = QLabel(
            "Guardian boundary  •  pairing grants telemetry and download-only handoff access; it cannot approve or execute device-changing operations."
        )
        boundary.setObjectName("Warning")
        boundary.setWordWrap(True)
        page.addWidget(boundary)
        page.addStretch()
        if self._approved:
            self._render_approved_state(restored=True)
        else:
            self._refresh_transfer_state()

    def set_device_snapshot(
        self,
        devices: list[AndroidDevice],
        *,
        observed_devices: list[AndroidDevice] | None = None,
        scan_error: str = "",
    ) -> None:
        """Reflect selected authority separately from read-only USB detection."""

        self._sync_approved_state()
        observed = list(devices if observed_devices is None else observed_devices)
        device = devices[0] if devices else None
        if device is None:
            if scan_error.strip():
                self.device_status.setText(
                    "Desktop device link: USB scan unavailable  •  Device Engine is retrying"
                )
            elif len(observed) > 1:
                self.device_status.setText(
                    f"Desktop device link: {len(observed)} USB devices detected  •  choose one in Device Center"
                )
            elif observed:
                self.device_status.setText(
                    "Desktop device link: USB device detected  •  select it in Device Center"
                )
            elif self._approved:
                self.device_status.setText(
                    "Desktop device link: wireless Companion active  •  USB is disconnected"
                )
            else:
                self.device_status.setText(
                    "Desktop device link: no USB device detected  •  wireless pairing remains available"
                )
            self._usb_ready = False
            self._usb_serial = ""
            self._usb_companion_installed = False
            self._update_usb_assist_button()
            if self._approved:
                self._render_approved_state(restored=self._approved_restored)
            elif not self._pairing_code_active():
                self.state.setText("Not paired")
                self.instructions.setText(
                    "Generate a code, then enter it in ROMVERSE Companion on your Android phone."
                )
                self.generate.setEnabled(self.transport.available)
            return
        if device.state is not DeviceState.DEVICE:
            if device.state is DeviceState.UNAUTHORIZED:
                state = "authorization required"
                instruction = (
                    "Unlock the phone and approve this computer's USB debugging fingerprint, "
                    "then refresh the read-only scan."
                )
            elif device.state is DeviceState.OFFLINE:
                state = "ADB offline"
                instruction = (
                    "ADB can see the phone but cannot read it. Reconnect USB or restart ADB, then "
                    "refresh the scan."
                )
            elif device.is_fastboot:
                state = f"{device.state.value} mode"
                instruction = (
                    "The phone is detected outside normal Android. Start Android before using "
                    "Companion telemetry."
                )
            elif device.state in {DeviceState.RECOVERY, DeviceState.SIDELOAD}:
                state = f"{device.state.value} mode"
                instruction = (
                    "The phone is detected outside normal Android. Return to Android before using "
                    "Companion telemetry."
                )
            else:
                state = "connection mode unknown"
                instruction = (
                    "Reconnect the phone in normal Android with USB debugging enabled, then "
                    "refresh the scan."
                )
            self.device_status.setText(
                f"Desktop device link: {device.display_name} detected  •  {state}"
            )
            self._usb_ready = False
            self._usb_serial = ""
            self._usb_companion_installed = False
            self._update_usb_assist_button()
            if self._approved:
                self._render_approved_state(restored=self._approved_restored)
            elif not self._pairing_code_active():
                self.state.setText(f"USB detected • {state}")
                self.instructions.setText(instruction)
                self.generate.setEnabled(self.transport.available)
            return
        companion = "installed" if device.companion_installed else "not installed"
        self.device_status.setText(
            f"Desktop device link: {device.display_name}  •  Companion {companion}"
        )
        self._telemetry = replace(
            self._telemetry,
            captured_at=datetime.now(UTC).isoformat(),
            battery_percent=device.battery_percent,
            storage_used_bytes=device.storage.used_bytes,
            storage_total_bytes=device.storage.total_bytes,
            guardian_active=True,
        )
        self._usb_ready = True
        self._usb_serial = device.serial
        self._usb_companion_installed = device.companion_installed
        self._update_usb_assist_button()
        if self._approved:
            self._render_approved_state(restored=self._approved_restored)
        elif not self._pairing_code_active():
            self.state.setText("USB connected • wireless Link not paired")
            self.instructions.setText(
                "USB supplies Desktop with read-only device evidence. Encrypted Companion Link is separate; "
                "generate a wireless code for the phone's live view."
            )
            self.generate.setEnabled(self.transport.available)

    def set_ascension_status(self, status: AscensionCompanionStatus) -> None:
        """Publish bounded root status; never commands, full hashes, paths, or approvals."""

        self._telemetry = replace(
            self._telemetry,
            captured_at=datetime.now(UTC).isoformat(),
            ascension_state=status.state,
            ascension_project=status.project_name,
            ascension_method=status.method,
            ascension_target_partition=status.target_partition,
            ascension_blocker_count=status.blocker_count,
            ascension_phone_changed=False,
            ascension_execution_authority="none",
            ascension_stage_number=status.stage_number,
            ascension_stage_title=status.stage_title,
            ascension_next_action=status.next_action,
            ascension_why=status.why,
            ascension_romverse_action=status.romverse_action,
            ascension_manager_state=status.manager_state,
            ascension_manager_repository=status.manager_repository,
            ascension_manager_tag=status.manager_tag,
            ascension_manager_asset=status.manager_asset,
            ascension_manager_sha256_ref=status.manager_sha256_ref,
        )

    def set_device_dna(
        self,
        profile: DeviceDnaProfile | None,
        project_name: str = "",
    ) -> None:
        """Publish a bounded Capability Map with no source paths, full hashes, or authority."""

        if profile is None:
            self._telemetry = replace(
                self._telemetry,
                captured_at=datetime.now(UTC).isoformat(),
                device_dna_state="unavailable",
                device_dna_project="",
                device_dna_profile_ref="",
                device_dna_warning_count=0,
                device_dna_capabilities=(),
                device_dna_execution_authority="none",
                device_dna_bootloader_relock="never",
            )
            return
        actionable = tuple(
            item for item in profile.capabilities if item.capability_id != "bootloader_relock"
        )
        needs_attention = any(item.state is not CapabilityState.SUPPORTED for item in actionable)
        capabilities = tuple(
            DeviceDnaCapabilityTelemetry(
                item.capability_id,
                self._link_text(item.label),
                item.state.value,
                self._link_text(item.detail),
            )
            for item in profile.capabilities[:12]
        )
        self._telemetry = replace(
            self._telemetry,
            captured_at=datetime.now(UTC).isoformat(),
            device_dna_state="needs-attention" if needs_attention else "ready",
            device_dna_project=self._link_text(project_name or profile.project_id)[:120],
            device_dna_profile_ref=profile.profile_digest[:16],
            device_dna_warning_count=min(100, len(profile.warnings)),
            device_dna_capabilities=capabilities,
            device_dna_execution_authority="none",
            device_dna_bootloader_relock="never",
        )

    def set_nexus_plan(self, plan: NexusPlan | None) -> None:
        """Publish only bounded plan status; Nexus execution remains on Desktop."""

        self._nexus_plan = plan

    def _telemetry_snapshot(self) -> CompanionTelemetry:
        events: tuple[LiveConsoleTelemetryEvent, ...] = ()
        integrity = "unavailable"
        if self._live_console_store is not None:
            try:
                recent = self._live_console_store.list_recent(8)
                integrity = "trusted"
                events = tuple(
                    LiveConsoleTelemetryEvent(
                        event_id=item.event_id,
                        updated_at=item.updated_at,
                        source=self._link_text(item.source),
                        stage=self._link_text(item.stage),
                        title=self._link_text(item.title),
                        summary=self._link_text(item.summary),
                        explanation=self._link_text(item.explanation),
                        next_action=self._link_text(item.next_action),
                        state=item.state.value,
                        progress_percent=item.progress_percent,
                        confidence=item.confidence.value,
                        guardian_protected=item.guardian_protected,
                    )
                    for item in recent
                )
            except (LiveConsoleStoreError, ValueError):
                integrity = "needs-attention"
        terminal_records: tuple[RawTerminalTelemetryRecord, ...] = ()
        terminal_integrity = "unavailable"
        if self._raw_terminal_feed is not None:
            try:
                terminal_records = tuple(
                    RawTerminalTelemetryRecord(
                        record_id=item.record_id,
                        captured_at=item.captured_at,
                        probe_id=item.probe_id,
                        title=item.title,
                        lines=item.lines,
                        success=item.success,
                        record_digest=item.record_digest,
                    )
                    for item in self._raw_terminal_feed.snapshot()
                )
                terminal_integrity = "verified-local-feed"
            except ValueError:
                terminal_records = ()
                terminal_integrity = "needs-attention"
        plan = self._nexus_plan
        stage = ""
        if plan is not None:
            current = next(
                (item for item in plan.route if item.state is RouteStageState.CURRENT),
                None,
            )
            if current is None:
                current = next(
                    (item for item in plan.route if item.state is RouteStageState.UPCOMING),
                    None,
                )
            stage = current.label if current is not None else ""
        return replace(
            self._telemetry,
            captured_at=datetime.now(UTC).isoformat(),
            live_console_events=events,
            live_console_integrity=integrity,
            nexus_status=plan.status.value if plan is not None else "no-plan",
            nexus_objective=plan.objective.value if plan is not None else "none",
            nexus_current_stage=stage,
            nexus_research_count=len(plan.research_requirements) if plan is not None else 0,
            guardian_review_state=(
                "ready"
                if plan is not None and plan.status is NexusPlanStatus.READY_FOR_GUARDIAN
                else "blocked"
                if plan is not None
                else "unavailable"
            ),
            live_console_execution_authority="none",
            raw_terminal_included=bool(terminal_records),
            raw_terminal_integrity=terminal_integrity,
            raw_terminal_records=terminal_records,
        )

    @staticmethod
    def _link_text(value: str) -> str:
        """Scrub local paths and full digests before a Desktop event leaves the PC."""

        clean = re.sub(r"\s+", " ", value.replace("\x00", " ")).strip()
        clean = re.sub(r"(?<![\w.])/(?:[^\s,;]+/?)+", "<local-path>", clean)
        clean = re.sub(r"\b[A-Za-z]:\\[^\s,;]+", "<local-path>", clean)
        return re.sub(r"\b[0-9a-fA-F]{64}\b", "<sha256>", clean)

    def _pairing_code_active(self) -> bool:
        return self._pairing is not None and not self._pairing.expired

    def _update_usb_assist_button(self) -> None:
        available = bool(
            self._usb_pairing_service is not None
            and self.transport.available
            and self._usb_ready
            and self._usb_serial
            and self._usb_companion_installed
            and not self._approved
            and not self._pairing_code_active()
        )
        self.usb_pair.setEnabled(available)
        if available:
            self.usb_pair.setToolTip(
                "Open a one-use safety-code confirmation on this exact authorized USB phone."
            )
        elif self._usb_ready and not self._usb_companion_installed:
            self.usb_pair.setToolTip(
                "Install ROMVERSE Companion on the selected phone before using USB assist."
            )
        elif self._approved:
            self.usb_pair.setToolTip("This Companion Link is already paired.")
        else:
            self.usb_pair.setToolTip(
                "Connect and authorize one phone by USB. The phone must still confirm the matching safety code."
            )

    def generate_code(self) -> None:
        self._begin_pairing(usb_auto_approve=False)

    def _begin_pairing(self, *, usb_auto_approve: bool) -> None:
        if not self.transport.available:
            self.state.setText("Wireless pairing unavailable")
            self.instructions.setText(
                "This computer denied local network access. USB read-only Companion features still work."
            )
            return
        if not self.transport.start():
            self.state.setText("Wireless pairing unavailable")
            self.instructions.setText(
                "ROMVERSE could not safely open the encrypted local pairing endpoint. "
                "USB read-only Companion features still work."
            )
            self.network_status.setText(
                "Wireless pairing unavailable on this computer  •  USB read-only features remain active"
            )
            self.generate.setEnabled(False)
            self._update_usb_assist_button()
            self._record_link_availability()
            return
        self.network_status.setText(
            f"Encrypted pairing endpoint: https://{self._local_address()}:{self.transport.port}"
            "  •  TLS 1.2+  •  same trusted network required"
        )
        self.transport.reset()
        self._refresh_transfer_state()
        self._pairing = create_pairing_code()
        self._approved = False
        self._approved_restored = False
        self._usb_auto_approve = usb_auto_approve
        self._usb_assist_plan = None
        self._pending_announced = False
        self.safety_confirm.setChecked(False)
        self.safety_confirm.setEnabled(False)
        self.code.setText(self._pairing.code[:3] + " " + self._pairing.code[3:])
        self.copy_button.setEnabled(True)
        self.reset_link.setEnabled(True)
        self.generate.setText("Generate wireless code")
        self.generate.setToolTip(
            "This code is valid for ten minutes and does not grant device-changing authority."
        )
        self.expiry.setText("Expires in 10:00")
        self.state.setText("Awaiting device approval")
        self.instructions.setText(
            "Enter this code in Companion. When the request arrives, compare the Link safety code on both screens before approving."
        )
        self.approve.setEnabled(False)
        self._update_usb_assist_button()
        self._expiry_timer.start()
        self._record_link_note(
            title="Encrypted Companion pairing opened",
            summary="ROMVERSE created a short-lived code for a TLS-pinned read-only Link request.",
            explanation="No phone is approved yet. Companion must present this code and the user must verify the matching safety code on both screens.",
            next_action="Enter the code in Companion, compare the Link safety code, then approve the request here.",
            state=MissionState.INFORMATION,
            confidence=MissionConfidence.VERIFIED,
            dedupe_key="",
        )

    @Slot()
    def pair_connected_usb(self) -> None:
        service = self._usb_pairing_service
        if (
            service is None
            or not self._usb_ready
            or not self._usb_serial
            or not self._usb_companion_installed
            or not self.transport.available
        ):
            self.state.setText("USB-assisted pairing is not ready")
            self.instructions.setText(
                "Connect one authorized Android phone with ROMVERSE Companion installed, then let the read-only scan finish."
            )
            self._update_usb_assist_button()
            return
        self._begin_pairing(usb_auto_approve=True)
        pairing = self._pairing
        if pairing is None:
            return
        try:
            plan = service.prepare(
                serial=self._usb_serial,
                port=self.transport.port,
                certificate_sha256=self.transport.certificate_sha256,
                pairing_code=pairing.code,
                expires_at=pairing.expires_at,
            )
            service.approve(plan)
            result = service.launch(plan)
        except Exception:
            self._usb_auto_approve = False
            self.state.setText("USB-assisted pairing stopped safely")
            self.instructions.setText(
                "ROMVERSE could not open the phone confirmation. The wireless code remains available for manual pairing."
            )
            self._update_usb_assist_button()
            return
        if not result.ok:
            self._usb_auto_approve = False
            self.state.setText("USB-assisted pairing needs attention")
            self.instructions.setText(
                f"{result.detail} The wireless code remains available for manual pairing."
            )
            self._update_usb_assist_button()
            return
        self._usb_assist_plan = plan
        self.state.setText("Check the safety code on your phone")
        self.instructions.setText(
            "USB delivered this one-use request to the selected phone. Choose Yes only if its safety code matches the Desktop code above; confirmation then completes read-only Link automatically."
        )
        self.copy_button.setEnabled(False)
        self._record_link_note(
            title="USB-assisted Companion confirmation opened",
            summary="ROMVERSE opened one safety-code prompt on the selected authorized USB phone.",
            explanation="The phone is not trusted yet. Link completes only if the user confirms the matching Desktop certificate code on that phone.",
            next_action="Compare the phone and Desktop safety codes, then choose Yes or No on the phone.",
            state=MissionState.ATTENTION,
            confidence=MissionConfidence.UNCONFIRMED,
            dedupe_key="",
        )

    def approve_device(self) -> None:
        if self._pairing is None or self._pairing.expired:
            return
        if not self.safety_confirm.isChecked():
            self.state.setText("Safety-code confirmation required")
            self.instructions.setText(
                "Confirm that the PC and phone show the same Link safety code. ROMVERSE will not approve a mismatched or unchecked identity."
            )
            return
        if not self.transport.approve():
            self.state.setText("Waiting for a verified phone request")
            self.instructions.setText(
                "Enter the code on your phone first. Approve unlocks only after ROMVERSE receives that exact request."
            )
            self.approve.setEnabled(False)
            return
        self._render_approved_state(restored=False)
        self._record_link_note(
            title="Encrypted Companion Link approved",
            summary="The phone completed TLS-pinned, safety-code-confirmed read-only pairing.",
            explanation="Protocol v3 encrypts the local channel and pins Companion to this workspace certificate. Guardian granted no device-changing authority.",
            next_action="Use read-only Companion health and Live Console telemetry; Guardian still reviews every changing action.",
            state=MissionState.INFORMATION,
            confidence=MissionConfidence.VERIFIED,
            dedupe_key="",
        )

    def _update_remote_snapshot(self) -> None:
        self._sync_approved_state()
        snapshot = self.transport.latest_remote_snapshot
        received_at = self.transport.remote_snapshot_received_at
        if snapshot is None or received_at is None:
            return
        if snapshot.captured_at_epoch_ms != self._last_remote_capture:
            self._last_remote_capture = snapshot.captured_at_epoch_ms
            self.remote_snapshot_updated.emit(snapshot)
        battery = (
            f"{snapshot.battery_percent}%"
            if snapshot.battery_percent is not None
            else "unavailable"
        )
        storage = self._usage_text(snapshot.storage_used_bytes, snapshot.storage_total_bytes)
        memory_used = None
        if snapshot.memory_available_bytes is not None and snapshot.memory_total_bytes is not None:
            memory_used = snapshot.memory_total_bytes - snapshot.memory_available_bytes
        memory = self._usage_text(memory_used, snapshot.memory_total_bytes)
        health = (
            f"{snapshot.health_score}/100" if snapshot.health_score is not None else "not scored"
        )
        vitalis = (
            f"{snapshot.vitalis_state} • {snapshot.vitalis_evidence_percent}% evidence"
            if snapshot.schema_version >= 4
            else "legacy evidence contract"
        )
        if (
            snapshot.schema_version >= 5
            and snapshot.user_data_backup_state == "confirmed_by_user"
            and snapshot.user_data_backup_confirmed_at_epoch_ms is not None
        ):
            backup_time = (
                datetime.fromtimestamp(
                    snapshot.user_data_backup_confirmed_at_epoch_ms / 1000,
                    tz=UTC,
                )
                .astimezone()
                .strftime("%Y-%m-%d %H:%M")
            )
            backup = f"confirmed by user at {backup_time}"
        else:
            backup = "unconfirmed"
        synchronized = received_at.astimezone().strftime("%H:%M:%S")
        self.remote_summary.setText(
            "LIVE COMPANION HEALTH  •  AUTHENTICATED\n"
            f"{snapshot.manufacturer} {snapshot.model} ({snapshot.device_codename})  •  "
            f"Android {snapshot.android_version} / API {snapshot.sdk_int}\n"
            f"Battery {battery}  •  Storage {storage}  •  RAM {memory}  •  "
            f"Guardian health {health}\n"
            f"Vitalis {vitalis}\n"
            f"User-data backup {backup}  •  user attestation only  •  authority none\n"
            f"Synced {synchronized}  •  Companion {snapshot.companion_version}  •  "
            f"{snapshot.privacy_scope.replace('_', ' ')} privacy scope\n"
            f"Kernel {snapshot.kernel_release or 'unavailable'}  •  "
            f"Root signal {snapshot.root_signal.replace('_', ' ')}  •  "
            f"Manager candidate {snapshot.root_manager_candidate.replace('_', ' ')}  •  "
            f"Bootloader {snapshot.bootloader_state}  •  KernelSU {snapshot.kernelsu_support}"
        )

    @staticmethod
    def _usage_text(used: int | None, total: int | None) -> str:
        if used is None or total is None:
            return "unavailable"
        return f"{CompanionCenter._format_bytes(used)} / {CompanionCenter._format_bytes(total)}"

    @staticmethod
    def _format_bytes(value: int) -> str:
        amount = float(value)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if amount < 1024 or unit == "TB":
                return f"{amount:.1f} {unit}"
            amount /= 1024
        return f"{amount:.1f} TB"

    @Slot()
    def choose_companion_transfer(self) -> None:
        service = self.transfer_service
        if service is None or not self.transport.approved or self._transfer_worker is not None:
            return
        filters = {
            "Android app (*.apk)": CompanionTransferKind.APK,
            "ROMVERSE report (*.json *.txt *.log *.html *.htm *.pdf)": CompanionTransferKind.REPORT,
            "Recovery capsule (*.romverse-recovery *.recovery.zip *.zip)": CompanionTransferKind.RECOVERY_CAPSULE,
            "Approved package (*.romverse-package *.romverse *.zip *.bin *.img)": CompanionTransferKind.APPROVED_PACKAGE,
            "Emergency guide (*.json *.txt *.html *.htm *.pdf)": CompanionTransferKind.EMERGENCY_GUIDE,
        }
        filename, selected_filter = QFileDialog.getOpenFileName(
            self,
            "Choose a file for ROMVERSE Companion",
            str(Path.home()),
            ";;".join(filters),
        )
        if not filename:
            return
        kind = filters.get(selected_filter)
        if kind is None:
            self._set_transfer_status(
                "No handoff was created because its file type was not selected.",
                "Warning",
            )
            return
        self.transfer_button.setEnabled(False)
        self._set_transfer_status(
            "Verifying the selected file for an exact handoff preview…",
            "CompanionTransferStatus",
        )
        worker = _CompanionTransferWorker(lambda: service.inspect(Path(filename), kind))
        self._transfer_worker = worker
        worker.signals.completed.connect(self._transfer_preview_ready)
        worker.signals.failed.connect(self._transfer_failed)
        start_background(worker)

    @Slot(object)
    def _transfer_preview_ready(self, value: object) -> None:
        self._transfer_worker = None
        if not isinstance(value, CompanionTransferPreview):
            self._transfer_failed("ROMVERSE returned an invalid transfer preview")
            return
        if not self.transport.approved or self.transfer_service is None:
            self._set_transfer_status(
                "The Link changed while the file was inspected. Pair again before offering it.",
                "Warning",
            )
            self._refresh_transfer_state()
            return
        answer = QMessageBox.question(
            self,
            "ROMVERSE Link • Confirm secure handoff",
            f"File: {value.display_name}\n"
            f"Type: {value.kind.value.replace('_', ' ').title()}\n"
            f"Size: {self._format_bytes(value.size_bytes)}\n"
            f"SHA-256: {value.sha256}\n\n"
            "Confirming copies these exact bytes into private ROMVERSE staging and makes a "
            "download offer available to the currently trusted Companion for 24 hours. The "
            "phone must confirm where to save it. Nothing will install, open, execute, flash, "
            "or change the phone automatically.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer is not QMessageBox.StandardButton.Yes:
            self._set_transfer_status(
                "Handoff declined. The selected file was inspected but not copied or offered.",
                "Warning",
            )
            self._refresh_transfer_state(preserve_message=True)
            return
        service = self.transfer_service
        if service is None:
            self._transfer_failed("Private Companion transfer storage is unavailable")
            return
        self.transfer_button.setEnabled(False)
        self._set_transfer_status(
            "Creating the approved private copy and rechecking its exact fingerprint…",
            "CompanionTransferStatus",
        )
        worker = _CompanionTransferWorker(lambda: service.stage(value))
        self._transfer_worker = worker
        worker.signals.completed.connect(self._transfer_staged)
        worker.signals.failed.connect(self._transfer_failed)
        start_background(worker)

    @Slot(object)
    def _transfer_staged(self, value: object) -> None:
        self._transfer_worker = None
        if not isinstance(value, CompanionTransferOffer):
            self._transfer_failed("ROMVERSE returned an invalid transfer offer")
            return
        self._set_transfer_status(
            f"READY FOR COMPANION  •  {value.display_name}  •  "
            f"{self._format_bytes(value.size_bytes)}  •  SHA-256 {value.sha256[:16]}…\n"
            "The encrypted Link now advertises this download. Companion will ask the user to "
            "accept or decline and choose the save location.",
            "Good",
        )
        self._record_link_note(
            title="Secure Companion handoff ready",
            summary=f"{value.display_name} is available to the authenticated Companion for 24 hours.",
            explanation="ROMVERSE copied the exact reviewed bytes into private content-addressed staging. Installation and execution authority remain none.",
            next_action="Open Secure Handoff on Companion, review the fingerprint, and choose where to save it.",
            state=MissionState.INFORMATION,
            confidence=MissionConfidence.VERIFIED,
            dedupe_key="",
        )
        self._refresh_transfer_state(preserve_message=True)

    @Slot(str)
    def _transfer_failed(self, message: str) -> None:
        self._transfer_worker = None
        self._set_transfer_status(f"Secure handoff stopped safely: {message}", "Danger")
        self._refresh_transfer_state(preserve_message=True)

    @Slot()
    def revoke_companion_transfers(self) -> None:
        service = self.transfer_service
        if service is None:
            return
        answer = QMessageBox.question(
            self,
            "Revoke pending Companion handoffs?",
            "This removes every pending phone download offer. Original files are never deleted. "
            "Private inert content may remain for integrity history, but no Companion can request "
            "it without a new confirmed offer.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer is not QMessageBox.StandardButton.Yes:
            return
        try:
            count = service.revoke_all()
        except CompanionTransferError as exc:
            self._set_transfer_status(f"Handoff revocation needs attention: {exc}", "Danger")
            return
        self._set_transfer_status(
            f"Revoked {count} pending handoff{'s' if count != 1 else ''}. Original files were not changed.",
            "Warning",
        )
        self._refresh_transfer_state(preserve_message=True)

    def _refresh_transfer_state(self, *, preserve_message: bool = False) -> None:
        available = bool(
            self.transfer_service is not None
            and self.transport.available
            and self.transport.approved
            and self._transfer_worker is None
        )
        self.transfer_button.setEnabled(available)
        service = self.transfer_service
        if service is None:
            self.transfer_clear.setEnabled(False)
            if not preserve_message:
                detail = (
                    self._transfer_availability_error or "Open a persistent ROMVERSE workspace."
                )
                self._set_transfer_status(
                    f"Private handoff storage is unavailable. {detail}",
                    "Warning",
                )
            return
        try:
            offers = service.list_active()
        except CompanionTransferError as exc:
            self.transfer_button.setEnabled(False)
            self.transfer_clear.setEnabled(False)
            if not preserve_message:
                self._set_transfer_status(
                    f"Private handoff storage needs attention: {exc}", "Danger"
                )
            return
        self.transfer_clear.setEnabled(bool(offers))
        if preserve_message:
            return
        if not self.transport.approved:
            self._set_transfer_status(
                "Pair Companion to open the encrypted handoff bridge.",
                "CompanionTransferStatus",
            )
        elif not offers:
            self._set_transfer_status(
                "Encrypted bridge ready  •  no files are waiting for the phone.",
                "CompanionTransferStatus",
            )
        else:
            latest = offers[0]
            self._set_transfer_status(
                f"{len(offers)} pending handoff{'s' if len(offers) != 1 else ''}  •  "
                f"latest: {latest.display_name}  •  SHA-256 {latest.sha256[:16]}…",
                "Good",
            )

    def _set_transfer_status(self, message: str, state: str) -> None:
        self.transfer_status.setText(message)
        self.transfer_status.setObjectName(state)
        self.transfer_status.style().unpolish(self.transfer_status)
        self.transfer_status.style().polish(self.transfer_status)

    def _update_expiry(self) -> None:
        if self.transport.pending and not self.transport.approved and not self._approved:
            if self._usb_auto_approve:
                if self.transport.approve():
                    self._render_approved_state(restored=False)
                    self._record_link_note(
                        title="USB-confirmed Companion Link approved",
                        summary="The selected phone confirmed the matching safety code and completed its one-use request.",
                        explanation="Desktop received the exact code delivered to that authorized USB phone. The resulting encrypted Link carries read-only telemetry only.",
                        next_action="Use Companion health and Live Console telemetry; Guardian still reviews every changing action.",
                        state=MissionState.INFORMATION,
                        confidence=MissionConfidence.VERIFIED,
                        dedupe_key="",
                    )
                    return
                self._usb_auto_approve = False
            self.state.setText("Wireless request received • approve device")
            self.safety_confirm.setEnabled(True)
            self.approve.setEnabled(self.safety_confirm.isChecked())
            if not self._pending_announced:
                self._pending_announced = True
                self._record_link_note(
                    title="Companion Link request awaiting safety check",
                    summary="A phone supplied the current one-time code and is waiting for local approval.",
                    explanation="ROMVERSE has not approved the session. Compare the safety code on both screens before continuing.",
                    next_action="Confirm the matching Link safety code, then approve the device on this PC.",
                    state=MissionState.ATTENTION,
                    confidence=MissionConfidence.UNCONFIRMED,
                    dedupe_key="",
                )
        if self._pairing is None:
            return
        remaining = int(
            (datetime.fromisoformat(self._pairing.expires_at) - datetime.now(UTC)).total_seconds()
        )
        if remaining <= 0:
            self._expiry_timer.stop()
            self.transport.reset()
            self._pairing = None
            self._usb_auto_approve = False
            self._usb_assist_plan = None
            self.code.setText("------")
            self.copy_button.setEnabled(False)
            self.reset_link.setEnabled(False)
            self.expiry.setText("Pairing code expired. Generate a new code.")
            self.state.setText(
                "Wireless Link not paired • USB read-only evidence remains available"
                if self._usb_ready
                else "Not paired"
            )
            self.instructions.setText(
                "Generate a new wireless code for the phone's live Companion view. "
                "The USB scan remains separate and read-only."
                if self._usb_ready
                else "Generate a new code, then enter it in ROMVERSE Companion on your Android phone."
            )
            self.generate.setText("Generate wireless code")
            self.approve.setEnabled(False)
            self.safety_confirm.setChecked(False)
            self.safety_confirm.setEnabled(False)
            self._update_usb_assist_button()
            return
        minutes, seconds = divmod(remaining, 60)
        self.expiry.setText(f"Expires in {minutes:02d}:{seconds:02d}")

    @Slot(bool)
    def _update_approval_button(self, confirmed: bool) -> None:
        self.approve.setEnabled(
            confirmed and self.transport.pending and not self.transport.approved
        )

    def _render_approved_state(self, *, restored: bool) -> None:
        self._approved = True
        self._approved_restored = restored
        self._usb_auto_approve = False
        self._usb_assist_plan = None
        state = (
            "Remembered pairing active • read-only wireless telemetry enabled"
            if restored
            else "Paired • read-only wireless telemetry enabled"
        )
        if self._usb_ready:
            state += " • USB also connected"
        self.state.setText(state)
        self.instructions.setText(
            "This workspace remembers the approved Companion for read-only health/activity telemetry "
            "and user-confirmed download handoffs. USB evidence remains a separate input. Guardian still "
            "blocks device-changing actions."
        )
        self._expiry_timer.stop()
        self._pairing = None
        self.code.setText("••• •••")
        self.copy_button.setEnabled(False)
        self.approve.setEnabled(False)
        self.safety_confirm.setChecked(False)
        self.safety_confirm.setEnabled(False)
        self.reset_link.setEnabled(True)
        self.generate.setText("Replace wireless pairing code")
        self.generate.setToolTip(
            "Revoke the remembered wireless session and create a new short-lived pairing code."
        )
        self.generate.setEnabled(self.transport.available)
        self._update_usb_assist_button()
        self.expiry.setText(self._approved_expiry_text())
        self._refresh_transfer_state()

    def _approved_expiry_text(self) -> str:
        remaining = self.transport.session_expires_in_seconds
        if remaining <= 0:
            return "Remembered wireless session has expired."
        days = ceil(remaining / (24 * 60 * 60))
        if days >= 2:
            lifetime = f"about {days} days"
        else:
            hours = max(1, ceil(remaining / (60 * 60)))
            lifetime = f"about {hours} hour{'s' if hours != 1 else ''}"
        return (
            f"Remembered wireless session expires in {lifetime}. Reset it anytime from this screen."
        )

    def _sync_approved_state(self) -> None:
        approved = self.transport.approved and self.transport.running
        if approved and not self._approved:
            self._render_approved_state(restored=True)
            return
        if approved:
            self.expiry.setText(self._approved_expiry_text())
            return
        if not self._approved:
            return
        self.transport.reset()
        self._approved = False
        self._approved_restored = False
        self._usb_auto_approve = False
        self._usb_assist_plan = None
        self.reset_link.setEnabled(False)
        self.generate.setText("Generate wireless code")
        self.generate.setToolTip("")
        self.generate.setEnabled(self.transport.available)
        self._update_usb_assist_button()
        self.code.setText("------")
        self.copy_button.setEnabled(False)
        self.expiry.setText(
            "Remembered wireless session expired. Generate a new code to pair again."
        )
        self.remote_summary.setText(
            "LIVE COMPANION HEALTH\nWaiting for an authenticated phone snapshot."
        )
        self._refresh_transfer_state()
        self._last_remote_capture = 0
        if self._usb_ready:
            self.state.setText("Wireless Link expired • USB read-only evidence remains available")
            self.instructions.setText(
                "Generate a new wireless code to restore the phone's live Companion view. "
                "The USB scan remains separate and read-only."
            )
        else:
            self.state.setText("Not paired")
            self.instructions.setText(
                "Generate a code, then enter it in ROMVERSE Companion on your Android phone."
            )

    @Slot()
    def reset_pairing(self) -> None:
        self.transport.reset()
        self._pairing = None
        self._approved = False
        self._approved_restored = False
        self._usb_auto_approve = False
        self._usb_assist_plan = None
        self._pending_announced = False
        self._last_remote_capture = 0
        self._expiry_timer.stop()
        self.code.setText("------")
        self.copy_button.setEnabled(False)
        self.approve.setEnabled(False)
        self.safety_confirm.setChecked(False)
        self.safety_confirm.setEnabled(False)
        self.reset_link.setEnabled(False)
        self.generate.setText("Generate wireless code")
        self.generate.setToolTip("")
        self.generate.setEnabled(self.transport.available)
        self._update_usb_assist_button()
        self.remote_summary.setText(
            "LIVE COMPANION HEALTH\nWaiting for an authenticated phone snapshot."
        )
        self._refresh_transfer_state()
        if self._usb_ready:
            self.state.setText(
                "Wireless Link not paired • USB read-only evidence remains available"
            )
            self.instructions.setText(
                "Wireless authorization was revoked. USB continues supplying Desktop's read-only "
                "device scan; generate a new code whenever you want the phone's live view."
            )
            self.expiry.setText("Wireless pairing reset. USB evidence was not changed.")
        else:
            self.state.setText("Not paired")
            self.instructions.setText(
                "Wireless pairing was reset on this computer. Generate a new code whenever you want to reconnect Companion."
            )
            self.expiry.setText(
                "Wireless pairing reset. Any remembered Companion token is now revoked."
            )
        self._record_link_note(
            title="Companion Link pairing reset",
            summary="The remembered wireless Companion authorization was revoked locally.",
            explanation="ROMVERSE cleared the pending request, stored session digest, cached wireless telemetry, and pending download offers. USB read-only evidence and original files were not changed.",
            next_action="Generate a new wireless code only when you want to pair Companion again.",
            state=MissionState.INFORMATION,
            confidence=MissionConfidence.VERIFIED,
            dedupe_key="",
        )

    def _record_link_availability(self) -> None:
        if self.transport.available:
            return
        self._record_link_note(
            title="Encrypted Companion Link needs attention",
            summary="ROMVERSE could not open the encrypted wireless Link endpoint.",
            explanation="The TLS identity or local listener could not be initialized safely. USB read-only features remain available.",
            next_action="Review ROMVERSE settings, local permissions, and port availability before retrying wireless Link.",
            state=MissionState.ATTENTION,
            confidence=MissionConfidence.UNCONFIRMED,
            dedupe_key="companion-link-v3-unavailable",
        )

    def _record_link_note(
        self,
        *,
        title: str,
        summary: str,
        explanation: str,
        next_action: str,
        state: MissionState,
        confidence: MissionConfidence,
        dedupe_key: str,
    ) -> None:
        if self._live_console_store is None:
            return
        try:
            self._live_console_store.note(
                source="ROMVERSE Link",
                stage="secure-pairing",
                title=title,
                summary=summary,
                explanation=explanation,
                next_action=next_action,
                state=state,
                confidence=confidence,
                guardian_protected=True,
                dedupe_key=dedupe_key,
            )
        except LiveConsoleStoreError:
            # A damaged ledger must not be silently replaced or block USB fallback.
            return

    def copy_code(self) -> None:
        if self._pairing is not None and not self._pairing.expired:
            QApplication.clipboard().setText(self._pairing.code)

    def import_summary(self) -> None:
        payload = QApplication.clipboard().text().strip()
        if not payload.startswith("ROMVERSE Companion health summary"):
            self.summary.setText("Clipboard does not contain a ROMVERSE Companion summary.")
            return
        self.summary.setText(payload)

    @staticmethod
    def _local_address() -> str:
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            probe.connect(("8.8.8.8", 80))
            address = probe.getsockname()[0]
            probe.close()
            return address
        except OSError:
            return "127.0.0.1"

    def closeEvent(self, event) -> None:  # noqa: N802
        self.shutdown()
        super().closeEvent(event)

    @Slot()
    def shutdown(self) -> None:
        self._expiry_timer.stop()
        self._remote_timer.stop()
        self.transport.close()
