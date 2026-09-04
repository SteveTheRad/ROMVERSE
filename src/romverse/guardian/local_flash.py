"""Local, explicitly approved image writes with honest transport-level evidence.

This is an Expert Mode operation, not a production Device Pack certification. The
user supplies the image-to-partition mapping. No mode transition or slot selection
is inferred and a completed Fastboot command never becomes proof of a healthy boot.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shutil
import stat
import struct
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from time import monotonic
from uuid import uuid4

from romverse.core.privacy import WorkspacePrivacy
from romverse.device.models import AndroidDevice
from romverse.device.parsers import parse_fastboot_devices
from romverse.guardian.audit import GuardianAuditStore
from romverse.guardian.models import (
    GuardianDecision,
    OperationClass,
    OperationRequest,
    RiskLevel,
)
from romverse.infrastructure.local_store import (
    LocalStoreConflictError,
    atomic_write_json,
    ensure_private_directory,
    exclusive_create_json,
)
from romverse.infrastructure.process import CommandResult, CommandRunner
from romverse.rom.models import ProjectError


class LocalFlashError(ProjectError):
    """A selected local operation cannot run as reviewed."""


class _Cancelled(LocalFlashError):
    pass


class LocalFlashState(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class LocalFlashSelection:
    partition: str
    image_path: Path


@dataclass(frozen=True, slots=True)
class LocalFlashWrite:
    partition: str
    image_path: Path = field(repr=False)
    image_name: str
    size_bytes: int
    expanded_size_bytes: int
    sha256: str
    partition_size_bytes: int | None
    is_logical: bool | None
    has_slot: bool | None


@dataclass(frozen=True, slots=True)
class LocalFlashPlan:
    plan_digest: str
    plan_id: str
    inspected_at: str
    device_name: str
    masked_serial: str
    product: str
    mode: str
    current_slot: str
    unlocked: bool | None
    writes: tuple[LocalFlashWrite, ...]
    warnings: tuple[str, ...]
    device_key: str
    serial: str = field(repr=False)
    fastboot_path: Path = field(repr=False)
    fastboot_sha256: str


@dataclass(frozen=True, slots=True)
class LocalFlashCommandResult:
    partition: str
    image_sha256: str
    command: tuple[str, ...]
    started_at: str
    completed_at: str
    returncode: int
    timed_out: bool
    output: str

    @property
    def completed(self) -> bool:
        return self.returncode == 0 and not self.timed_out


@dataclass(frozen=True, slots=True)
class LocalFlashResult:
    state: LocalFlashState
    summary: str
    receipt_path: Path
    results: tuple[LocalFlashCommandResult, ...]
    phone_change_attempted: bool
    phone_state_uncertain: bool
    boot_verified: bool = False

    @property
    def completed_count(self) -> int:
        return sum(item.completed for item in self.results)


_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


class LocalFlashService:
    """Inspect and execute one immutable, single-use, user-reviewed local plan."""

    MAX_WRITES = 128
    MAX_JOURNAL_BYTES = 2 * 1024 * 1024
    PROBE_TIMEOUT_SECONDS = 5
    WRITE_TIMEOUT_SECONDS = 1800
    PLAN_VALID_FOR_SECONDS = 15 * 60
    PARTITION = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
    SERIAL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}")

    def __init__(
        self,
        workspace: Path,
        runner: CommandRunner,
        fastboot_path: Path,
        *,
        audit: GuardianAuditStore | None = None,
    ) -> None:
        self.workspace = workspace.resolve(strict=True)
        self.runner = runner
        self.fastboot_path = fastboot_path
        self.privacy = WorkspacePrivacy(self.workspace)
        self.audit = audit or GuardianAuditStore(self.workspace)
        self.root = self.workspace / "guardian" / "local-flash"
        # A public dataclass is a preview, not a capability. Only this live service can
        # execute its own unchanged preview; a persisted report grants no authority.
        self._plans: dict[str, LocalFlashPlan] = {}
        self._plan_lock = threading.Lock()

    def inspect(
        self,
        device: AndroidDevice,
        selections: tuple[LocalFlashSelection, ...],
    ) -> LocalFlashPlan:
        if not isinstance(device, AndroidDevice) or not self.SERIAL.fullmatch(device.serial):
            raise LocalFlashError("Choose a connected phone with a valid exact USB identity.")
        if not device.is_fastboot:
            raise LocalFlashError(
                "Put the selected phone in Fastboot or Fastbootd, refresh devices, and try again."
            )
        if not selections or len(selections) > self.MAX_WRITES:
            raise LocalFlashError("Choose between 1 and 128 partition images.")
        partitions: set[str] = set()
        for selection in selections:
            if (
                not isinstance(selection, LocalFlashSelection)
                or not self.PARTITION.fullmatch(selection.partition)
                or selection.partition.casefold() in partitions
            ):
                raise LocalFlashError("Use a unique, exact partition name for each image.")
            partitions.add(selection.partition.casefold())
        tool = self._tool()
        tool_hash = self._hash_file(tool)[0]
        self.audit.assert_ready()
        warnings: list[str] = [
            "You supplied these image-to-partition mappings. Device identity checks do not prove that each image belongs to this phone.",
            "These writes may make the phone unbootable or lose data. Keep your own recovery images and backup available.",
            "Fastboot completion proves command acceptance only. Image readback, Android boot and subsystem health remain unverified.",
        ]
        with self._device_lock(device.serial):
            product, mode, unlocked, slot = self._live(tool, device.serial, warnings)
            expected = {value.casefold() for value in (device.product, device.codename) if value}
            if not expected:
                raise LocalFlashError(
                    "The selected phone has no recorded product identity. Refresh Device DNA before reviewing image writes."
                )
            if product.casefold() not in expected:
                raise LocalFlashError(
                    "The live product differs from the selected phone. Refresh Device DNA and review the intended target."
                )
            writes: list[LocalFlashWrite] = []
            for selection in selections:
                image = self._image_path(selection.image_path)
                digest, size, expanded = self._hash_file(image, image=True)
                size_limit, logical, slotted = self._partition(
                    tool, device.serial, selection.partition, warnings
                )
                self._mapping_constraints(
                    selection.partition,
                    expanded,
                    size_limit,
                    logical,
                    slotted,
                    mode,
                    bool(slot or device.ab_update or device.virtual_ab),
                )
                writes.append(
                    LocalFlashWrite(
                        selection.partition,
                        image,
                        image.name,
                        size,
                        expanded,
                        digest,
                        size_limit,
                        logical,
                        slotted,
                    )
                )
            # Close the read-only inspection around the same target and mode.
            if self._live(tool, device.serial, []) != (product, mode, unlocked, slot):
                raise LocalFlashError("The phone state changed during inspection. Review again.")
        plan = LocalFlashPlan(
            plan_digest="",
            plan_id=uuid4().hex,
            inspected_at=_now(),
            device_name=_clean(device.display_name, 160),
            masked_serial=device.masked_serial(),
            product=product,
            mode=mode,
            current_slot=slot,
            unlocked=unlocked,
            writes=tuple(writes),
            warnings=tuple(dict.fromkeys(warnings)),
            device_key=self.privacy.pseudonym(device.serial),
            serial=device.serial,
            fastboot_path=tool,
            fastboot_sha256=tool_hash,
        )
        plan = replace(plan, plan_digest=self._plan_digest(plan))
        with self._plan_lock:
            if len(self._plans) >= 128:
                self._plans.pop(next(iter(self._plans)))
            self._plans[plan.plan_digest] = plan
        return plan

    def execute(
        self,
        plan: LocalFlashPlan,
        *,
        accepted_digest: str,
        risk_accepted: bool,
        should_cancel: Callable[[], bool] | None = None,
        progress: Callable[[int, int, str], None] | None = None,
    ) -> LocalFlashResult:
        self._validate_confirmation(plan, accepted_digest, risk_accepted)
        cancel = should_cancel or (lambda: False)
        notify = progress or (lambda _done, _total, _message: None)
        with self._device_lock(plan.serial):
            self._validate_confirmation(plan, accepted_digest, risk_accepted)
            # Claim before revalidation: a retry always presents a fresh preview.
            journal_path = self.root / f"{plan.plan_id}.json"
            payload = self._journal(plan)
            try:
                exclusive_create_json(
                    journal_path,
                    payload,
                    boundary=self.workspace,
                    maximum_bytes=self.MAX_JOURNAL_BYTES,
                )
            except LocalStoreConflictError as exc:
                raise LocalFlashError(
                    "This confirmation was already used. Inspect a new plan."
                ) from exc
            with self._plan_lock:
                self._plans.pop(plan.plan_digest, None)
            results: list[LocalFlashCommandResult] = []
            attempted = False
            state = LocalFlashState.REJECTED
            summary = "No image write started."
            try:
                self.audit.assert_ready()
                self._revalidate(plan, include_images=False)
                snapshots = self._stage_images(plan, payload, journal_path, cancel, notify)
                for index, write in enumerate(plan.writes):
                    if cancel():
                        raise _Cancelled
                    self._revalidate(plan, include_images=False)
                    staged_write = replace(write, image_path=snapshots[write.sha256])
                    self._verify_image(staged_write)
                    current = self._partition(plan.fastboot_path, plan.serial, write.partition, [])
                    if current != (
                        write.partition_size_bytes,
                        write.is_logical,
                        write.has_slot,
                    ):
                        raise LocalFlashError(
                            f"Partition facts changed for {write.partition}; inspect a fresh plan."
                        )
                    notify(index, len(plan.writes), f"Writing {write.partition}…")
                    self._revalidate(plan, include_images=False)
                    if cancel():
                        raise _Cancelled
                    payload["state"] = "writing"
                    payload["in_flight_partition"] = write.partition
                    payload["phone_change_attempted"] = True
                    payload["phone_state_uncertain"] = True
                    self._save(journal_path, payload)
                    # A crash after this checkpoint leaves an explicit uncertain write.
                    attempted = True
                    started_at = _now()
                    command = (
                        str(plan.fastboot_path),
                        "-s",
                        plan.serial,
                        "flash",
                        write.partition,
                        str(staged_write.image_path),
                    )
                    result = self._run(
                        command,
                        operation_id="local-flash.write",
                        write=True,
                        approval=plan.plan_digest,
                    )
                    entry = LocalFlashCommandResult(
                        partition=write.partition,
                        image_sha256=write.sha256,
                        command=("fastboot", "-s", "<device>", "flash", write.partition, "<image>"),
                        started_at=started_at,
                        completed_at=_now(),
                        returncode=result.returncode,
                        timed_out=result.timed_out,
                        output=self._scrub_output(result.stdout + "\n" + result.stderr, plan),
                    )
                    results.append(entry)
                    payload["results"] = [asdict(item) for item in results]
                    payload["in_flight_partition"] = ""
                    self._save(journal_path, payload)
                    self._verify_image(staged_write)
                    if not entry.completed:
                        state = LocalFlashState.FAILED
                        summary = f"Fastboot did not complete {write.partition}. Inspect the phone before any retry."
                        break
                    notify(index + 1, len(plan.writes), f"Fastboot completed {write.partition}.")
                else:
                    state = LocalFlashState.COMPLETED
                    summary = (
                        f"Fastboot completed all {len(results)} selected image write(s). "
                        "The phone has not been rebooted; boot and image readback remain unverified."
                    )
            except _Cancelled:
                state = LocalFlashState.CANCELLED
                summary = (
                    "Stopped between writes at your request."
                    if attempted
                    else "Stopped before any image write at your request."
                )
            except Exception as exc:
                state = LocalFlashState.FAILED if attempted else LocalFlashState.REJECTED
                summary = f"Stopped: {self._scrub_output(str(exc), plan)}. " + (
                    "A write was attempted; inspect the current phone state before continuing."
                    if attempted
                    else "No image write started."
                )
            result = LocalFlashResult(
                state,
                summary,
                journal_path,
                tuple(results),
                attempted,
                attempted,  # Transport success is not independent partition/boot proof.
            )
            payload.update(
                state=state.value,
                summary=summary,
                completed_at=_now(),
                phone_change_attempted=attempted,
                phone_state_uncertain=attempted,
                results=[asdict(item) for item in results],
            )
            try:
                self._save(journal_path, payload)
            except OSError:
                # Preserve the existing pre-command journal. Do not report a successful
                # outcome whose final evidence could not be made durable.
                return replace(
                    result,
                    state=LocalFlashState.FAILED,
                    summary="The final operation record could not be saved. The existing journal may show an interrupted write; inspect the phone before continuing.",
                )
            return result

    def _stage_images(
        self,
        plan: LocalFlashPlan,
        journal: dict[str, object],
        journal_path: Path,
        cancel: Callable[[], bool],
        notify: Callable[[int, int, str], None],
    ) -> dict[str, Path]:
        """Freeze reviewed bytes so unrelated builds cannot change a pending write.

        Snapshots are retained and referenced by the operation journal for recovery.
        User-selected input files are never modified. No partial snapshot can be used.
        """

        unique = {write.sha256: write for write in plan.writes}
        required = sum(write.size_bytes for write in unique.values()) + 8 * 1024 * 1024
        if shutil.disk_usage(self.root).free < required:
            raise LocalFlashError(
                f"The data drive needs at least {required} free bytes for private image snapshots and operation records."
            )
        destination_root = ensure_private_directory(
            self.root / "images" / plan.plan_id, boundary=self.workspace
        )
        paths = {digest: destination_root / f"{digest}.img" for digest in unique}
        journal["state"] = "staging"
        journal["snapshots_verified"] = False
        journal["image_snapshots"] = [
            {
                "relative_path": str(paths[digest].relative_to(self.workspace)),
                "sha256": digest,
                "size_bytes": write.size_bytes,
            }
            for digest, write in unique.items()
        ]
        self._save(journal_path, journal)
        for digest, write in unique.items():
            if cancel():
                raise _Cancelled
            source = self._image_path(write.image_path)
            notify(0, len(plan.writes), f"Preserving approved bytes for {write.partition}…")
            source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                target_fd = os.open(
                    paths[digest],
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                )
            except BaseException:
                os.close(source_fd)
                raise
            measured = hashlib.sha256()
            size = 0
            with os.fdopen(source_fd, "rb") as source_stream, os.fdopen(target_fd, "wb") as target:
                before = os.fstat(source_stream.fileno())
                if not stat.S_ISREG(before.st_mode) or before.st_size != write.size_bytes:
                    raise LocalFlashError(f"The image for {write.partition} changed after review.")
                for chunk in iter(lambda: source_stream.read(1024 * 1024), b""):
                    if cancel():
                        raise _Cancelled
                    size += len(chunk)
                    if size > write.size_bytes:
                        raise LocalFlashError(f"The image for {write.partition} grew after review.")
                    measured.update(chunk)
                    target.write(chunk)
                target.flush()
                os.fsync(target.fileno())
                after = os.fstat(source_stream.fileno())
                if (
                    size != write.size_bytes
                    or measured.hexdigest() != digest
                    or (before.st_mtime_ns, before.st_ctime_ns)
                    != (after.st_mtime_ns, after.st_ctime_ns)
                ):
                    raise LocalFlashError(f"The image for {write.partition} changed after review.")
                if os.name != "nt":
                    os.fchmod(target.fileno(), 0o400)
            self._verify_image(replace(write, image_path=paths[digest]))
        if os.name != "nt":
            directory_fd = os.open(destination_root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        journal["state"] = "prepared"
        journal["snapshots_verified"] = True
        self._save(journal_path, journal)
        return paths

    def _validate_confirmation(
        self, plan: LocalFlashPlan, accepted_digest: str, risk_accepted: bool
    ) -> None:
        if (
            risk_accepted is not True
            or not isinstance(plan, LocalFlashPlan)
            or not isinstance(accepted_digest, str)
            or not hmac.compare_digest(accepted_digest, plan.plan_digest)
        ):
            raise LocalFlashError(
                "Confirm the displayed plan and accept Expert Mode risk before writing."
            )
        with self._plan_lock:
            if self._plans.get(plan.plan_digest) != plan:
                raise LocalFlashError(
                    "This preview changed or was already used. Inspect a fresh plan."
                )
        if self._plan_digest(plan) != plan.plan_digest:
            raise LocalFlashError("The reviewed plan changed. Inspect a fresh plan.")
        age = (datetime.now(UTC) - datetime.fromisoformat(plan.inspected_at)).total_seconds()
        if not 0 <= age <= self.PLAN_VALID_FOR_SECONDS:
            raise LocalFlashError(
                "This preview expired. Inspect the current phone and images again."
            )

    def _revalidate(self, plan: LocalFlashPlan, *, include_images: bool) -> None:
        tool = self._tool()
        if tool != plan.fastboot_path or self._hash_file(tool)[0] != plan.fastboot_sha256:
            raise LocalFlashError("The Fastboot executable changed after review.")
        if self._live(tool, plan.serial, []) != (
            plan.product,
            plan.mode,
            plan.unlocked,
            plan.current_slot,
        ):
            raise LocalFlashError(
                "The selected phone, mode, unlock status or slot changed after review."
            )
        if include_images:
            for write in plan.writes:
                self._verify_image(write)

    def _verify_image(self, write: LocalFlashWrite) -> None:
        if self._image_path(write.image_path) != write.image_path:
            raise LocalFlashError("The selected image path changed after review.")
        if self._hash_file(write.image_path, image=True) != (
            write.sha256,
            write.size_bytes,
            write.expanded_size_bytes,
        ):
            raise LocalFlashError(f"The image for {write.partition} changed after review.")

    def _live(
        self, tool: Path, serial: str, warnings: list[str]
    ) -> tuple[str, str, bool | None, str]:
        discovery = self._run((str(tool), "devices", "-l"), operation_id="local-flash.discover")
        discovery_text = discovery.stdout + "\n" + discovery.stderr
        devices = parse_fastboot_devices(discovery_text)
        selected = [device for device in devices if device["serial"] == serial]
        # The shared parser deduplicates rows for display. Execution must still reject
        # two physical rows advertising the same selected serial, because -s would be
        # ambiguous. Unrelated phones may remain connected.
        selected_rows = sum(
            len(parts) >= 2 and parts[0] == serial and parts[1].casefold() == "fastboot"
            for line in discovery_text.splitlines()
            if (parts := line.split())
        )
        if not discovery.ok or len(selected) != 1 or selected_rows != 1:
            raise LocalFlashError(
                "The selected Fastboot phone is missing or its serial is ambiguous. Refresh devices and review the intended target."
            )
        product = self._getvar(tool, serial, "product", warnings)
        if not product or not self.PARTITION.fullmatch(product):
            raise LocalFlashError(
                "Fastboot did not report a usable product identity. Refresh the phone connection."
            )
        unlock = self._getvar(tool, serial, "unlocked", warnings).casefold()
        unlocked = _boolean(unlock)
        if unlock and unlocked is None:
            warnings.append(
                "The bootloader unlock value is not recognised; unlock status remains unverified."
            )
        if unlocked is False:
            raise LocalFlashError(
                "The phone reports a locked bootloader. It cannot accept this image-write route."
            )
        mode_value = self._getvar(tool, serial, "is-userspace", warnings).casefold()
        mode = (
            "fastbootd"
            if _boolean(mode_value) is True
            else "bootloader"
            if _boolean(mode_value) is False
            else "unknown"
        )
        if mode_value and mode == "unknown":
            warnings.append(
                "The phone's userspace value is not recognised; its current Fastboot mode remains unverified."
            )
        slot = self._getvar(tool, serial, "current-slot", warnings).casefold().removeprefix("_")
        if slot not in {"", "a", "b"}:
            warnings.append(
                "The current slot value is not recognised; use exact partition names from the device's documentation."
            )
        return product, mode, unlocked, slot

    def _partition(
        self, tool: Path, serial: str, partition: str, warnings: list[str]
    ) -> tuple[int | None, bool | None, bool | None]:
        raw_size = self._getvar(tool, serial, f"partition-size:{partition}", warnings)
        size: int | None = None
        if raw_size:
            try:
                size = int(raw_size, 16 if re.fullmatch(r"(?:0x)?[0-9a-fA-F]+", raw_size) else 10)
                if size < 0:
                    raise ValueError
            except ValueError:
                warnings.append(
                    f"The size of {partition} could not be established; its image fit is unverified."
                )
                size = None
        logical_value = self._getvar(tool, serial, f"is-logical:{partition}", warnings)
        logical = _boolean(logical_value)
        if logical_value and logical is None:
            warnings.append(
                f"The logical-partition value for {partition} is not recognised; required transport remains unverified."
            )
        base = partition[:-2] if partition.endswith(("_a", "_b")) else partition
        slot_value = self._getvar(tool, serial, f"has-slot:{base}", warnings)
        slotted = _boolean(slot_value)
        if slot_value and slotted is None:
            warnings.append(
                f"The A/B slot value for {base} is not recognised; use an explicit reviewed target."
            )
        return size, logical, slotted

    @staticmethod
    def _mapping_constraints(
        partition: str,
        expanded: int,
        size: int | None,
        logical: bool | None,
        slotted: bool | None,
        mode: str,
        ab_device: bool,
    ) -> None:
        if size is not None and expanded > size:
            raise LocalFlashError(
                f"The image is too large for {partition}: {expanded} bytes for a {size}-byte partition."
            )
        if logical is True and mode == "bootloader":
            raise LocalFlashError(
                f"{partition} is a logical partition. Enter Fastbootd and inspect again."
            )
        explicit_slot = partition.endswith(("_a", "_b"))
        if not explicit_slot and (slotted is True or (slotted is None and ab_device)):
            raise LocalFlashError(
                f"Choose the exact {partition}_a or {partition}_b partition. ROMVERSE will not choose an A/B slot implicitly."
            )

    def _getvar(self, tool: Path, serial: str, variable: str, warnings: list[str]) -> str:
        result = self._run(
            (str(tool), "-s", serial, "getvar", variable),
            operation_id="local-flash.probe",
        )
        output = result.stdout + "\n" + result.stderr
        if result.timed_out:
            raise LocalFlashError(
                f"The phone timed out while reading {variable}; reconnect and inspect again."
            )
        if not result.ok:
            unsupported = any(
                token in output.casefold()
                for token in (
                    "unknown variable",
                    "variable not found",
                    "not supported",
                    "unknown command",
                    "getvar variable not found",
                )
            )
            if not unsupported:
                raise LocalFlashError(
                    f"Fastboot could not read {variable}; check the connection and refresh."
                )
        else:
            # Variable names themselves contain ':', so split only after the full name.
            prefix = re.compile(
                r"^(?:\(bootloader\)\s*)?" + re.escape(variable) + r"\s*:\s*(.*?)\s*$",
                re.IGNORECASE,
            )
            values = {
                match.group(1)
                for line in output.splitlines()
                if (match := prefix.fullmatch(line.strip()))
            }
            if len(values) > 1:
                raise LocalFlashError(f"Fastboot reported conflicting values for {variable}.")
            if values and next(iter(values)):
                return _clean(next(iter(values)), 160)
        warnings.append(f"The phone does not report {variable}; that check remains unverified.")
        return ""

    def _run(
        self,
        command: tuple[str, ...],
        *,
        operation_id: str,
        write: bool = False,
        approval: str = "",
    ) -> CommandResult:
        started = monotonic()
        safe_args = list(command[1:])
        if write:
            safe_args[-1] = "<reviewed-image>"
        serial = command[2] if len(command) > 2 and command[1] == "-s" else "host"
        request = OperationRequest(
            operation_id,
            OperationClass.STATE_CHANGING if write else OperationClass.READ_ONLY,
            command[0],
            tuple(safe_args),
            "Execute the exact locally reviewed image write"
            if write
            else "Inspect the selected local image-write target",
            target=serial,
            approval_digest=approval,
        )
        decision = GuardianDecision(
            True,
            RiskLevel.HIGH if write else RiskLevel.NONE,
            (
                "Explicit local Expert Mode plan confirmation"
                if write
                else "Read-only local plan inspection",
            ),
            user_approval_required=write,
        )
        self.audit.assert_ready()
        try:
            result = self.runner.run(
                command,
                timeout=self.WRITE_TIMEOUT_SECONDS if write else self.PROBE_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            self.audit.record(
                request, decision, None, int((monotonic() - started) * 1000), type(exc).__name__
            )
            raise LocalFlashError("The device command did not return a measurable result.") from exc
        self.audit.record(request, decision, result, int((monotonic() - started) * 1000))
        if result.args != command:
            raise LocalFlashError("The command runner returned evidence for a different operation.")
        return result

    def _tool(self) -> Path:
        path = self.fastboot_path.expanduser()
        if path.name.casefold() not in {"fastboot", "fastboot.exe"}:
            raise LocalFlashError("Select the verified Fastboot executable from Forge Arsenal.")
        path = self._regular_path(path)
        if os.name != "nt" and not os.access(path, os.X_OK):
            raise LocalFlashError("Fastboot is not executable. Repair it in Forge Arsenal.")
        return path

    @classmethod
    def _image_path(cls, path: Path) -> Path:
        if not isinstance(path, Path) or path.suffix.casefold() != ".img":
            raise LocalFlashError(
                "Choose an extracted .img image, not a firmware archive or script."
            )
        return cls._regular_path(path.expanduser())

    @staticmethod
    def _regular_path(path: Path) -> Path:
        path = path.absolute()
        try:
            for parent in (path, *path.parents):
                info = parent.lstat()
                if stat.S_ISLNK(info.st_mode):
                    raise LocalFlashError(
                        "The selected file path contains a symbolic link; choose its actual file."
                    )
            if not stat.S_ISREG(path.stat().st_mode):
                raise LocalFlashError("The selected input is not a regular file.")
            return path.resolve(strict=True)
        except OSError as exc:
            raise LocalFlashError("A selected image or tool is unavailable.") from exc

    @staticmethod
    def _hash_file(path: Path, *, image: bool = False) -> tuple[str, int, int]:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size <= 0:
                raise LocalFlashError(
                    "The selected image or tool is empty or is not a regular file."
                )
            digest = hashlib.sha256()
            header = stream.read(28)
            digest.update(header)
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
            expanded = before.st_size
            if image and header[:4] == b"\x3a\xff\x26\xed":
                stream.seek(0)
                expanded = _sparse_size(stream, before.st_size)
            after = os.fstat(stream.fileno())
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ):
                raise LocalFlashError("A selected file changed while it was being verified.")
        return digest.hexdigest(), before.st_size, expanded

    @staticmethod
    def _plan_digest(plan: LocalFlashPlan) -> str:
        payload = asdict(plan)
        payload.pop("plan_digest")
        return _digest(payload)

    @staticmethod
    def _journal(plan: LocalFlashPlan) -> dict[str, object]:
        writes = []
        for write in plan.writes:
            item = asdict(write)
            item.pop("image_path")
            writes.append(item)
        return {
            "format": "romverse.local-expert-flash",
            "schema_version": 1,
            "plan_id": plan.plan_id,
            "plan_digest": plan.plan_digest,
            "device_key": plan.device_key,
            "product": plan.product,
            "mode": plan.mode,
            "current_slot": plan.current_slot,
            "fastboot_sha256": plan.fastboot_sha256,
            "writes": writes,
            "warnings": list(plan.warnings),
            "consent": "explicit-expert-exact-plan",
            "started_at": _now(),
            "state": "preparing",
            "in_flight_partition": "",
            "phone_change_attempted": False,
            "phone_state_uncertain": False,
            "boot_verified": False,
            "readback_verified": False,
            "external_certification": False,
            "results": [],
        }

    def _save(self, path: Path, payload: dict[str, object]) -> None:
        document = dict(payload)
        document["record_digest"] = _digest(document)
        atomic_write_json(
            path, document, boundary=self.workspace, maximum_bytes=self.MAX_JOURNAL_BYTES
        )

    @staticmethod
    def _scrub_output(output: str, plan: LocalFlashPlan) -> str:
        value = output[-8192:]
        for private in (
            plan.serial,
            str(plan.fastboot_path),
            *(str(item.image_path) for item in plan.writes),
        ):
            value = value.replace(private, "<private>")
        value = re.sub(r"(?:[A-Za-z]:[\\/]|/)(?:[^\s\"'<>]+[\\/])*[^\s\"'<>]*", "<path>", value)
        value = re.sub(r"\b(?:[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\d{14,20})\b", "<private>", value)
        value = re.sub(
            r"(?i)\b(?:token|password|secret|imei|serial)\s*[:=]\s*\S+", "<private>", value
        )
        return "".join(char for char in value if char in "\n\t" or ord(char) >= 32).strip()

    @contextmanager
    def _device_lock(self, serial: str) -> Iterator[None]:
        key = hashlib.sha256(serial.encode()).hexdigest()
        with _LOCKS_GUARD:
            lock = _LOCKS.setdefault(key, threading.Lock())
        if not lock.acquire(blocking=False):
            raise LocalFlashError(
                "Another local image operation is using this phone. Wait for it to finish."
            )
        descriptor: int | None = None
        try:
            lock_root = ensure_private_directory(self.root / "locks", boundary=self.workspace)
            path = lock_root / f"{self.privacy.pseudonym(serial)}.lock"
            descriptor = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise LocalFlashError("The phone operation lock is not a regular file.")
            if os.name == "nt":
                import msvcrt

                if os.fstat(descriptor).st_size == 0:
                    os.write(descriptor, b"\0")
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
        except BlockingIOError as exc:
            raise LocalFlashError(
                "Another ROMVERSE process is using this phone. Wait for it to finish."
            ) from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
            lock.release()


def _boolean(value: str) -> bool | None:
    clean = value.casefold()
    return (
        True if clean in {"yes", "true", "1"} else False if clean in {"no", "false", "0"} else None
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _clean(value: str, maximum: int) -> str:
    return " ".join(value.replace("\x00", " ").split())[:maximum]


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _sparse_size(stream, file_size: int) -> int:
    """Validate sparse chunk geometry without expanding or modifying the image."""
    header = stream.read(28)
    if len(header) != 28:
        raise LocalFlashError("The Android sparse image header is truncated.")
    magic, major, _minor, file_header, chunk_header, block_size, blocks, chunks, _checksum = (
        struct.unpack("<I4H4I", header)
    )
    if (
        magic != 0xED26FF3A
        or major != 1
        or file_header < 28
        or chunk_header < 12
        or block_size <= 0
        or block_size % 4
        or blocks <= 0
        or chunks <= 0
        or chunks > file_size // 12
        or file_header > file_size
    ):
        raise LocalFlashError("The Android sparse image header is invalid.")
    stream.seek(file_header)
    observed_blocks = 0
    for _ in range(chunks):
        chunk = stream.read(12)
        if len(chunk) != 12:
            raise LocalFlashError("The Android sparse image has a truncated chunk.")
        kind, _reserved, chunk_blocks, total = struct.unpack("<2H2I", chunk)
        payload = total - chunk_header
        expected = {0xCAC1: chunk_blocks * block_size, 0xCAC2: 4, 0xCAC3: 0, 0xCAC4: 4}.get(kind)
        if expected is None or payload != expected or (kind == 0xCAC4 and chunk_blocks != 0):
            raise LocalFlashError("The Android sparse image contains invalid chunk geometry.")
        observed_blocks += chunk_blocks
        next_offset = stream.tell() - 12 + total
        if next_offset > file_size or next_offset < stream.tell():
            raise LocalFlashError("The Android sparse image chunk extends outside the file.")
        stream.seek(next_offset)
    if stream.tell() != file_size or observed_blocks != blocks:
        raise LocalFlashError("The Android sparse image block count or file length is invalid.")
    return blocks * block_size
