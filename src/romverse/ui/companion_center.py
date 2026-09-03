from __future__ import annotations

import re
import socket
from dataclasses import replace
from datetime import UTC, datetime
from math import ceil
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QLabel,
    QPushButton,
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
from romverse.companion.transport import CompanionTransport
from romverse.device.dna import CapabilityState, DeviceDnaProfile
from romverse.device.models import AndroidDevice, DeviceState
from romverse.nexus.events import (
    LiveConsoleEventStore,
    LiveConsoleStoreError,
    MissionConfidence,
    MissionState,
)
from romverse.nexus.planning import NexusPlan, NexusPlanStatus, RouteStageState


class CompanionCenter(QWidget):
    remote_snapshot_updated = Signal(object)

    def __init__(
        self,
        live_console_store: LiveConsoleEventStore | None = None,
        raw_terminal_feed: RawTerminalFeed | None = None,
        workspace: Path | None = None,
    ) -> None:
        super().__init__()
        self._pairing: PairingCode | None = None
        self._approved = False
        self._usb_paired = False
        self._last_remote_capture = 0
        self._pending_announced = False
        self._telemetry = CompanionTelemetry()
        self._live_console_store = live_console_store
        self._raw_terminal_feed = raw_terminal_feed
        self._nexus_plan: NexusPlan | None = None
        identity_root = workspace / "config" / "companion-link" if workspace is not None else None
        self.transport = CompanionTransport(
            lambda: self._pairing,
            self._telemetry_snapshot,
            identity_root,
        )
        self.transport.start()
        self._approved = self.transport.approved
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
        page = QVBoxLayout(self)
        page.setContentsMargins(30, 26, 30, 30)
        page.setSpacing(16)
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
        if self.transport.available:
            network_text = (
                f"Encrypted pairing endpoint: https://{self._local_address()}:{self.transport.port}"
                "  •  TLS 1.2+  •  same trusted network required"
            )
        else:
            network_text = "Wireless pairing unavailable on this computer  •  USB read-only features remain active"
        self.network_status = QLabel(network_text)
        self.network_status.setObjectName("Muted")
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
        self.identity_status.setObjectName("StatusCard")
        self.identity_status.setWordWrap(True)
        self.identity_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.identity_status.setToolTip(
            "The PC and phone must show the same safety code. A mismatch can mean you discovered the wrong computer or the network path was intercepted."
        )
        page.addWidget(self.identity_status)
        card = QFrame()
        card.setObjectName("HeroCard")
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
        self.code.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.code.setStyleSheet(
            "font-size:42px; font-weight:800; letter-spacing:8px; color:#D8B5FF;"
        )
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
        self.remote_summary.setObjectName("StatusCard")
        self.remote_summary.setStyleSheet(
            "QLabel#StatusCard { background: rgba(3, 12, 22, 225); "
            "border: 1px solid rgba(40, 231, 245, 105); border-radius: 10px; "
            "padding: 14px; color: #DDE9FF; }"
        )
        self.remote_summary.setWordWrap(True)
        self.remote_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.remote_summary.setToolTip(
            "A paired phone may share battery, storage, memory, Android version, and a local health score. "
            "ROMVERSE never requests its serial, IMEI, accounts, files, or app list through this channel."
        )
        layout.addWidget(self.remote_summary)
        buttons = QVBoxLayout()
        self.generate = QPushButton("Generate wireless code")
        self.generate.setObjectName("Primary")
        self.generate.setEnabled(self.transport.available)
        if not self.transport.available:
            self.generate.setToolTip(
                "This environment denied ROMVERSE permission to open a local pairing endpoint."
            )
        self.generate.clicked.connect(self.generate_code)
        self.copy_button = QPushButton("Copy code")
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(self.copy_code)
        self.approve = QPushButton("Approve device")
        self.approve.setObjectName("Primary")
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
        self.reset_link.setEnabled(False)
        self.reset_link.setToolTip(
            "Immediately revoke the remembered wireless session on this computer. USB pairing is not changed."
        )
        self.reset_link.clicked.connect(self.reset_pairing)
        import_summary = QPushButton("Import phone summary")
        import_summary.setToolTip(
            "Read a ROMVERSE health summary from the clipboard. This is display-only and never executes commands."
        )
        import_summary.clicked.connect(self.import_summary)
        buttons.addWidget(self.generate)
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.safety_confirm)
        buttons.addWidget(self.approve)
        buttons.addWidget(self.reset_link)
        buttons.addWidget(import_summary)
        layout.addLayout(buttons)
        page.addWidget(card)
        boundary = QLabel(
            "Guardian boundary  •  pairing grants telemetry visibility only; it cannot approve or execute device-changing operations."
        )
        boundary.setObjectName("Warning")
        boundary.setWordWrap(True)
        page.addWidget(boundary)
        page.addStretch()
        if self._approved:
            self._render_approved_state(restored=True)

    def set_device_snapshot(self, devices: list[AndroidDevice]) -> None:
        """Reflect the latest read-only Device Engine result in Companion."""

        self._sync_approved_state()
        device = next((item for item in devices if item.state is DeviceState.DEVICE), None)
        if device is None:
            if self._approved:
                self.device_status.setText(
                    "Desktop device link: wireless Companion active  •  USB is disconnected"
                )
                self._render_approved_state(restored=True)
            else:
                self.device_status.setText(
                    "Desktop device link: no USB device detected  •  wireless pairing remains available"
                )
            self._usb_paired = False
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
        self._usb_paired = bool(device.companion_installed)
        if self._usb_paired:
            self.state.setText("USB paired • read-only telemetry enabled")
            self.instructions.setText(
                "This authorized phone was paired automatically over USB. Generate a wireless code only when using Wi‑Fi."
            )
            self.generate.setEnabled(False)
        else:
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

    def generate_code(self) -> None:
        if not self.transport.available:
            self.state.setText("Wireless pairing unavailable")
            self.instructions.setText(
                "This computer denied local network access. USB read-only Companion features still work."
            )
            return
        self.transport.reset()
        self._pairing = create_pairing_code()
        self._approved = False
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
        synchronized = received_at.astimezone().strftime("%H:%M:%S")
        self.remote_summary.setText(
            "LIVE COMPANION HEALTH  •  AUTHENTICATED\n"
            f"{snapshot.manufacturer} {snapshot.model} ({snapshot.device_codename})  •  "
            f"Android {snapshot.android_version} / API {snapshot.sdk_int}\n"
            f"Battery {battery}  •  Storage {storage}  •  RAM {memory}  •  "
            f"Guardian health {health}\n"
            f"Vitalis {vitalis}\n"
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

    def _update_expiry(self) -> None:
        if self.transport.pending and not self.transport.approved and not self._approved:
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
            self.code.setText("------")
            self.copy_button.setEnabled(False)
            self.reset_link.setEnabled(False)
            self.expiry.setText("Pairing code expired. Generate a new code.")
            self.state.setText("Not paired")
            self.generate.setText("Generate wireless code")
            self.approve.setEnabled(False)
            self.safety_confirm.setChecked(False)
            self.safety_confirm.setEnabled(False)
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
        if not self._usb_paired:
            self.state.setText(
                "Remembered pairing active • read-only telemetry enabled"
                if restored
                else "Paired • read-only telemetry enabled"
            )
            self.instructions.setText(
                "This workspace remembers the approved Companion for read-only health and activity telemetry. Guardian still blocks device-changing actions."
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
        self.generate.setEnabled(self.transport.available and not self._usb_paired)
        self.expiry.setText(self._approved_expiry_text())

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
        return f"Remembered wireless session expires in {lifetime}. Reset it anytime from this screen."

    def _sync_approved_state(self) -> None:
        approved = self.transport.approved
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
        self.reset_link.setEnabled(False)
        self.generate.setText("Generate wireless code")
        self.generate.setToolTip("")
        self.generate.setEnabled(self.transport.available and not self._usb_paired)
        self.code.setText("------")
        self.copy_button.setEnabled(False)
        self.expiry.setText("Remembered wireless session expired. Generate a new code to pair again.")
        self.remote_summary.setText(
            "LIVE COMPANION HEALTH\nWaiting for an authenticated phone snapshot."
        )
        self._last_remote_capture = 0
        if not self._usb_paired:
            self.state.setText("Not paired")
            self.instructions.setText(
                "Generate a code, then enter it in ROMVERSE Companion on your Android phone."
            )

    @Slot()
    def reset_pairing(self) -> None:
        self.transport.reset()
        self._pairing = None
        self._approved = False
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
        self.generate.setEnabled(self.transport.available and not self._usb_paired)
        self.remote_summary.setText(
            "LIVE COMPANION HEALTH\nWaiting for an authenticated phone snapshot."
        )
        if self._usb_paired:
            self.state.setText("USB paired • read-only telemetry enabled")
            self.instructions.setText(
                "Wireless pairing was reset. This authorized phone remains connected through USB read-only mode."
            )
            self.expiry.setText("Wireless pairing reset. USB pairing was not changed.")
        else:
            self.state.setText("Not paired")
            self.instructions.setText(
                "Wireless pairing was reset on this computer. Generate a new code whenever you want to reconnect Companion."
            )
            self.expiry.setText("Wireless pairing reset. Any remembered Companion token is now revoked.")
        self._record_link_note(
            title="Companion Link pairing reset",
            summary="The remembered wireless Companion authorization was revoked locally.",
            explanation="ROMVERSE cleared the pending request, stored session digest, and cached wireless telemetry. USB read-only pairing was not changed.",
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
