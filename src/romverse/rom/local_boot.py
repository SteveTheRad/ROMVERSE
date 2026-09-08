"""Measured, read-only Android boot observation after a local Expert operation.

These receipts describe a live observation window, never image readback, subsystem
health, a signed Guardian execution, or production Device Pack certification.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from time import monotonic
from uuid import UUID, uuid4

from romverse.device.models import AndroidDevice, DeviceState
from romverse.device.parsers import parse_adb_devices
from romverse.guardian.local_flash import LocalFlashResult, LocalFlashService, LocalFlashState
from romverse.guardian.models import GuardianDecision, OperationClass, OperationRequest, RiskLevel
from romverse.guardian.source_installation import (
    SourceInstallationError,
    SourceInstallationResult,
    validate_source_installation_boot_binding,
)
from romverse.infrastructure.local_store import atomic_write_json, read_json_object
from romverse.infrastructure.process import CommandResult
from romverse.rom.models import ProjectError


class LocalBootError(ProjectError):
    pass


class LocalBootStatus(StrEnum):
    WAITING = "waiting"
    SETTLING = "settling"
    STABLE = "stable"
    ATTENTION = "attention"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class LocalBootSession:
    session_id: str
    device_name: str
    masked_serial: str


@dataclass(frozen=True, slots=True)
class LocalBootReport:
    status: LocalBootStatus
    summary: str
    receipt_path: Path
    sample_count: int
    elapsed_seconds: float
    boot_observed: bool
    terminal: bool
    failure_kind: str
    latest_device: AndroidDevice | None


@dataclass(frozen=True, slots=True)
class _Sample:
    tick: float
    uptime: float
    boot_id: str
    identity: tuple[str, str, str, str]
    boot_complete: bool
    device: AndroidDevice


@dataclass(slots=True)
class _SessionState:
    public: LocalBootSession
    target: AndroidDevice
    started: float
    last_tick: float
    started_at: str
    adb_sha256: str
    report: LocalBootReport
    flash_binding: dict[str, str] | None
    flash_result: LocalFlashResult | SourceInstallationResult | None
    samples: list[dict[str, object]] = field(default_factory=list)
    last_probe_tick: float | None = None
    previous: _Sample | None = None
    identity: tuple[str, str, str, str] | None = None
    stable_start: _Sample | None = None
    stable_samples: int = 0
    restarts: int = 0
    boot_observed: bool = False
    last_device: AndroidDevice | None = None
    cancelled: threading.Event = field(default_factory=threading.Event)
    observing: threading.Lock = field(default_factory=threading.Lock)
    data_lock: threading.RLock = field(default_factory=threading.RLock)


class _ObservationIssue(Exception):
    def __init__(self, kind: str, summary: str, *, terminal: bool = False):
        super().__init__(summary)
        self.kind = kind
        self.summary = summary
        self.terminal = terminal


class LocalBootService:
    MAX_RECEIPT_BYTES = 512 * 1024
    MAX_SAMPLES = 256
    PROBE_TIMEOUT_SECONDS = 5
    OBSERVATION_TIMEOUT_SECONDS = 30
    PROPERTIES = (
        "sys.boot_completed",
        "ro.product.device",
        "ro.product.name",
        "ro.build.fingerprint",
        "ro.boot.slot_suffix",
        "ro.bootmode",
    )
    OPTIONAL_PROPERTIES = ("ro.build.version.release", "ro.build.id")

    def __init__(
        self,
        flash_service: LocalFlashService,
        adb_path: Path,
        *,
        monotonic_clock: Callable[[], float] = monotonic,
        utc_clock: Callable[[], datetime] | None = None,
        stable_window_seconds: float = 60,
        timeout_seconds: float = 600,
        minimum_sample_spacing_seconds: float = 5,
    ) -> None:
        values = (stable_window_seconds, timeout_seconds, minimum_sample_spacing_seconds)
        if any(type(value) not in {int, float} or not math.isfinite(value) for value in values):
            raise LocalBootError("Boot observation timing must contain finite numbers.")
        if not (
            1 <= minimum_sample_spacing_seconds <= 60
            and 2 * minimum_sample_spacing_seconds <= stable_window_seconds <= 600
            and stable_window_seconds <= timeout_seconds <= 1800
        ):
            raise LocalBootError("Boot observation timing is outside its supported range.")
        self.flash = flash_service
        self.workspace = flash_service.workspace
        self.adb_path = adb_path
        self.monotonic_clock = monotonic_clock
        self.utc_clock = utc_clock or (lambda: datetime.now(UTC))
        self.stable_window = float(stable_window_seconds)
        self.timeout = float(timeout_seconds)
        self.spacing = float(minimum_sample_spacing_seconds)
        self.maximum_gap = max(15.0, self.spacing * 3)
        self._sessions: dict[str, _SessionState] = {}
        self._sessions_lock = threading.Lock()

    def begin(
        self,
        device: AndroidDevice,
        flash_result: LocalFlashResult | SourceInstallationResult | None = None,
    ) -> LocalBootSession:
        if not isinstance(device, AndroidDevice) or not self.flash.SERIAL.fullmatch(device.serial):
            raise LocalBootError("Choose the exact phone to observe.")
        tool = self._tool()
        now = self._tick()
        started_at = self._utc()
        binding = self._flash_binding(device, flash_result) if flash_result is not None else None
        self.flash.audit.assert_ready()
        session = LocalBootSession(uuid4().hex, device.display_name, device.masked_serial())
        report = LocalBootReport(
            LocalBootStatus.WAITING,
            "Waiting to observe the selected phone through authorized Android debugging.",
            self.workspace / "guardian" / "local-boot" / f"{session.session_id}.json",
            0,
            0.0,
            False,
            False,
            "",
            None,
        )
        state = _SessionState(
            session,
            device,
            now,
            now,
            started_at,
            self.flash._hash_file(tool)[0],
            report,
            binding,
            flash_result,
        )
        with self._sessions_lock:
            if len(self._sessions) >= 32:
                retired = next(
                    (key for key, value in self._sessions.items() if value.report.terminal), None
                )
                if retired is None:
                    raise LocalBootError("Stop an existing boot monitor before opening another.")
                self._sessions.pop(retired)
            self._persist(state, report)
            self._sessions[session.session_id] = state
        return session

    def observe(self, session: LocalBootSession) -> LocalBootReport:
        state = self._state(session)
        if not state.observing.acquire(blocking=False):
            raise LocalBootError("This phone observation is already running.")
        try:
            with state.data_lock:
                if state.report.terminal:
                    return state.report
                now = self._checked_tick(state)
                if now - state.started >= self.timeout:
                    return self._finish_timeout(state, now)
                if state.last_probe_tick is not None and now - state.last_probe_tick < self.spacing:
                    return state.report
                state.last_probe_tick = now
            try:
                if state.flash_result is not None:
                    try:
                        binding = self._flash_binding(state.target, state.flash_result)
                    except (OSError, ValueError, ProjectError):
                        binding = None
                    if binding != state.flash_binding:
                        raise _ObservationIssue(
                            "flash_record_changed",
                            "The linked image-write record changed; begin a fresh monitor with verified evidence.",
                            terminal=True,
                        )
                tool = self._tool()
                if self.flash._hash_file(tool)[0] != state.adb_sha256:
                    raise _ObservationIssue(
                        "tool_changed", "ADB changed; begin a fresh boot monitor.", terminal=True
                    )
                with self.flash._device_lock(state.target.serial):
                    sample = self._sample(
                        state,
                        tool,
                        min(now + self.OBSERVATION_TIMEOUT_SECONDS, state.started + self.timeout),
                    )
                with state.data_lock:
                    if state.report.terminal:
                        return state.report
                    end = self._checked_tick(state)
                    if end - state.started >= self.timeout:
                        return self._finish_timeout(state, end)
                    return self._accept_sample(state, sample, end)
            except _ObservationIssue as exc:
                issue = exc
            except (OSError, ValueError, RuntimeError, ProjectError):
                issue = _ObservationIssue(
                    "evidence_unavailable",
                    "The target, tool, operation record, or audit could not be verified. No boot success is claimed.",
                )
            with state.data_lock:
                if state.report.terminal:
                    return state.report
                end = self._checked_tick(state)
                state.stable_start = None
                state.stable_samples = 0
                state.last_device = None
                if issue.kind == "reboot_during_sample":
                    state.restarts += 1
                    # The next complete sample belongs to the new boot already counted
                    # here. Retain identity independently, but do not count that boot again.
                    state.previous = None
                    if state.restarts >= 2:
                        issue = _ObservationIssue(
                            "reboot_loop",
                            "Repeated restarts interrupted the observations; inspect this phone in Recovery Bay.",
                            terminal=True,
                        )
                state.samples.append(
                    {"elapsed_seconds": end - state.started, "failure_kind": issue.kind}
                )
                if end - state.started >= self.timeout:
                    return self._finish_timeout(state, end)
                return self._publish(
                    state,
                    LocalBootStatus.ATTENTION,
                    issue.summary,
                    end,
                    terminal=issue.terminal,
                    failure_kind=issue.kind,
                )
        finally:
            state.observing.release()

    def stop(self, session: LocalBootSession) -> LocalBootReport:
        state = self._state(session)
        state.cancelled.set()
        with state.data_lock:
            if state.report.terminal:
                return state.report
            return self._publish(
                state,
                LocalBootStatus.CANCELLED,
                "Boot observation stopped. Recorded samples are retained; no phone command was sent by Stop.",
                self._checked_tick(state),
                terminal=True,
                failure_kind="cancelled",
            )

    def _sample(self, state: _SessionState, tool: Path, deadline: float) -> _Sample:
        serial = state.target.serial
        self._discover(state, tool, deadline)
        boot_id = self._run(
            state, tool, ("shell", "cat", "/proc/sys/kernel/random/boot_id"), deadline
        ).stdout.strip()
        try:
            if str(UUID(boot_id)) != boot_id or UUID(boot_id).int == 0:
                raise ValueError
        except ValueError:
            raise _ObservationIssue(
                "boot_identity_unavailable",
                "A valid kernel boot identity is unavailable; a continuous boot cannot be established.",
            ) from None
        props = {
            key: self._run(state, tool, ("shell", "getprop", key), deadline).stdout.strip()
            for key in self.PROPERTIES
        }
        optional: dict[str, str] = {}
        for key in self.OPTIONAL_PROPERTIES:
            try:
                value = self._run(state, tool, ("shell", "getprop", key), deadline).stdout.strip()
            except _ObservationIssue as exc:
                if exc.kind not in {"probe_failed", "probe_malformed", "probe_timeout"}:
                    raise
                value = ""
            optional[key] = value if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", value) else ""
        codename, product = props["ro.product.device"], props["ro.product.name"]
        if any(
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}", value)
            for value in (codename, product)
        ):
            raise _ObservationIssue(
                "identity_unavailable", "Android did not report a usable product identity."
            )
        aliases = {
            value.casefold()
            for value in (state.target.codename, state.target.product, state.target.vendor_device)
            if value
        }
        if aliases and codename.casefold() not in aliases:
            raise _ObservationIssue(
                "identity_changed",
                "The observed Android identity differs from the selected phone.",
                terminal=True,
            )
        fingerprint = props["ro.build.fingerprint"]
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/+,-]{0,511}", fingerprint):
            raise _ObservationIssue(
                "build_unavailable", "The Android build fingerprint is missing or malformed."
            )
        slot = props["ro.boot.slot_suffix"]
        if slot not in {"", "_a", "_b"}:
            raise _ObservationIssue("slot_unavailable", "The Android slot evidence is malformed.")
        bootmode = props["ro.bootmode"].casefold()
        if bootmode in {"recovery", "sideload", "rescue"}:
            raise _ObservationIssue(
                "recovery",
                "The selected phone is in recovery; normal Android boot has not been observed.",
            )
        if bootmode and not re.fullmatch(r"[a-z0-9_-]{1,64}", bootmode):
            raise _ObservationIssue(
                "mode_unavailable", "The reported Android boot mode is malformed."
            )
        if props["sys.boot_completed"] not in {"0", "1"}:
            raise _ObservationIssue(
                "boot_status_unavailable",
                "Android has not supplied a valid boot-complete observation.",
            )
        raw_uptime = self._run(
            state, tool, ("shell", "cat", "/proc/uptime"), deadline
        ).stdout.split()
        tick = self._tick()
        try:
            uptime, idle = map(float, raw_uptime)
            if not (
                math.isfinite(uptime)
                and math.isfinite(idle)
                and 0 <= uptime <= 315360000
                and 0 <= idle <= 1e15
            ):
                raise ValueError
        except (TypeError, ValueError):
            raise _ObservationIssue(
                "uptime_unavailable",
                "Android uptime is missing, malformed, or outside its valid range.",
            ) from None
        # Close the observation around the same transport and boot; a reconnect cannot
        # combine properties from one boot with uptime from another.
        self._discover(state, tool, deadline)
        final_boot = self._run(
            state, tool, ("shell", "cat", "/proc/sys/kernel/random/boot_id"), deadline
        ).stdout.strip()
        if final_boot != boot_id:
            raise _ObservationIssue(
                "reboot_during_sample",
                "The phone restarted during this observation; a new stable window is required.",
            )
        device = AndroidDevice(
            serial=serial,
            state=DeviceState.DEVICE,
            manufacturer=state.target.manufacturer,
            model=state.target.model,
            marketing_name=state.target.marketing_name,
            product=product,
            codename=codename,
            android_version=optional["ro.build.version.release"],
            build_id=optional["ro.build.id"],
            build_fingerprint=fingerprint,
            boot_completed=props["sys.boot_completed"] == "1",
            uptime_seconds=int(uptime),
            slot_suffix=slot,
            connection_note="Fresh read-only local boot observation; subsystem health is untested.",
        )
        return _Sample(
            tick,
            uptime,
            boot_id,
            (codename, product, fingerprint, slot),
            bool(device.boot_completed),
            device,
        )

    def _discover(self, state: _SessionState, tool: Path, deadline: float) -> None:
        result = self._run(state, tool, ("devices", "-l"), deadline, discovery=True)
        rows = [
            row for row in parse_adb_devices(result.stdout) if row["serial"] == state.target.serial
        ]
        if not rows:
            raise _ObservationIssue(
                "device_unavailable",
                "The selected phone is not available through ADB. Waiting for that exact phone.",
            )
        if len(rows) != 1:
            raise _ObservationIssue(
                "ambiguous_target",
                "Multiple ADB rows claim the selected identity. Refresh the target before continuing.",
                terminal=True,
            )
        value = rows[0]["state"]
        if value != "device":
            kind = (
                value
                if value in {"unauthorized", "offline", "recovery", "sideload"}
                else "device_unavailable"
            )
            raise _ObservationIssue(
                kind,
                f"The selected phone is {kind}. Authorized normal Android is required for boot observation.",
            )

    def _accept_sample(self, state: _SessionState, sample: _Sample, now: float) -> LocalBootReport:
        previous = state.previous
        state.samples.append(
            {
                "elapsed_seconds": sample.tick - state.started,
                "uptime_seconds": sample.uptime,
                "boot_complete": sample.boot_complete,
                "boot_id_sha256": _digest(sample.boot_id),
                "identity_sha256": _digest(sample.identity),
                "build_fingerprint_sha256": _digest(sample.identity[2]),
                "slot_suffix": sample.identity[3],
            }
        )
        state.last_device = sample.device
        state.boot_observed = state.boot_observed or sample.boot_complete
        state.previous = sample
        if state.identity is not None and sample.identity != state.identity:
            state.stable_start = None
            return self._publish(
                state,
                LocalBootStatus.ATTENTION,
                "Android identity, build, or slot changed during observation. Begin a fresh monitor for the current phone.",
                now,
                terminal=True,
                failure_kind="identity_changed",
            )
        state.identity = sample.identity
        if previous is not None and sample.boot_id != previous.boot_id:
            state.restarts += 1
            state.stable_start = None
            state.stable_samples = 0
            return self._publish(
                state,
                LocalBootStatus.ATTENTION,
                "Repeated restarts were observed; inspect this phone in Recovery Bay."
                if state.restarts >= 2
                else "The phone restarted or lost boot-complete state. The stable observation window has restarted.",
                now,
                terminal=state.restarts >= 2,
                failure_kind="reboot_loop" if state.restarts >= 2 else "reboot_detected",
            )
        if previous is not None and previous.boot_complete and not sample.boot_complete:
            state.stable_start = None
            state.stable_samples = 0
            return self._publish(
                state,
                LocalBootStatus.ATTENTION,
                "Android no longer reports boot complete. A new stable observation window is required.",
                now,
                failure_kind="boot_complete_lost",
            )
        if not sample.boot_complete:
            state.stable_start = None
            state.stable_samples = 0
            return self._publish(
                state,
                LocalBootStatus.WAITING,
                "The exact phone responds, but Android has not completed booting.",
                now,
            )
        if previous is not None:
            elapsed = sample.tick - previous.tick
            increase = sample.uptime - previous.uptime
            if elapsed <= 0 or increase <= 0 or abs(increase - elapsed) > max(2.0, elapsed * 0.2):
                state.stable_start = None
                state.stable_samples = 0
                return self._publish(
                    state,
                    LocalBootStatus.ATTENTION,
                    "Uptime did not advance coherently with the measured observation interval.",
                    now,
                    failure_kind="uptime_incoherent",
                )
            if elapsed > self.maximum_gap:
                state.stable_start = None
                state.stable_samples = 0
        if state.stable_start is None:
            state.stable_start = sample
            state.stable_samples = 1
        else:
            state.stable_samples += 1
        window = sample.tick - state.stable_start.tick
        advance = sample.uptime - state.stable_start.uptime
        coherent = abs(advance - window) <= max(2.0, window * 0.1)
        stable = window >= self.stable_window and state.stable_samples >= 3 and coherent
        return self._publish(
            state,
            LocalBootStatus.STABLE if stable else LocalBootStatus.SETTLING,
            f"Android boot-complete remained observed across {window:.0f} measured seconds with advancing uptime. Image readback and subsystem health remain unverified."
            if stable
            else f"Android reports boot complete. Observed {window:.0f} of {self.stable_window:.0f} seconds in the current stable window.",
            now,
            terminal=stable,
        )

    def _run(
        self,
        state: _SessionState,
        tool: Path,
        arguments: tuple[str, ...],
        deadline: float,
        *,
        discovery: bool = False,
    ) -> CommandResult:
        if state.cancelled.is_set():
            raise _ObservationIssue("cancelled", "Boot observation stopped.", terminal=True)
        remaining = deadline - self._tick()
        if remaining <= 0:
            raise _ObservationIssue(
                "probe_timeout", "The bounded observation timed out; no boot success is claimed."
            )
        command = (
            (str(tool), *arguments)
            if discovery
            else (str(tool), "-s", state.target.serial, *arguments)
        )
        request = OperationRequest(
            "local-boot.discover" if discovery else "local-boot.observe",
            OperationClass.READ_ONLY,
            str(tool),
            command[1:],
            "Read exact-phone Android boot evidence",
            target="host" if discovery else state.target.serial,
        )
        decision = GuardianDecision(True, RiskLevel.NONE, ("Read-only local boot observation",))
        self.flash.audit.assert_ready()
        began = self._tick()
        try:
            result = self.flash.runner.run(
                command, timeout=min(self.PROBE_TIMEOUT_SECONDS, remaining)
            )
        except Exception as exc:
            self.flash.audit.record(request, decision, None, 0, type(exc).__name__)
            raise _ObservationIssue(
                "probe_failed", "The read-only phone probe did not return a result."
            ) from exc
        self.flash.audit.record(
            request, decision, result, max(0, int((self._tick() - began) * 1000))
        )
        if result.args != command:
            raise _ObservationIssue(
                "wrong_probe_result",
                "The transport returned evidence for a different operation.",
                terminal=True,
            )
        if result.timed_out:
            raise _ObservationIssue("probe_timeout", "The read-only phone probe timed out.")
        if not result.ok:
            raise _ObservationIssue(
                "probe_failed", "A required read-only boot probe is unavailable or denied."
            )
        if len(result.stdout) > (65536 if discovery else 2048):
            raise _ObservationIssue(
                "probe_malformed", "The read-only phone probe exceeded its evidence limit."
            )
        return result

    def _state(self, session: LocalBootSession) -> _SessionState:
        if not isinstance(session, LocalBootSession):
            raise LocalBootError("Choose a live boot observation session.")
        with self._sessions_lock:
            state = self._sessions.get(session.session_id)
        if state is None or state.public is not session:
            raise LocalBootError("This boot session is not owned by the current service.")
        return state

    def _tool(self) -> Path:
        if not isinstance(self.adb_path, Path) or self.adb_path.name.casefold() not in {
            "adb",
            "adb.exe",
        }:
            raise LocalBootError("Choose the ADB executable from Forge Arsenal.")
        path = self.flash._regular_path(self.adb_path.expanduser())
        if os.name != "nt" and not os.access(path, os.X_OK):
            raise LocalBootError("The selected ADB tool is not executable.")
        return path

    def _tick(self) -> float:
        value = self.monotonic_clock()
        if type(value) not in {int, float} or not math.isfinite(value) or value < 0:
            raise LocalBootError("The monotonic observation clock is invalid.")
        return float(value)

    def _checked_tick(self, state: _SessionState) -> float:
        value = self._tick()
        if value < state.last_tick:
            raise LocalBootError("The observation clock moved backwards; begin a fresh monitor.")
        state.last_tick = value
        return value

    def _utc(self) -> str:
        value = self.utc_clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise LocalBootError("The observation timestamp must include a timezone.")
        return value.astimezone(UTC).isoformat()

    def _finish_timeout(self, state: _SessionState, now: float) -> LocalBootReport:
        return self._publish(
            state,
            LocalBootStatus.ATTENTION,
            "The observation deadline passed without a verified stable boot window. Inspect the exact phone in Recovery Bay.",
            now,
            terminal=True,
            failure_kind="boot_timeout",
        )

    def _publish(
        self,
        state: _SessionState,
        status: LocalBootStatus,
        summary: str,
        now: float,
        *,
        terminal: bool = False,
        failure_kind: str = "",
    ) -> LocalBootReport:
        if len(state.samples) >= self.MAX_SAMPLES:
            status, terminal, failure_kind = LocalBootStatus.ATTENTION, True, "sample_limit"
            summary = (
                "The bounded observation sample limit was reached. Start a fresh monitor if needed."
            )
        report = LocalBootReport(
            status,
            summary,
            state.report.receipt_path,
            len(state.samples),
            now - state.started,
            state.boot_observed,
            terminal,
            failure_kind,
            state.last_device,
        )
        try:
            self._persist(state, report)
        except (OSError, ValueError):
            report = LocalBootReport(
                LocalBootStatus.ATTENTION,
                "The current observation could not be preserved. Earlier evidence remains; no stable boot result is claimed.",
                state.report.receipt_path,
                len(state.samples),
                now - state.started,
                state.boot_observed,
                True,
                "persistence_failed",
                state.last_device,
            )
        state.report = report
        return report

    def _persist(self, state: _SessionState, report: LocalBootReport) -> None:
        document = {
            "format": "romverse.local-boot-observation",
            "schema_version": 1,
            "session_id": state.public.session_id,
            "device_key": self.flash.privacy.pseudonym(state.target.serial),
            "started_at": state.started_at,
            "updated_at": self._utc(),
            "adb_sha256": state.adb_sha256,
            "flash_binding": state.flash_binding,
            "status": report.status.value,
            "summary": report.summary,
            "sample_count": report.sample_count,
            "elapsed_seconds": report.elapsed_seconds,
            "boot_observed": report.boot_observed,
            "terminal": report.terminal,
            "failure_kind": report.failure_kind,
            "stable_window_required_seconds": self.stable_window,
            "minimum_sample_spacing_seconds": self.spacing,
            "restarts_observed": state.restarts,
            "samples": state.samples,
            "execution_authority": "none",
            "phone_changed": False,
            "readback_verified": False,
            "subsystems_verified": False,
            "guardian_execution_certified": False,
            "production_certified": False,
        }
        document["record_digest"] = _digest(document)
        atomic_write_json(
            report.receipt_path,
            document,
            boundary=self.workspace,
            maximum_bytes=self.MAX_RECEIPT_BYTES,
        )

    def _flash_binding(
        self, device: AndroidDevice, result: LocalFlashResult | SourceInstallationResult
    ) -> dict[str, str]:
        if isinstance(result, SourceInstallationResult):
            try:
                return validate_source_installation_boot_binding(self.flash, device, result)
            except (SourceInstallationError, OSError, TypeError, ValueError) as exc:
                raise LocalBootError(
                    "The source installation record is not valid for this phone and result."
                ) from exc
        if (
            not isinstance(result, LocalFlashResult)
            or not isinstance(result.state, LocalFlashState)
            or result.boot_verified is not False
            or type(result.phone_change_attempted) is not bool
            or type(result.phone_state_uncertain) is not bool
        ):
            raise LocalBootError("The linked image-write result is not a local transport receipt.")
        path = result.receipt_path
        if (
            not isinstance(path, Path)
            or path.parent != self.flash.root
            or not re.fullmatch(r"[a-f0-9]{32}\.json", path.name)
        ):
            raise LocalBootError(
                "The image-write record is outside its exact local journal directory."
            )
        document = read_json_object(
            path, boundary=self.workspace, maximum_bytes=self.flash.MAX_JOURNAL_BYTES
        )
        digest = document.get("record_digest")
        content = {key: value for key, value in document.items() if key != "record_digest"}
        if (
            not isinstance(digest, str)
            or not re.fullmatch(r"[a-f0-9]{64}", digest)
            or _digest(content) != digest
        ):
            raise LocalBootError("The image-write record digest is invalid.")
        required = {
            "format",
            "schema_version",
            "plan_id",
            "plan_digest",
            "device_key",
            "product",
            "mode",
            "current_slot",
            "fastboot_sha256",
            "writes",
            "warnings",
            "consent",
            "started_at",
            "completed_at",
            "state",
            "summary",
            "in_flight_partition",
            "phone_change_attempted",
            "phone_state_uncertain",
            "boot_verified",
            "readback_verified",
            "external_certification",
            "results",
            "record_digest",
        }
        allowed = required | {"snapshots_verified", "image_snapshots"}
        if not required <= set(document) <= allowed:
            raise LocalBootError("The image-write journal fields do not match the local contract.")
        aliases = {
            value.casefold()
            for value in (device.product, device.codename, device.vendor_device)
            if value
        }
        if (
            document.get("format") != "romverse.local-expert-flash"
            or type(document.get("schema_version")) is not int
            or document["schema_version"] != 1
            or document.get("plan_id") != path.stem
            or document.get("device_key") != self.flash.privacy.pseudonym(device.serial)
            or document.get("consent") != "explicit-expert-exact-plan"
            or not _sha256(document.get("plan_digest"))
            or not _sha256(document.get("fastboot_sha256"))
            or not isinstance(document.get("product"), str)
            or not self.flash.PARTITION.fullmatch(document["product"])
            or (aliases and document["product"].casefold() not in aliases)
            or document.get("state") != result.state.value
            or document.get("summary") != result.summary
            or document.get("phone_change_attempted") is not result.phone_change_attempted
            or document.get("phone_state_uncertain") is not result.phone_state_uncertain
            or any(
                document.get(key) is not False
                for key in ("boot_verified", "readback_verified", "external_certification")
            )
            or _digest(document.get("results"))
            != _digest([asdict(item) for item in result.results])
        ):
            raise LocalBootError("The image-write record does not match this phone and result.")
        if (
            _timestamp(document["completed_at"]) < _timestamp(document["started_at"])
            or result.phone_state_uncertain != result.phone_change_attempted
            or (result.results and not result.phone_change_attempted)
            or (result.state is LocalFlashState.REJECTED and result.phone_change_attempted)
        ):
            raise LocalBootError("The image-write completion evidence is inconsistent.")
        writes, results = document.get("writes"), document.get("results")
        if (
            not isinstance(writes, list)
            or not 1 <= len(writes) <= self.flash.MAX_WRITES
            or not isinstance(results, list)
            or len(results) > len(writes)
        ):
            raise LocalBootError("The image-write record has invalid operation counts.")
        write_fields = {
            "partition",
            "image_name",
            "size_bytes",
            "expanded_size_bytes",
            "sha256",
            "partition_size_bytes",
            "is_logical",
            "has_slot",
        }
        partitions: set[str] = set()
        for write in writes:
            if (
                not isinstance(write, dict)
                or set(write) != write_fields
                or not isinstance(write["partition"], str)
                or not self.flash.PARTITION.fullmatch(write["partition"])
                or write["partition"] in partitions
                or not _sha256(write["sha256"])
                or any(
                    type(write[key]) is not int or not 1 <= write[key] < 2**63
                    for key in ("size_bytes", "expanded_size_bytes")
                )
                or (
                    write["partition_size_bytes"] is not None
                    and (
                        type(write["partition_size_bytes"]) is not int
                        or not 0 <= write["partition_size_bytes"] < 2**63
                    )
                )
                or any(
                    write[key] is not None and type(write[key]) is not bool
                    for key in ("is_logical", "has_slot")
                )
            ):
                raise LocalBootError("The image-write plan is malformed.")
            partitions.add(write["partition"])
        if document["in_flight_partition"] and document["in_flight_partition"] not in partitions:
            raise LocalBootError("The interrupted image write is not part of its plan.")
        if "image_snapshots" in document or "snapshots_verified" in document:
            expected_snapshots = {
                write["sha256"]: {
                    "relative_path": str(
                        Path("guardian")
                        / "local-flash"
                        / "images"
                        / path.stem
                        / f"{write['sha256']}.img"
                    ),
                    "sha256": write["sha256"],
                    "size_bytes": write["size_bytes"],
                }
                for write in writes
            }
            if (
                type(document.get("snapshots_verified")) is not bool
                or document.get("image_snapshots") != list(expected_snapshots.values())
                or (result.phone_change_attempted and document["snapshots_verified"] is not True)
            ):
                raise LocalBootError(
                    "The image snapshot references do not match their approved plan."
                )
        for index, item in enumerate(results):
            write = writes[index]
            if (
                not isinstance(item, dict)
                or set(item)
                != {
                    "partition",
                    "image_sha256",
                    "command",
                    "started_at",
                    "completed_at",
                    "returncode",
                    "timed_out",
                    "output",
                }
                or not isinstance(write, dict)
                or item.get("partition") != write.get("partition")
                or item.get("image_sha256") != write.get("sha256")
                or type(item.get("returncode")) is not int
                or type(item.get("timed_out")) is not bool
                or item.get("command")
                != ["fastboot", "-s", "<device>", "flash", write["partition"], "<image>"]
            ):
                raise LocalBootError("The image-write results do not match their ordered plan.")
            if _timestamp(item["completed_at"]) < _timestamp(item["started_at"]):
                raise LocalBootError("The image-write result timestamps are inconsistent.")
        if result.state is LocalFlashState.COMPLETED and (
            len(results) != len(writes)
            or not result.phone_change_attempted
            or not all(item.completed for item in result.results)
        ):
            raise LocalBootError("The completed image-write record has incomplete results.")
        return {
            "relative_path": path.relative_to(self.workspace).as_posix(),
            "record_digest": digest,
            "plan_digest": str(document["plan_digest"]),
            "device_key": str(document["device_key"]),
        }


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise LocalBootError("An image-write timestamp is invalid.")
    try:
        observed = datetime.fromisoformat(value)
        if observed.tzinfo is None or observed.utcoffset() is None:
            raise ValueError
        return observed.astimezone(UTC)
    except (ValueError, OverflowError) as exc:
        raise LocalBootError("An image-write timestamp is invalid.") from exc
