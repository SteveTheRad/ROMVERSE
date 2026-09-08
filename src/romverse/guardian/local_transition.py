"""Explicit local device-mode changes followed by exact-target observation."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from romverse.device.models import AndroidDevice, DeviceState
from romverse.device.parsers import parse_adb_devices, parse_getprop
from romverse.guardian.local_flash import LocalFlashError, LocalFlashService, LocalFlashState
from romverse.guardian.models import GuardianDecision, OperationClass, OperationRequest, RiskLevel
from romverse.infrastructure.local_store import (
    LocalStoreConflictError,
    atomic_write_json,
    exclusive_create_json,
)
from romverse.infrastructure.process import CommandResult


class LocalTransitionTarget(StrEnum):
    BOOTLOADER = "bootloader"
    FASTBOOTD = "fastbootd"
    ANDROID = "android"


@dataclass(frozen=True, slots=True)
class LocalTransitionTool:
    name: str
    path: Path = field(repr=False)
    sha256: str


@dataclass(frozen=True, slots=True)
class LocalTransitionPlan:
    plan_digest: str
    plan_id: str
    created_at: str
    expires_at: str
    device_name: str
    masked_serial: str
    source_mode: str
    target: LocalTransitionTarget
    warnings: tuple[str, ...]
    command: tuple[str, ...]
    device_key: str
    tools: tuple[LocalTransitionTool, ...]
    source_device: AndroidDevice = field(repr=False)


@dataclass(frozen=True, slots=True)
class LocalTransitionResult:
    state: LocalFlashState
    summary: str
    phone_change_attempted: bool
    receipt_path: Path
    observed_device: AndroidDevice | None = None
    arrival_verified: bool = False
    boot_verified: bool = False
    command_completed: bool = False


class _Cancelled(LocalFlashError):
    pass


class _SuccessfulEmptyFastbootProduct(LocalFlashError):
    """One exact Fastboot transport returned success without product evidence."""


class LocalDeviceTransitionService:
    """One approved reboot command; never infer a different phone after USB changes.

    Inspection and arrival probes share the image writer's device lock and audit.
    Arrival means only that the selected serial and product appeared in the requested
    transport; it does not prove Android first boot or a healthy operating system.
    """

    PLAN_VALID_SECONDS = 120
    ARRIVAL_TIMEOUT_SECONDS = 45
    COMMAND_TIMEOUT_SECONDS = 10
    PROBE_TIMEOUT_SECONDS = 4
    POLL_INTERVAL_SECONDS = 0.5
    MAX_JOURNAL_BYTES = 128 * 1024

    def __init__(
        self,
        flash_service: LocalFlashService,
        adb_path: Path | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] | None = None,
        sleeper: Callable[[float], None] | None = None,
        arrival_timeout_seconds: float = ARRIVAL_TIMEOUT_SECONDS,
    ) -> None:
        if not 0 < arrival_timeout_seconds <= self.ARRIVAL_TIMEOUT_SECONDS:
            raise ValueError("Device arrival observation must be bounded by 45 seconds")
        self.flash_service = flash_service
        self.adb_path = adb_path
        self.clock = clock or (lambda: datetime.now(UTC))
        self.monotonic = monotonic or time.monotonic
        self.sleeper = sleeper or time.sleep
        self.arrival_timeout_seconds = float(arrival_timeout_seconds)
        self.root = flash_service.workspace / "guardian" / "local-transitions"
        self._plans: dict[str, LocalTransitionPlan] = {}
        self._plan_lock = threading.Lock()

    def inspect(self, device: AndroidDevice, target: LocalTransitionTarget) -> LocalTransitionPlan:
        if not isinstance(target, LocalTransitionTarget):
            raise LocalFlashError("Choose Android, bootloader Fastboot or Fastbootd.")
        if not isinstance(device, AndroidDevice) or not self.flash_service.SERIAL.fullmatch(
            device.serial
        ):
            raise LocalFlashError("Select a phone with an exact USB identity.")
        if device.transport not in {"usb", "usb-fastboot"}:
            raise LocalFlashError("Connect this phone by USB before changing its boot mode.")
        if device.state is not DeviceState.DEVICE and not device.is_fastboot:
            raise LocalFlashError(
                "Authorize the phone in Android, or connect it in Fastboot, before reviewing a mode change."
            )
        if not device.product and not device.codename:
            raise LocalFlashError(
                "Refresh Device DNA to record the selected phone's product identity first."
            )
        source_adb = device.state is DeviceState.DEVICE
        tools = self._required_tools(source_adb, target)
        warnings = [
            "This sends one reboot command to the selected phone. Save work on the phone before continuing.",
            "Only transport arrival will be verified. Android first boot, image integrity and subsystem health require separate checks.",
            "If USB presents a different serial after reboot, refresh and identify the phone manually; ROMVERSE will not guess a replacement target.",
        ]
        with self.flash_service._device_lock(device.serial):
            observed = (
                self._observe_source(device, tools, True)
                if source_adb
                else self._observe_fastboot_source_pair(device, tools)
            )
            if observed is None:
                raise LocalFlashError(
                    "The selected phone is no longer in its reviewed mode. Refresh devices and try again."
                )
            source_mode = self._mode(observed)
            if source_mode == target.value and target is not LocalTransitionTarget.ANDROID:
                raise LocalFlashError(
                    f"The selected phone is already in {target.value}. Refresh it and continue with the image review."
                )
            if source_mode == "fastboot":
                warnings.append(
                    "Fastboot did not identify its current userspace mode. The destination must still be measured before the change can be called complete."
                )
            if source_adb and self._observe_source(device, tools, True) != observed:
                raise LocalFlashError(
                    "The phone identity changed during inspection. Refresh and review again."
                )
        created = self._now()
        plan = LocalTransitionPlan(
            plan_digest="",
            plan_id=uuid4().hex,
            created_at=created.isoformat(),
            expires_at=(created + timedelta(seconds=self.PLAN_VALID_SECONDS)).isoformat(),
            device_name=device.display_name,
            masked_serial=device.masked_serial(),
            source_mode=source_mode,
            target=target,
            warnings=tuple(warnings),
            command=self._command(source_mode, target, "<selected-phone>"),
            device_key=self.flash_service.privacy.pseudonym(device.serial),
            tools=tools,
            source_device=observed,
        )
        plan = replace(plan, plan_digest=self._digest_plan(plan))
        with self._plan_lock:
            if len(self._plans) >= 128:
                self._plans.pop(next(iter(self._plans)))
            self._plans[plan.plan_digest] = plan
        return plan

    def execute(
        self,
        plan: LocalTransitionPlan,
        *,
        accepted_digest: str,
        risk_accepted: bool,
        should_cancel: Callable[[], bool] | None = None,
        progress: Callable[[int, int, str], None] | None = None,
    ) -> LocalTransitionResult:
        self._confirmation(plan, accepted_digest, risk_accepted)
        cancel = should_cancel or (lambda: False)
        notify = progress or (lambda _done, _total, _message: None)
        with self.flash_service._device_lock(plan.source_device.serial):
            self._confirmation(plan, accepted_digest, risk_accepted)
            path = self.root / f"{plan.plan_id}.json"
            journal = self._journal(plan)
            try:
                exclusive_create_json(
                    path,
                    journal,
                    boundary=self.flash_service.workspace,
                    maximum_bytes=self.MAX_JOURNAL_BYTES,
                )
            except LocalStoreConflictError as exc:
                raise LocalFlashError(
                    "This mode-change confirmation was already used. Review a new one."
                ) from exc
            with self._plan_lock:
                self._plans.pop(plan.plan_digest, None)
            attempted = False
            command_completed = False
            arrived: AndroidDevice | None = None
            state = LocalFlashState.REJECTED
            summary = "No mode-change command started."
            try:
                if cancel():
                    raise _Cancelled
                self._revalidate(plan)
                notify(0, 1, f"Changing to {plan.target.value}…")
                self._revalidate(plan)
                if cancel():
                    raise _Cancelled
                self._confirmation_age(plan)
                journal["state"] = "command-in-flight"
                journal["phone_change_attempted"] = True
                journal["phone_state_uncertain"] = True
                self._save(path, journal)
                attempted = True
                logical = self._command(plan.source_mode, plan.target, plan.source_device.serial)
                tool = next(tool.path for tool in plan.tools if tool.name == logical[0])
                command = (str(tool), *logical[1:])
                result = self._run(
                    command,
                    write=True,
                    approval=plan.plan_digest,
                    timeout=self.COMMAND_TIMEOUT_SECONDS,
                )
                command_completed = result.ok
                journal["command_completed"] = command_completed
                journal["command_result"] = {
                    "returncode": result.returncode,
                    "timed_out": result.timed_out,
                    "output": self._scrub(result.stdout + "\n" + result.stderr, plan),
                }
                journal["state"] = "awaiting-arrival"
                self._save(path, journal)
                if not result.ok:
                    raise LocalFlashError(
                        "The reboot command did not return success. Refresh the phone to establish its actual state."
                    )
                arrived = self._await_arrival(plan, journal, path, cancel, notify)
                if arrived is None:
                    raise LocalFlashError(
                        f"The exact selected phone did not appear in {plan.target.value} within {self.arrival_timeout_seconds:g} seconds. It may still be rebooting, need USB authorization or use a different serial; refresh and identify it manually."
                    )
                state = LocalFlashState.COMPLETED
                summary = (
                    f"The selected phone is now visible in {plan.target.value}. "
                    "This verifies transport arrival only; Android boot and subsystem health have not been verified."
                )
            except _Cancelled:
                state = LocalFlashState.CANCELLED
                summary = (
                    "Stopped observing at your request. The reboot command was already sent; refresh the phone to see its current state."
                    if attempted
                    else "Cancelled before the mode-change command."
                )
            except Exception as exc:
                state = LocalFlashState.FAILED if attempted else LocalFlashState.REJECTED
                summary = self._scrub(str(exc), plan)
            output = LocalTransitionResult(
                state,
                summary,
                attempted,
                path,
                arrived,
                arrived is not None,
                command_completed=command_completed,
            )
            journal.update(
                state=state.value,
                summary=summary,
                completed_at=self._now().isoformat(),
                phone_change_attempted=attempted,
                phone_state_uncertain=attempted and arrived is None,
                arrival_verified=arrived is not None,
                command_completed=command_completed,
                observation=self._public_observation(arrived),
            )
            try:
                self._save(path, journal)
            except OSError:
                return replace(
                    output,
                    state=LocalFlashState.FAILED,
                    arrival_verified=False,
                    summary="The final transition record could not be saved. Preserve the journal and refresh the phone to establish its state.",
                )
            return output

    def _await_arrival(
        self,
        plan: LocalTransitionPlan,
        journal: dict[str, object],
        path: Path,
        cancel: Callable[[], bool],
        notify: Callable[[int, int, str], None],
    ) -> AndroidDevice | None:
        deadline = self.monotonic() + self.arrival_timeout_seconds
        needs_departure = plan.source_mode == plan.target.value
        departed = not needs_departure
        observations = 0
        while self.monotonic() < deadline:
            if cancel():
                raise _Cancelled
            self._verify_tools(plan.tools)
            if plan.target is LocalTransitionTarget.ANDROID:
                if needs_departure and not departed:
                    # A failed property read is not proof that Android disconnected.
                    # Only a successful discovery showing the authorized transport gone
                    # can establish the departure needed for an Android-to-Android reboot.
                    present = self._adb_present(plan.source_device, plan.tools, deadline)
                    departed = present is False
                observed = (
                    self._adb_observe(plan.source_device, plan.tools, deadline=deadline)
                    if departed
                    else None
                )
            else:
                observed = self._fastboot_observe(plan.source_device, plan.tools, deadline=deadline)
                if observed is not None:
                    journal["last_seen_device"] = self._public_observation(observed)
                if observed is not None and self._mode(observed) != plan.target.value:
                    observed = None
            if observed is not None:
                journal["last_seen_device"] = self._public_observation(observed)
            observations += 1
            journal["arrival_observation_count"] = observations
            journal["source_departure_observed"] = departed if needs_departure else None
            journal["last_observation_at"] = self._now().isoformat()
            self._save(path, journal)
            if cancel():
                raise _Cancelled
            if observed is not None and departed:
                notify(1, 1, f"The selected phone appeared in {plan.target.value}.")
                return observed
            notify(0, 1, f"Waiting for the selected phone in {plan.target.value}…")
            remaining = deadline - self.monotonic()
            if remaining > 0:
                self.sleeper(min(self.POLL_INTERVAL_SECONDS, remaining))
        return None

    def _observe_source(
        self, expected: AndroidDevice, tools: tuple[LocalTransitionTool, ...], adb: bool
    ) -> AndroidDevice | None:
        return (
            self._adb_observe(expected, tools) if adb else self._fastboot_observe(expected, tools)
        )

    def _observe_fastboot_source_pair(
        self,
        expected: AndroidDevice,
        tools: tuple[LocalTransitionTool, ...],
    ) -> AndroidDevice:
        """Require two complete identical Fastboot observations before plan creation.

        One successful but completely empty product response may be reacquired. The
        reacquisition is a new discovery/product/mode sequence and contributes no
        evidence itself. Every other missing, malformed, changed or failed observation
        remains a command-free rejection.
        """

        complete: list[AndroidDevice] = []
        empty_product_reacquired = False
        while len(complete) < 2:
            try:
                observed = self._fastboot_observe(
                    expected,
                    tools,
                    signal_successful_empty_product=True,
                    require_known_mode=True,
                )
            except _SuccessfulEmptyFastbootProduct as exc:
                if empty_product_reacquired:
                    raise LocalFlashError(
                        "Fastboot product identity remained unavailable after one fresh reacquisition."
                    ) from exc
                empty_product_reacquired = True
                continue
            if observed is None:
                raise LocalFlashError(
                    "The selected phone is no longer in its reviewed mode. Refresh devices and try again."
                )
            complete.append(observed)
        if complete[0] != complete[1]:
            raise LocalFlashError(
                "The phone identity or Fastboot mode changed during inspection. Refresh and review again."
            )
        return complete[0]

    def _adb_observe(
        self,
        expected: AndroidDevice,
        tools: tuple[LocalTransitionTool, ...],
        *,
        deadline: float | None = None,
    ) -> AndroidDevice | None:
        tool = self._find_tool(tools, "adb")
        if self._adb_present(expected, tools, deadline) is not True:
            return None
        response = self._probe((str(tool), "-s", expected.serial, "shell", "getprop"), deadline)
        if response is None or not response.ok:
            return None
        properties = parse_getprop(response.stdout)
        product = properties.get("ro.product.name", "")
        codename = properties.get("ro.product.device", "")
        self._identity(expected, product, codename)
        boot_mode = properties.get("ro.bootmode", "").casefold()
        if boot_mode in {"recovery", "sideload", "rescue"}:
            # Some recoveries advertise a regular ADB "device" row. That transport
            # alone is not evidence that the requested normal Android mode arrived.
            return None
        if boot_mode and not re.fullmatch(r"[a-z0-9_-]{1,64}", boot_mode):
            raise LocalFlashError("The selected phone reported an invalid Android boot mode.")
        return AndroidDevice(
            serial=expected.serial,
            state=DeviceState.DEVICE,
            transport="usb",
            manufacturer=properties.get("ro.product.manufacturer", ""),
            model=properties.get("ro.product.model", ""),
            product=product,
            codename=codename,
            android_version=properties.get("ro.build.version.release", ""),
            build_id=properties.get("ro.build.id", ""),
            build_fingerprint=properties.get("ro.build.fingerprint", ""),
            slot_suffix=properties.get("ro.boot.slot_suffix", ""),
            connection_note="Authorized Android transport observed after exact product matching; boot health is not verified.",
        )

    def _adb_present(
        self,
        expected: AndroidDevice,
        tools: tuple[LocalTransitionTool, ...],
        deadline: float | None,
    ) -> bool | None:
        tool = self._find_tool(tools, "adb")
        discovery = self._probe((str(tool), "devices", "-l"), deadline)
        if discovery is None or not discovery.ok:
            return None
        rows = [
            row
            for row in parse_adb_devices(discovery.stdout)
            if row.get("serial") == expected.serial
        ]
        if len(rows) > 1:
            raise LocalFlashError(
                "The selected ADB serial identifies more than one target. Re-identify the phone manually."
            )
        return bool(rows and rows[0].get("state") == "device")

    def _fastboot_observe(
        self,
        expected: AndroidDevice,
        tools: tuple[LocalTransitionTool, ...],
        *,
        deadline: float | None = None,
        signal_successful_empty_product: bool = False,
        require_known_mode: bool = False,
    ) -> AndroidDevice | None:
        tool = self._find_tool(tools, "fastboot")
        discovery = self._probe((str(tool), "devices", "-l"), deadline)
        if discovery is None or not discovery.ok:
            return None
        rows = [
            parts
            for line in (discovery.stdout + "\n" + discovery.stderr).splitlines()
            if (parts := line.split())
            and len(parts) >= 2
            and parts[0] == expected.serial
            and parts[1].casefold() == "fastboot"
        ]
        if len(rows) > 1:
            raise LocalFlashError(
                "The selected Fastboot serial is ambiguous. Re-identify the phone manually."
            )
        if not rows:
            return None
        product = self._getvar(
            tool,
            expected.serial,
            "product",
            deadline,
            signal_successful_empty=signal_successful_empty_product,
        )
        if not product:
            return None
        # Fastboot reports a product, not Android's ro.product.device. Preserve
        # its legitimate product alias without inventing a contradictory codename.
        self._identity(expected, product, "")
        mode = self._getvar(tool, expected.serial, "is-userspace", deadline)
        if require_known_mode and mode.casefold() not in {"yes", "true", "1", "no", "false", "0"}:
            raise LocalFlashError(
                "Fastboot did not report a complete bootloader/userspace mode identity."
            )
        state = (
            DeviceState.FASTBOOTD
            if mode.casefold() in {"yes", "true", "1"}
            else DeviceState.BOOTLOADER
            if mode.casefold() in {"no", "false", "0"}
            else DeviceState.FASTBOOT
        )
        return AndroidDevice(
            serial=expected.serial,
            state=state,
            transport="usb",
            manufacturer=expected.manufacturer,
            model=expected.model,
            product=product,
            # Retain the already-reviewed hardware codename across a transport
            # that exposes only a product alias; otherwise a valid return to
            # Android would contradict our own invented codename.
            codename=expected.codename or product,
            connection_note="Exact Fastboot product and transport observed; no image or boot verification performed.",
        )

    def _getvar(
        self,
        tool: Path,
        serial: str,
        variable: str,
        deadline: float | None,
        *,
        signal_successful_empty: bool = False,
    ) -> str:
        result = self._probe((str(tool), "-s", serial, "getvar", variable), deadline)
        if result is None or not result.ok:
            return ""
        if signal_successful_empty and not (result.stdout + result.stderr).strip():
            raise _SuccessfulEmptyFastbootProduct(
                "Fastboot returned success without current product identity."
            )
        matcher = re.compile(
            r"^(?:\(bootloader\)\s*)?" + re.escape(variable) + r"\s*:\s*(.*?)\s*$", re.IGNORECASE
        )
        values = {
            match.group(1)
            for line in (result.stdout + "\n" + result.stderr).splitlines()
            if (match := matcher.fullmatch(line.strip()))
        }
        if len(values) > 1:
            raise LocalFlashError(f"The phone returned conflicting {variable} values.")
        return next(iter(values)) if values else ""

    @staticmethod
    def _identity(expected: AndroidDevice, product: str, codename: str) -> None:
        known = {value.casefold() for value in (expected.product, expected.codename) if value}
        observed = {value.casefold() for value in (product, codename) if value}
        if not known or not observed:
            raise LocalFlashError(
                "The selected phone did not report usable product identity. Refresh Device DNA."
            )
        if any(not LocalFlashService.PARTITION.fullmatch(value) for value in observed):
            raise LocalFlashError("The selected phone returned an invalid product identity.")
        if (
            expected.codename and codename and expected.codename.casefold() != codename.casefold()
        ) or not known.intersection(observed):
            raise LocalFlashError(
                "The device product differs from the reviewed phone. Re-identify the target manually."
            )

    def _required_tools(
        self, source_adb: bool, target: LocalTransitionTarget
    ) -> tuple[LocalTransitionTool, ...]:
        names = set()
        if source_adb or target is LocalTransitionTarget.ANDROID:
            names.add("adb")
        if not source_adb or target is not LocalTransitionTarget.ANDROID:
            names.add("fastboot")
        result = []
        for name in sorted(names):
            path = self._tool(name)
            result.append(LocalTransitionTool(name, path, self.flash_service._hash_file(path)[0]))
        return tuple(result)

    def _tool(self, name: str) -> Path:
        if name == "fastboot":
            return self.flash_service._tool()
        if self.adb_path is None:
            raise LocalFlashError(
                "Verify ADB in Forge Arsenal so ROMVERSE can observe Android before or after the mode change."
            )
        path = self.flash_service._regular_path(self.adb_path.expanduser())
        if path.name.casefold() not in {"adb", "adb.exe"} or (
            os.name != "nt" and not os.access(path, os.X_OK)
        ):
            raise LocalFlashError(
                "The selected ADB tool is not a regular executable. Repair it in Forge Arsenal."
            )
        return path

    def _verify_tools(self, tools: tuple[LocalTransitionTool, ...]) -> None:
        for tool in tools:
            if (
                self._tool(tool.name) != tool.path
                or self.flash_service._hash_file(tool.path)[0] != tool.sha256
            ):
                raise LocalFlashError(
                    "An Android tool changed after this mode change was reviewed. Inspect again."
                )

    def _revalidate(self, plan: LocalTransitionPlan) -> None:
        self._verify_tools(plan.tools)
        observed = self._observe_source(
            plan.source_device, plan.tools, plan.source_mode == "android"
        )
        if observed is None or self._mode(observed) != plan.source_mode:
            raise LocalFlashError(
                "The phone changed mode or disconnected after review. Refresh and review again."
            )
        if (
            observed.product,
            observed.codename,
            observed.build_fingerprint,
            observed.slot_suffix,
        ) != (
            plan.source_device.product,
            plan.source_device.codename,
            plan.source_device.build_fingerprint,
            plan.source_device.slot_suffix,
        ):
            raise LocalFlashError(
                "The phone identity changed after review. Refresh and review again."
            )

    def _probe(self, command: tuple[str, ...], deadline: float | None) -> CommandResult | None:
        remaining = (
            self.PROBE_TIMEOUT_SECONDS
            if deadline is None
            else min(self.PROBE_TIMEOUT_SECONDS, deadline - self.monotonic())
        )
        if remaining <= 0:
            return None
        return self._run(command, timeout=remaining)

    def _run(
        self, command: tuple[str, ...], *, timeout: float, write: bool = False, approval: str = ""
    ) -> CommandResult:
        serial = command[2] if len(command) > 2 and command[1] == "-s" else "host"
        request = OperationRequest(
            operation_id="local-transition.reboot" if write else "local-transition.observe",
            category=OperationClass.STATE_CHANGING if write else OperationClass.READ_ONLY,
            executable=command[0],
            arguments=command[1:],
            target=serial,
            purpose="Execute one explicitly reviewed device reboot"
            if write
            else "Observe the exact selected device transport and identity",
            approval_digest=approval,
        )
        decision = GuardianDecision(
            True,
            RiskLevel.MEDIUM if write else RiskLevel.NONE,
            (
                "Confirmed exact local mode change"
                if write
                else "Read-only transport and identity observation",
            ),
            user_approval_required=write,
        )
        audit = self.flash_service.audit
        audit.assert_ready()
        started = self.monotonic()
        try:
            result = self.flash_service.runner.run(command, timeout=timeout)
        except Exception as exc:
            audit.record(
                request,
                decision,
                None,
                int((self.monotonic() - started) * 1000),
                type(exc).__name__,
            )
            raise LocalFlashError(
                "The device command returned no measurable result. Refresh the phone before continuing."
            ) from exc
        audit.record(request, decision, result, int((self.monotonic() - started) * 1000))
        if result.args != command:
            raise LocalFlashError("The tool result belongs to a different command.")
        return result

    @staticmethod
    def _command(source_mode: str, target: LocalTransitionTarget, serial: str) -> tuple[str, ...]:
        executable = "adb" if source_mode == "android" else "fastboot"
        suffix = (
            ("bootloader",)
            if target is LocalTransitionTarget.BOOTLOADER
            else ("fastboot",)
            if target is LocalTransitionTarget.FASTBOOTD
            else ()
        )
        return (executable, "-s", serial, "reboot", *suffix)

    @staticmethod
    def _mode(device: AndroidDevice) -> str:
        return "android" if device.state is DeviceState.DEVICE else device.state.value

    @staticmethod
    def _find_tool(tools: tuple[LocalTransitionTool, ...], name: str) -> Path:
        tool = next((tool for tool in tools if tool.name == name), None)
        if tool is None:
            raise LocalFlashError(f"The reviewed {name} executable is unavailable.")
        return tool.path

    def _confirmation(
        self, plan: LocalTransitionPlan, accepted_digest: str, risk_accepted: bool
    ) -> None:
        if (
            risk_accepted is not True
            or not isinstance(plan, LocalTransitionPlan)
            or not isinstance(accepted_digest, str)
            or not hmac.compare_digest(accepted_digest, plan.plan_digest)
        ):
            raise LocalFlashError(
                "Confirm the exact displayed mode change before sending a reboot command."
            )
        with self._plan_lock:
            if self._plans.get(plan.plan_digest) != plan:
                raise LocalFlashError(
                    "This mode-change preview changed or was already used. Inspect a new plan."
                )
        if self._digest_plan(plan) != plan.plan_digest:
            raise LocalFlashError("The mode-change preview changed. Inspect a new plan.")
        self._confirmation_age(plan)

    def _confirmation_age(self, plan: LocalTransitionPlan) -> None:
        if (
            not datetime.fromisoformat(plan.created_at)
            <= self._now()
            < datetime.fromisoformat(plan.expires_at)
        ):
            raise LocalFlashError(
                "The mode-change preview expired. Inspect the current phone again."
            )

    @staticmethod
    def _digest_plan(plan: LocalTransitionPlan) -> str:
        payload = asdict(plan)
        payload.pop("plan_digest")
        return _digest(payload)

    def _now(self) -> datetime:
        moment = self.clock()
        if moment.tzinfo is None or moment.utcoffset() is None:
            raise LocalFlashError("The transition clock must include a time zone.")
        return moment.astimezone(UTC)

    def _journal(self, plan: LocalTransitionPlan) -> dict[str, object]:
        payload: dict[str, object] = {
            "format": "romverse.local-expert-transition",
            "schema_version": 1,
            "plan_id": plan.plan_id,
            "plan_digest": plan.plan_digest,
            "device_key": plan.device_key,
            "product": plan.source_device.product,
            "codename": plan.source_device.codename,
            "source_mode": plan.source_mode,
            "target_mode": plan.target.value,
            "command": plan.command,
            "tools": [{"name": tool.name, "sha256": tool.sha256} for tool in plan.tools],
            "consent": "explicit-expert-exact-transition",
            "started_at": self._now().isoformat(),
            "state": "preparing",
            "phone_change_attempted": False,
            "command_completed": False,
            "phone_state_uncertain": False,
            "arrival_verified": False,
            "boot_verified": False,
            "warnings": plan.warnings,
            "arrival_observation_count": 0,
        }
        payload["record_digest"] = _digest(payload)
        return payload

    def _save(self, path: Path, journal: dict[str, object]) -> None:
        payload = dict(journal)
        payload.pop("record_digest", None)
        payload["record_digest"] = _digest(payload)
        atomic_write_json(
            path,
            payload,
            boundary=self.flash_service.workspace,
            maximum_bytes=self.MAX_JOURNAL_BYTES,
        )

    @staticmethod
    def _public_observation(device: AndroidDevice | None) -> dict[str, object] | None:
        if device is None:
            return None
        return {
            "mode": device.state.value,
            "product": device.product,
            "codename": device.codename,
            "boot_verified": False,
        }

    @staticmethod
    def _scrub(value: str, plan: LocalTransitionPlan) -> str:
        text = value[-8192:].replace(plan.source_device.serial, "<private-device>")
        for tool in plan.tools:
            text = text.replace(str(tool.path), "<private-tool>")
        text = re.sub(
            r"(?:[A-Za-z]:[\\/]|/)(?:[^\s\"'<>]+[\\/])*[^\s\"'<>]*", "<private-path>", text
        )
        text = re.sub(r"\b(?:[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\d{14,20})\b", "<private>", text)
        text = re.sub(
            r"(?i)\b(?:token|password|secret|imei|serial)\s*[:=]\s*\S+", "<private>", text
        )
        return "".join(char for char in text if char in "\n\t" or ord(char) >= 32).strip()


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
