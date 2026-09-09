"""Execute a vetted, source-declared installation without running its shell script.

This is local user authorization, not a signed production certification. Every
step is recorded before dispatch; command success is not independent readback or
Android health evidence. Cancellation never interrupts an in-flight write.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shutil
import stat
import threading
import zipfile
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from time import monotonic
from uuid import uuid4

from romverse.device.models import AndroidDevice
from romverse.guardian.local_flash import LocalFlashError, LocalFlashService, LocalFlashState
from romverse.guardian.local_transition import LocalDeviceTransitionService, LocalTransitionTarget
from romverse.guardian.models import GuardianDecision, OperationClass, OperationRequest, RiskLevel
from romverse.infrastructure.local_store import (
    LocalStoreConflictError,
    atomic_write_json,
    ensure_private_directory,
    exclusive_create_json,
    read_json_object,
)
from romverse.infrastructure.process import CommandResult
from romverse.rom.candidate_installation import (
    CandidateInstallationRecipe,
    candidate_composition_payload,
)
from romverse.rom.source_installation import (
    POPSICLE_PHYSICAL_PARTITIONS,
    POPSICLE_SCRIPT_SHA256,
    SourceInstallationRecipe,
    SourceInstallationService,
)


class SourceInstallationError(LocalFlashError):
    pass


class _Cancelled(SourceInstallationError):
    pass


@dataclass(frozen=True, slots=True)
class SourceInstallationPlan:
    plan_id: str
    plan_digest: str
    inspected_at: str
    recipe: SourceInstallationRecipe
    device_name: str
    masked_serial: str
    product: str
    current_slot: str
    device_key: str
    warnings: tuple[str, ...]
    partition_facts: tuple[tuple[str, int | None, bool | None, bool | None], ...]
    fastboot_sha256: str
    serial: str = field(repr=False)
    fastboot_path: Path = field(repr=False)
    source_device: AndroidDevice = field(repr=False)


@dataclass(frozen=True, slots=True)
class SourceInstallationStepResult:
    index: int
    action: str
    partition: str
    command: tuple[str, ...]
    started_at: str
    completed_at: str
    returncode: int
    timed_out: bool
    output: str
    verified_slot: str = ""

    @property
    def completed(self) -> bool:
        return self.returncode == 0 and not self.timed_out


@dataclass(frozen=True, slots=True)
class SourceInstallationResult:
    state: LocalFlashState
    summary: str
    receipt_path: Path
    results: tuple[SourceInstallationStepResult, ...]
    phone_change_attempted: bool
    phone_state_uncertain: bool
    reboot_requested: bool
    android_arrival_verified: bool = False
    observed_device: AndroidDevice | None = None
    boot_verified: bool = False

    @property
    def completed_count(self) -> int:
        return sum(item.completed for item in self.results)


class SourceInstallationExecutor:
    FORMAT = "romverse.source-installation"
    CANDIDATE_FORMAT = "romverse.candidate-installation"
    MAX_JOURNAL_BYTES = 2 * 1024 * 1024
    MAX_STEPS = 128
    PLAN_VALID_FOR_SECONDS = 900

    def __init__(
        self,
        source_service: SourceInstallationService,
        local_flash: LocalFlashService,
        adb_path: Path | None = None,
    ) -> None:
        self.source_service = source_service
        self.flash = local_flash
        self.workspace = local_flash.workspace
        self.root = ensure_private_directory(
            self.workspace / "guardian" / "source-installation", boundary=self.workspace
        )
        self.adb_path = adb_path
        self._plans: dict[str, SourceInstallationPlan] = {}
        self._plans_lock = threading.Lock()

    def inspect(
        self, device: AndroidDevice, recipe: SourceInstallationRecipe
    ) -> SourceInstallationPlan:
        self.source_service.verify(recipe)
        _recipe_provenance(recipe)
        if (
            not isinstance(device, AndroidDevice)
            or not self.flash.SERIAL.fullmatch(device.serial)
            or device.transport not in {"usb", "usb-fastboot"}
            or not device.is_fastboot
        ):
            raise SourceInstallationError(
                "Connect the exact phone in USB bootloader mode, then refresh Device DNA."
            )
        if not 1 <= len(recipe.steps) <= self.MAX_STEPS:
            raise SourceInstallationError("The source installation has an invalid step count.")
        tool = self.flash._tool()
        tool_hash = self.flash._hash_file(tool)[0]
        warnings = list(recipe.warnings)
        with self.flash._device_lock(device.serial):
            product, mode, unlocked, slot = self.flash._live(tool, device.serial, warnings)
            self._identity(recipe, product, mode)
            if (
                device.codename
                and device.codename.strip().casefold() != recipe.expected_product.casefold()
            ):
                raise SourceInstallationError(
                    "The selected phone's known codename contradicts the source device."
                )
            if (
                device.manufacturer
                and device.manufacturer.strip().casefold()
                != recipe.expected_manufacturer.casefold()
            ):
                raise SourceInstallationError(
                    "The selected phone's known manufacturer contradicts the source device."
                )
            known = {value.casefold() for value in (device.product, device.codename) if value}
            if known and product.casefold() not in known:
                raise SourceInstallationError(
                    "The live phone differs from the selected Device DNA."
                )
            if slot not in {"a", "b"}:
                raise SourceInstallationError(
                    "The current slot is unknown; refresh the phone before installation."
                )
            self._unlock(tool, device.serial)
            images = {image.member: image for image in recipe.images}
            facts: list[tuple[str, int | None, bool | None, bool | None]] = []
            for step in recipe.steps:
                if step.action != "flash":
                    continue
                image = images[step.image_member]
                size, logical, slotted = self.flash._partition(
                    tool, device.serial, step.partition, warnings
                )
                # The verified script explicitly addresses the whole physical
                # super container, not an inferred logical/A-B destination. Some
                # bootloaders omit has-slot:super; do not invent super_a/super_b.
                # A positive slotted/logical report and size limits still apply.
                whole_super = step.partition == "super" and step.chunk_size == "700M"
                self.flash._mapping_constraints(
                    step.partition,
                    image.expanded_size_bytes,
                    size,
                    logical,
                    slotted,
                    mode,
                    not whole_super,
                )
                facts.append((step.partition, size, logical, slotted))
            if self.flash._live(tool, device.serial, []) != (product, mode, unlocked, slot):
                raise SourceInstallationError(
                    "The phone state changed during review; inspect again."
                )
        warnings.extend(
            (
                "This runs the package's complete reviewed source procedure, not a production-certified Device Pack.",
                "Keep-data mode does not guarantee existing apps or data remain usable; a separate backup is essential.",
                "Stopping waits for the current command and may leave an incomplete installation. Boot and readback are separate checks.",
            )
        )
        plan = SourceInstallationPlan(
            uuid4().hex,
            "",
            _now(),
            recipe,
            device.display_name,
            device.masked_serial(),
            product,
            slot,
            self.flash.privacy.pseudonym(device.serial),
            tuple(dict.fromkeys(warnings)),
            tuple(facts),
            tool_hash,
            device.serial,
            tool,
            device,
        )
        plan = replace(plan, plan_digest=_digest(asdict(plan)))
        with self._plans_lock:
            if len(self._plans) >= 128:
                self._plans.pop(next(iter(self._plans)))
            self._plans[plan.plan_digest] = plan
        return plan

    def execute(
        self,
        plan: SourceInstallationPlan,
        *,
        accepted_digest: str,
        risk_accepted: bool,
        should_cancel: Callable[[], bool] | None = None,
        progress: Callable[[int, int, str], None] | None = None,
    ) -> SourceInstallationResult:
        self._confirmation(plan, accepted_digest, risk_accepted)
        cancel = should_cancel or (lambda: False)
        notify = progress or (lambda _done, _total, _message: None)
        with self.flash._device_lock(plan.serial):
            self._confirmation(plan, accepted_digest, risk_accepted)
            path = self.root / f"{plan.plan_id}.json"
            journal = self._journal(plan)
            try:
                exclusive_create_json(
                    path,
                    {**journal, "record_digest": _digest(journal)},
                    boundary=self.workspace,
                    maximum_bytes=self.MAX_JOURNAL_BYTES,
                )
            except LocalStoreConflictError as exc:
                raise SourceInstallationError(
                    "This confirmation was already used; review a new installation."
                ) from exc
            with self._plans_lock:
                self._plans.pop(plan.plan_digest, None)
            entries: list[SourceInstallationStepResult] = []
            attempted = False
            rebooted = False
            arrived = None
            state = LocalFlashState.REJECTED
            summary = "No installation command started."
            expected_slot = plan.current_slot
            try:
                if cancel():
                    raise _Cancelled
                self.source_service.verify(plan.recipe)
                self._revalidate(plan, expected_slot)
                snapshots = self._stage(plan, journal, path, cancel, notify)
                # The confirmed operation owns its single-use claim now. Slow
                # snapshot preparation must not expire that active operation and
                # force another copy cycle; all bytes/tools/live state are still
                # freshly checked at their use boundaries.
                images = {item.member: item for item in plan.recipe.images}
                facts = {item[0]: item[1:] for item in plan.partition_facts}
                for index, step in enumerate(plan.recipe.steps):
                    if cancel():
                        raise _Cancelled
                    self._revalidate(plan, expected_slot)
                    if step.action == "flash":
                        image = images[step.image_member]
                        self._verify_snapshot(snapshots[image.member], image)
                        if (
                            self.flash._partition(
                                plan.fastboot_path, plan.serial, step.partition, []
                            )
                            != facts[step.partition]
                        ):
                            raise SourceInstallationError(
                                f"Partition facts changed for {step.partition}; no further steps will run."
                            )
                    command = self._command(plan, step, snapshots)
                    notify(
                        index,
                        len(plan.recipe.steps),
                        f"{index + 1}/{len(plan.recipe.steps)} · {step.action} {step.partition or step.slot or 'Android'}",
                    )
                    self._revalidate(plan, expected_slot)
                    if step.action == "flash":
                        self._verify_snapshot(
                            snapshots[step.image_member], images[step.image_member]
                        )
                    if cancel():
                        raise _Cancelled
                    journal.update(
                        state="command-in-flight",
                        in_flight_step=index,
                        phone_change_attempted=True,
                        phone_state_uncertain=True,
                    )
                    self._save(path, journal)
                    attempted = True
                    if step.action == "reboot":
                        rebooted = True
                    started = _now()
                    result = self._run(
                        command, action=step.action, approval=plan.plan_digest, write=True
                    )
                    entry = SourceInstallationStepResult(
                        index,
                        step.action,
                        step.partition,
                        self._public_command(command),
                        started,
                        _now(),
                        result.returncode,
                        result.timed_out,
                        self._scrub(result.stdout + "\n" + result.stderr, plan),
                    )
                    entries.append(entry)
                    journal.update(results=[asdict(item) for item in entries], in_flight_step=None)
                    self._save(path, journal)
                    if not result.ok:
                        raise SourceInstallationError(
                            f"Fastboot did not complete step {index + 1} ({step.action} {step.partition}). Inspect the phone before any retry."
                        )
                    if step.action == "set_active":
                        # An ACK is not evidence the requested slot actually became active.
                        self._revalidate(plan, step.slot)
                        expected_slot = step.slot
                        entries[-1] = replace(entry, verified_slot=step.slot)
                    elif step.action == "flash":
                        self._verify_snapshot(
                            snapshots[step.image_member], images[step.image_member]
                        )
                    elif step.action == "reboot":
                        # Arrival is a bounded read-only sample, not a boot-health claim.
                        arrived = self._android_arrival(plan)
                    journal["results"] = [asdict(item) for item in entries]
                    self._save(path, journal)
                    notify(
                        index + 1,
                        len(plan.recipe.steps),
                        f"Completed {step.action} {step.partition or step.slot or 'Android'}.",
                    )
                state = LocalFlashState.COMPLETED
                summary = (
                    (
                        f"Fastboot completed the rebuilt candidate's {len(entries)} reviewed installation steps. "
                        if type(plan.recipe) is CandidateInstallationRecipe
                        else f"Fastboot completed the source's {len(entries)} declared installation steps. "
                    )
                    + (
                        "Android reboot was requested. "
                        if rebooted
                        else "The phone remains in bootloader mode. "
                    )
                    + "Image readback, Android boot stability and subsystem health remain unverified."
                )
            except _Cancelled:
                state = LocalFlashState.CANCELLED
                summary = (
                    "Stopped between commands; installation may be incomplete."
                    if attempted
                    else "Cancelled before changing the phone."
                )
            except Exception as exc:
                state = LocalFlashState.FAILED if attempted else LocalFlashState.REJECTED
                summary = self._scrub(str(exc), plan) + (
                    " The phone state is uncertain; do not automatically retry."
                    if attempted
                    else " No phone-changing command started."
                )
            output = SourceInstallationResult(
                state,
                summary,
                path,
                tuple(entries),
                attempted,
                attempted,
                rebooted,
                arrived is not None,
                arrived,
            )
            journal.update(
                state=state.value,
                summary=summary,
                completed_at=_now(),
                results=[asdict(item) for item in entries],
                phone_change_attempted=attempted,
                phone_state_uncertain=attempted,
                reboot_requested=rebooted,
                android_arrival_verified=arrived is not None,
            )
            try:
                self._save(path, journal)
            except OSError:
                return replace(
                    output,
                    state=LocalFlashState.FAILED,
                    summary="The final installation record could not be saved. Preserve the existing interrupted-operation journal and inspect the phone.",
                )
            return output

    def _stage(self, plan, journal, journal_path, cancel, notify):
        candidate = _recipe_provenance(plan.recipe)
        origins = {item["member"]: item for item in candidate["origins"]} if candidate else {}
        images = {item.member: item for item in plan.recipe.images}
        unique = {item.sha256: item for item in images.values()}
        required = sum(item.size_bytes for item in unique.values()) + 8 * 1024 * 1024
        if shutil.disk_usage(self.root).free < required:
            raise SourceInstallationError(
                f"At least {required} free bytes are required for private installation images."
            )
        folder = ensure_private_directory(
            self.root / "images" / plan.plan_id, boundary=self.workspace
        )
        paths = {member: folder / f"{image.sha256}.img" for member, image in images.items()}
        journal.update(
            state="staging",
            snapshots_verified=False,
            image_snapshots=[
                {
                    "member": member,
                    "relative_path": paths[member].relative_to(self.workspace).as_posix(),
                    "sha256": image.sha256,
                    "size_bytes": image.size_bytes,
                    "expanded_size_bytes": image.expanded_size_bytes,
                }
                for member, image in images.items()
            ],
        )
        self._save(journal_path, journal)
        archive = self.flash._regular_path(plan.recipe.archive_path)
        descriptor = os.open(archive, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as archive_stream:
            before = os.fstat(archive_stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise SourceInstallationError("The protected source is not a regular archive.")
            measured = hashlib.sha256()
            for chunk in iter(lambda: archive_stream.read(1024 * 1024), b""):
                if cancel():
                    raise _Cancelled
                measured.update(chunk)
            archive_sha256 = (
                candidate["procedure_source_sha256"] if candidate else plan.recipe.source_sha256
            )
            if measured.hexdigest() != archive_sha256:
                raise SourceInstallationError("The protected source changed after review.")
            archive_stream.seek(0)
            with zipfile.ZipFile(archive_stream) as source:
                members = source.infolist()
                done: set[str] = set()
                for member, image in images.items():
                    if cancel():
                        raise _Cancelled
                    matches = [item for item in members if item.filename == member]
                    origin = origins.get(member)
                    rebuilt = origin is not None and origin["source_kind"] == "signed-final"
                    if len(matches) != 1 or (
                        not rebuilt and matches[0].file_size != image.size_bytes
                    ):
                        raise SourceInstallationError(
                            "An installation image is missing, duplicated or resized."
                        )
                    if image.sha256 in done and not rebuilt:
                        continue
                    notify(
                        0, len(plan.recipe.steps), f"Preserving reviewed image {Path(member).name}…"
                    )
                    with ExitStack() as stack:
                        if rebuilt:
                            # The base archive's super/child images are deliberately
                            # never opened for replacement roles, even on failure.
                            path = self._rebuilt_path(origin["relative_path"])
                            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                            stream = stack.enter_context(os.fdopen(fd, "rb"))
                            original_stat = os.fstat(stream.fileno())
                            if (
                                not stat.S_ISREG(original_stat.st_mode)
                                or original_stat.st_size != image.size_bytes
                            ):
                                raise SourceInstallationError(
                                    "A rebuilt installation image is missing or resized."
                                )
                        else:
                            stream = stack.enter_context(source.open(matches[0]))
                        self._copy_snapshot(
                            stream, paths[member], image, cancel, create=image.sha256 not in done
                        )
                        if rebuilt and (
                            _file_identity(original_stat)
                            != _file_identity(os.fstat(stream.fileno()))
                            or _file_identity(original_stat) != _file_identity(path.stat())
                            or self._rebuilt_path(origin["relative_path"]) != path
                        ):
                            raise SourceInstallationError(
                                "A rebuilt image changed while its private snapshot was prepared."
                            )
                    self._verify_snapshot(paths[member], image)
                    done.add(image.sha256)
            after = os.fstat(archive_stream.fileno())
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ):
                raise SourceInstallationError(
                    "The protected source changed while images were preserved."
                )
        if os.name != "nt":
            directory_fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        journal.update(state="prepared", snapshots_verified=True)
        self._save(journal_path, journal)
        return paths

    def _rebuilt_path(self, relative_path):
        _relative_member(relative_path, canonical=True)
        selected = self.workspace / relative_path
        path = self.flash._image_path(selected)
        if not path.is_relative_to(self.workspace) or path != selected:
            raise SourceInstallationError("A rebuilt image is outside the reviewed workspace.")
        return path

    @staticmethod
    def _copy_snapshot(stream, path, image, cancel, *, create):
        # Even an identical-byte duplicate replacement must be read and verified;
        # deduplication never substitutes missing/stale input with a base image.
        with ExitStack() as stack:
            target = None
            if create:
                fd = os.open(
                    path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600
                )
                target = stack.enter_context(os.fdopen(fd, "wb"))
            digest, size = hashlib.sha256(), 0
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                if cancel():
                    raise _Cancelled
                size += len(chunk)
                if size > image.size_bytes:
                    raise SourceInstallationError(
                        "An installation image exceeded its reviewed size."
                    )
                digest.update(chunk)
                if target is not None:
                    target.write(chunk)
            if size != image.size_bytes or digest.hexdigest() != image.sha256:
                raise SourceInstallationError(
                    "An installation image differs from the reviewed source."
                )
            if target is not None:
                target.flush()
                os.fsync(target.fileno())
                if os.name != "nt":
                    os.fchmod(target.fileno(), 0o400)

    def _verify_snapshot(self, path, image):
        if self.flash._image_path(path) != path or self.flash._hash_file(path, image=True) != (
            image.sha256,
            image.size_bytes,
            image.expanded_size_bytes,
        ):
            raise SourceInstallationError(
                "A private installation image changed; no further steps will run."
            )

    def _identity(self, recipe, product, mode):
        if product.casefold() != recipe.expected_product.casefold():
            raise SourceInstallationError(
                "The source is for a different device. An exact live product match is required; partition size alone is not device identity."
            )
        if mode != "bootloader":
            raise SourceInstallationError(
                "This source procedure requires bootloader Fastboot, not Fastbootd or an unknown mode."
            )

    def _unlock(self, tool, serial):
        result = self._run(
            (str(tool), "-s", serial, "oem", "device-info"), action="unlock-inspection"
        )
        if not result.ok:
            raise SourceInstallationError(
                "The phone's bootloader and critical unlock state could not be verified with device-info."
            )
        text = result.stdout + "\n" + result.stderr
        for name in ("Device unlocked", "Device critical unlocked"):
            values = {
                match.group(1).casefold()
                for line in text.splitlines()
                if (
                    match := re.fullmatch(
                        r"(?:\(bootloader\)\s*)?" + re.escape(name) + r"\s*:\s*(true|false|yes|no)",
                        line.strip(),
                        re.I,
                    )
                )
            }
            if len(values) != 1 or next(iter(values)) not in {"true", "yes"}:
                raise SourceInstallationError(
                    f"{name} must be positively verified before this source installation. ROMVERSE will not unlock the phone."
                )

    def _revalidate(self, plan, expected_slot):
        if (
            self.flash._tool() != plan.fastboot_path
            or self.flash._hash_file(plan.fastboot_path)[0] != plan.fastboot_sha256
        ):
            raise SourceInstallationError("Fastboot changed after review.")
        product, mode, _unlocked, slot = self.flash._live(plan.fastboot_path, plan.serial, [])
        self._identity(plan.recipe, product, mode)
        if slot != expected_slot:
            raise SourceInstallationError(
                "The active slot differs from the reviewed installation state."
            )
        self._unlock(plan.fastboot_path, plan.serial)

    def _confirmation(self, plan, accepted_digest, risk_accepted):
        if (
            not isinstance(plan, SourceInstallationPlan)
            or risk_accepted is not True
            or not isinstance(accepted_digest, str)
            or not hmac.compare_digest(accepted_digest, plan.plan_digest)
        ):
            raise SourceInstallationError(
                "Confirm the exact installation and its data-loss risks before continuing."
            )
        with self._plans_lock:
            if self._plans.get(plan.plan_digest) != plan:
                raise SourceInstallationError(
                    "This installation preview changed or was already used."
                )
        if _digest(asdict(replace(plan, plan_digest=""))) != plan.plan_digest:
            raise SourceInstallationError("The reviewed installation changed.")
        self._age(plan)

    def _age(self, plan):
        age = (datetime.now(UTC) - datetime.fromisoformat(plan.inspected_at)).total_seconds()
        if not 0 <= age <= self.PLAN_VALID_FOR_SECONDS:
            raise SourceInstallationError(
                "This installation preview expired; inspect and confirm again."
            )

    @staticmethod
    def _command(plan, step, snapshots):
        prefix = (str(plan.fastboot_path), "-s", plan.serial)
        if step.action == "set_active" and step.slot == "a":
            return (*prefix, "set_active", "a")
        if step.action == "flash" and re.fullmatch(r"[A-Za-z0-9_.-]+", step.partition):
            flags = ("-S", "700M") if step.chunk_size == "700M" else ()
            if step.chunk_size not in {"", "700M"}:
                raise SourceInstallationError("Unsupported source transfer size.")
            return (*prefix, *flags, "flash", step.partition, str(snapshots[step.image_member]))
        if (
            step.action == "erase"
            and plan.recipe.wipe
            and step.partition in {"metadata", "userdata"}
        ):
            return (*prefix, "erase", step.partition)
        if step.action == "reboot" and plan.recipe.reboot:
            return (*prefix, "reboot")
        raise SourceInstallationError(
            "The source contains an unsupported or unconfirmed operation."
        )

    def _run(self, command, *, action, approval="", write=False):
        public = self._public_command(command)
        request = OperationRequest(
            f"source-installation.{action}",
            OperationClass.STATE_CHANGING if write else OperationClass.READ_ONLY,
            command[0],
            tuple(public[1:]),
            f"{'Execute' if write else 'Inspect'} the exact source-declared installation {action}",
            target=command[2],
            approval_digest=approval,
        )
        decision = GuardianDecision(
            True,
            RiskLevel.HIGH if write else RiskLevel.NONE,
            (
                "Explicit source-bound installation confirmation"
                if write
                else "Read-only source-installation inspection",
            ),
            user_approval_required=write,
        )
        self.flash.audit.assert_ready()
        started = monotonic()
        try:
            result = self.flash.runner.run(
                command,
                timeout=self.flash.WRITE_TIMEOUT_SECONDS
                if write
                else self.flash.PROBE_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            self.flash.audit.record(
                request, decision, None, int((monotonic() - started) * 1000), type(exc).__name__
            )
            raise SourceInstallationError(
                "The installation command did not return measurable evidence."
            ) from exc
        self.flash.audit.record(request, decision, result, int((monotonic() - started) * 1000))
        if not isinstance(result, CommandResult) or result.args != command:
            raise SourceInstallationError("The command result belongs to a different operation.")
        return result

    def _android_arrival(self, plan):
        if self.adb_path is None:
            return None
        # No reboot is issued by this observer. A later boot monitor can wait longer.
        transition = LocalDeviceTransitionService(self.flash, self.adb_path)
        try:
            tools = transition._required_tools(False, LocalTransitionTarget.ANDROID)
            return transition._adb_observe(plan.source_device, tools)
        except (LocalFlashError, OSError, ValueError):
            return None

    @staticmethod
    def _public_command(command):
        public = ["fastboot", "-s", "<device>", *command[3:]]
        if "flash" in public:
            public[-1] = "<reviewed-image>"
        return tuple(public)

    @staticmethod
    def _scrub(text, plan):
        value = str(text)[-8192:]
        for private in (plan.serial, str(plan.fastboot_path), str(plan.recipe.archive_path)):
            value = value.replace(private, "<private>")
        value = re.sub(r"(?:[A-Za-z]:[\\/]|/)(?:[^\s\"'<>]+[\\/])*[^\s\"'<>]*", "<path>", value)
        value = re.sub(r"\b(?:[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\d{14,20})\b", "<private>", value)
        value = re.sub(
            r"(?i)\b(?:token|password|secret|imei|serial)\s*[:=]\s*\S+", "<private>", value
        )
        return "".join(char for char in value if char in "\n\t" or ord(char) >= 32).strip()

    def _journal(self, plan):
        candidate = _recipe_provenance(plan.recipe)
        return {
            "format": self.CANDIDATE_FORMAT if candidate else self.FORMAT,
            **({"candidate_provenance": candidate} if candidate else {}),
            "schema_version": 1,
            "plan_id": plan.plan_id,
            "plan_digest": plan.plan_digest,
            "project_id": plan.recipe.project_id,
            "source_sha256": plan.recipe.source_sha256,
            "recipe_digest": plan.recipe.recipe_digest,
            "script_sha256": plan.recipe.script_sha256,
            "device_key": plan.device_key,
            "product": plan.product,
            "fastboot_sha256": plan.fastboot_sha256,
            "initial_slot": plan.current_slot,
            "steps": [asdict(item) for item in plan.recipe.steps],
            "wipe": plan.recipe.wipe,
            "reboot": plan.recipe.reboot,
            "consent": "explicit-source-installation-exact-plan",
            "started_at": _now(),
            "state": "preparing",
            "in_flight_step": None,
            "results": [],
            "phone_change_attempted": False,
            "phone_state_uncertain": False,
            "reboot_requested": False,
            "android_arrival_verified": False,
            "boot_verified": False,
            "readback_verified": False,
            "production_certification": False,
        }

    def _save(self, path, journal):
        content = dict(journal)
        content["record_digest"] = _digest(content)
        atomic_write_json(
            path, content, boundary=self.workspace, maximum_bytes=self.MAX_JOURNAL_BYTES
        )


def _file_identity(info):
    stable = info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns
    # Windows descriptor/path stat calls can expose different ctime semantics for one file.
    return stable if os.name == "nt" else (*stable, info.st_ctime_ns)


def _relative_member(value, *, canonical=False):
    if (
        not isinstance(value, str)
        or not value
        or value.startswith("/")
        or "\\" in value
        or ":" in value
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise SourceInstallationError("Invalid candidate image path.")
    path = PurePosixPath(value)
    if (
        ".." in path.parts
        or path.as_posix() in {"", "."}
        or (canonical and path.as_posix() != value)
    ):
        raise SourceInstallationError("Invalid candidate image path.")
    return path


def _recipe_provenance(recipe):
    if type(recipe) is SourceInstallationRecipe:
        return None
    if type(recipe) is not CandidateInstallationRecipe:
        raise SourceInstallationError("The installation recipe type is not supported.")
    payload = candidate_composition_payload(recipe)
    document = {
        "format": SourceInstallationExecutor.CANDIDATE_FORMAT,
        "schema_version": 1,
        "candidate_provenance": payload,
        "recipe_digest": recipe.recipe_digest,
        **{
            name: getattr(recipe, name)
            for name in ("project_id", "source_sha256", "script_sha256", "wipe", "reboot")
        },
        "steps": [asdict(step) for step in recipe.steps],
    }
    validate_source_installation_provenance(document)
    return payload


def validate_source_installation_provenance(document) -> bool:
    """Validate typed historical composition, without touching tools or image bytes.

    Digests provide local consistency, not publisher authentication. Candidate
    records require their complete provenance; original records cannot contain it.
    Live execution separately verifies current source/build/base/AVB receipts.
    """
    if type(document.get("schema_version")) is not int or document["schema_version"] != 1:
        raise SourceInstallationError("The installation evidence version is not supported.")
    if document.get("format") == SourceInstallationExecutor.FORMAT:
        if "candidate_provenance" in document:
            raise SourceInstallationError("Candidate evidence cannot be labeled original firmware.")
        return False
    if document.get("format") != SourceInstallationExecutor.CANDIDATE_FORMAT:
        raise SourceInstallationError("The installation evidence type is not supported.")
    payload = document.get("candidate_provenance")
    expected_fields = set(CandidateInstallationRecipe.__dataclass_fields__) - {
        "archive_path",
        "recipe_digest",
    }
    if (
        not isinstance(payload, dict)
        or set(payload) != expected_fields
        or not _sha(document.get("recipe_digest"))
        or _digest(payload) != document["recipe_digest"]
        or type(payload["composition_version"]) is not int
        or payload["composition_version"] != 2
        or any(
            _digest(payload[name]) != _digest(document.get(name))
            for name in ("project_id", "source_sha256", "script_sha256", "steps", "wipe", "reboot")
        )
        or any(
            not isinstance(payload[name], str)
            or not re.fullmatch(r"[a-z0-9-]{1,64}", payload[name])
            for name in ("project_id", "procedure_project_id")
        )
        or payload["project_id"] == payload["procedure_project_id"]
        or any(
            not _sha(payload[name])
            for name in (
                "source_sha256",
                "procedure_source_sha256",
                "procedure_recipe_digest",
                "base_receipt_digest",
                "build_receipt_digest",
                "build_plan_digest",
                "build_pack_sha256",
                "avb_receipt_digest",
                "signing_receipt_digest",
                "signed_assembly_receipt_digest",
                "checksums_sha256",
            )
        )
        or any(
            payload[name] != "" and not _sha(payload[name])
            for name in ("build_recipe_digest", "build_toolchain_digest")
        )
        or payload["script_sha256"] != POPSICLE_SCRIPT_SHA256
        or payload["expected_product"] != "popsicle"
        or not isinstance(payload["expected_manufacturer"], str)
        or payload["expected_manufacturer"].casefold() != "xiaomi"
        or payload["target_slot"] != "a"
        or payload["requires_critical_unlock"] is not True
        or any(type(payload[name]) is not bool for name in ("wipe", "reboot"))
        or not isinstance(payload["label"], str)
        or not 0 < len(payload["label"]) <= 1024
        or not isinstance(payload["warnings"], (list, tuple))
        or len(payload["warnings"]) > 64
        or any(not isinstance(item, str) or len(item) > 8192 for item in payload["warnings"])
    ):
        raise SourceInstallationError("The rebuilt installation provenance is missing or changed.")
    script = _relative_member(payload["script_member"])
    checksums = _relative_member(payload["checksums_member"])
    if script.name != "flash_all.sh" or checksums != script.parent / "SHA256SUMS":
        raise SourceInstallationError("The rebuilt installation changed its base procedure.")
    images, origins = payload["images"], payload["origins"]
    roles = (*POPSICLE_PHYSICAL_PARTITIONS, "super", "vbmeta_system", "vbmeta")
    if any(not isinstance(items, (list, tuple)) or len(items) != 50 for items in (images, origins)):
        raise SourceInstallationError(
            "The rebuilt installation needs exactly 50 explicit image origins."
        )
    for image, origin, role in zip(images, origins, roles, strict=True):
        if (
            not isinstance(image, dict)
            or set(image) != {"member", "sha256", "size_bytes", "expanded_size_bytes"}
            or not _sha(image["sha256"])
            or any(
                type(image[name]) is not int or not 0 < image[name] <= 1024**4
                for name in ("size_bytes", "expanded_size_bytes")
            )
            or _relative_member(image["member"]) != script.parent / "images" / f"{role}.img"
            or not isinstance(origin, dict)
            or set(origin) != {"member", "source_kind", "relative_path"}
            or origin["member"] != image["member"]
        ):
            raise SourceInstallationError("The rebuilt installation image origins are invalid.")
        if role in {"super", "vbmeta_system"}:
            relative = _relative_member(origin["relative_path"], canonical=True)
            valid_final = (
                origin["source_kind"] == "signed-final"
                and len(relative.parts) == 5
                and relative.name == f"{role}.img"
                and (
                    (
                        role == "super"
                        and relative.parts[:3]
                        == ("working_roms", payload["project_id"], "signed-assembly")
                        and relative.parts[3].startswith(payload["signing_receipt_digest"][:16])
                    )
                    or (
                        role == "vbmeta_system"
                        and relative.parts[:3]
                        == ("projects", payload["project_id"], "signing-evidence")
                    )
                )
                and bool(re.fullmatch(r"[a-f0-9-]{8,64}", relative.parts[3]))
            )
            if not valid_final:
                raise SourceInstallationError("A rebuilt image is not its exact final signed role.")
        elif origin["source_kind"] != "base-package" or origin["relative_path"] != "":
            raise SourceInstallationError("An unchanged base image has an unexpected source.")
    expected = [
        {"action": "set_active", "partition": "", "image_member": "", "slot": "a", "chunk_size": ""}
    ]
    for image, role in zip(images, roles, strict=True):
        expected.append(
            {
                "action": "flash",
                "partition": "super" if role == "super" else role + "_a",
                "image_member": image["member"],
                "slot": "",
                "chunk_size": "700M" if role == "super" else "",
            }
        )
    if payload["wipe"]:
        expected.extend(
            {"action": "erase", "partition": part, "image_member": "", "slot": "", "chunk_size": ""}
            for part in ("metadata", "userdata")
        )
    expected.append(dict(expected[0]))
    if payload["reboot"]:
        expected.append(
            {"action": "reboot", "partition": "", "image_member": "", "slot": "", "chunk_size": ""}
        )
    if _digest(payload["steps"]) != _digest(expected):
        raise SourceInstallationError(
            "The rebuilt installation changed the reviewed procedure order."
        )
    snapshots = document.get("image_snapshots")
    if snapshots is not None and (
        not isinstance(snapshots, list)
        or len(snapshots) != len(images)
        or any(
            not isinstance(snapshot, dict)
            or any(snapshot.get(name) != image[name] for name in image)
            for snapshot, image in zip(snapshots, images, strict=True)
        )
    ):
        raise SourceInstallationError("Private images do not match the rebuilt composition.")
    return True


def _now() -> str:
    return datetime.now(UTC).isoformat()


def validate_source_installation_boot_binding(
    flash: LocalFlashService, device: AndroidDevice, result: SourceInstallationResult
) -> dict[str, str]:
    """Read a genuine, exact-device transport record, never promote it to health proof.

    This validates the journal contract and its measured ordered results, not the
    current source/image bytes. Re-reading historical evidence must not flash or
    claim that those bytes remain present on the phone.
    """
    if (
        not isinstance(result, SourceInstallationResult)
        or not isinstance(result.state, LocalFlashState)
        or result.boot_verified is not False
        or any(
            type(value) is not bool
            for value in (
                result.phone_change_attempted,
                result.phone_state_uncertain,
                result.reboot_requested,
                result.android_arrival_verified,
            )
        )
        or result.phone_change_attempted != result.phone_state_uncertain
    ):
        raise SourceInstallationError(
            "The linked installation result is not a local transport receipt."
        )
    path = result.receipt_path
    if (
        not isinstance(path, Path)
        or path.parent != flash.workspace / "guardian" / "source-installation"
        or not re.fullmatch(r"[a-f0-9]{32}\.json", path.name)
    ):
        raise SourceInstallationError(
            "The installation receipt is outside its exact private journal directory."
        )
    document = read_json_object(
        path, boundary=flash.workspace, maximum_bytes=SourceInstallationExecutor.MAX_JOURNAL_BYTES
    )
    content = {key: value for key, value in document.items() if key != "record_digest"}
    digest = document.get("record_digest")
    if not _sha(digest) or _digest(content) != digest:
        raise SourceInstallationError("The installation journal digest is invalid.")
    required = {
        "format",
        "schema_version",
        "plan_id",
        "plan_digest",
        "project_id",
        "source_sha256",
        "recipe_digest",
        "script_sha256",
        "device_key",
        "product",
        "fastboot_sha256",
        "initial_slot",
        "steps",
        "wipe",
        "reboot",
        "consent",
        "started_at",
        "completed_at",
        "state",
        "summary",
        "in_flight_step",
        "results",
        "phone_change_attempted",
        "phone_state_uncertain",
        "reboot_requested",
        "android_arrival_verified",
        "boot_verified",
        "readback_verified",
        "production_certification",
        "record_digest",
    }
    candidate = validate_source_installation_provenance(document)
    if candidate:
        required.add("candidate_provenance")
    if not required <= set(document) <= required | {"snapshots_verified", "image_snapshots"}:
        raise SourceInstallationError("The installation journal fields do not match its contract.")
    aliases = {
        value.casefold()
        for value in (device.product, device.codename, device.vendor_device)
        if value
    }
    if (device.codename and device.codename.strip().casefold() != "popsicle") or (
        device.manufacturer and device.manufacturer.strip().casefold() != "xiaomi"
    ):
        raise SourceInstallationError(
            "The known phone identity contradicts this installation receipt."
        )
    if (
        type(document["schema_version"]) is not int
        or document["schema_version"] != 1
        or document["plan_id"] != path.stem
        or document["device_key"] != flash.privacy.pseudonym(device.serial)
        or document["product"] != "popsicle"
        or (aliases and "popsicle" not in aliases)
        or document["script_sha256"] != POPSICLE_SCRIPT_SHA256
        or document["consent"] != "explicit-source-installation-exact-plan"
        or any(
            not _sha(document[key])
            for key in ("plan_digest", "source_sha256", "recipe_digest", "fastboot_sha256")
        )
        or document["initial_slot"] not in {"a", "b"}
        or any(type(document[key]) is not bool for key in ("wipe", "reboot"))
        or any(
            document[key] is not False
            for key in ("boot_verified", "readback_verified", "production_certification")
        )
        or document["state"] != result.state.value
        or document["summary"] != result.summary
        or any(
            document[key] is not getattr(result, key)
            for key in (
                "phone_change_attempted",
                "phone_state_uncertain",
                "reboot_requested",
                "android_arrival_verified",
            )
        )
        or _digest(document["results"]) != _digest([asdict(item) for item in result.results])
    ):
        raise SourceInstallationError(
            "The installation record does not match this exact phone and result."
        )
    try:
        start, end = (
            datetime.fromisoformat(document[key]) for key in ("started_at", "completed_at")
        )
        if start.utcoffset() is None or end.utcoffset() is None or end < start:
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise SourceInstallationError(
            "The installation record has invalid completion times."
        ) from exc
    steps = document["steps"]
    expected = [("set_active", "", "a", "")]
    expected.extend(("flash", name + "_a", "", "") for name in POPSICLE_PHYSICAL_PARTITIONS)
    expected.extend(
        (
            ("flash", "super", "", "700M"),
            ("flash", "vbmeta_system_a", "", ""),
            ("flash", "vbmeta_a", "", ""),
        )
    )
    if document["wipe"]:
        expected.extend((("erase", "metadata", "", ""), ("erase", "userdata", "", "")))
    expected.append(("set_active", "", "a", ""))
    if document["reboot"]:
        expected.append(("reboot", "", "", ""))
    if not isinstance(steps, list) or len(steps) != len(expected):
        raise SourceInstallationError("The source procedure has missing installation steps.")
    commands = []
    for step, expected_step in zip(steps, expected, strict=True):
        if (
            not isinstance(step, dict)
            or set(step) != {"action", "partition", "image_member", "slot", "chunk_size"}
            or tuple(step[key] for key in ("action", "partition", "slot", "chunk_size"))
            != expected_step
        ):
            raise SourceInstallationError(
                "The installation record changed the source-declared order."
            )
        action, partition, slot, chunk = expected_step
        member = step["image_member"]
        if (
            not isinstance(member, str)
            or (
                action == "flash"
                and (
                    not member
                    or member.startswith("/")
                    or "\\" in member
                    or ".." in PurePosixPath(member).parts
                    or PurePosixPath(member).as_posix() in {"", "."}
                    or any(ord(char) < 32 or ord(char) == 127 for char in member)
                )
            )
            or (action != "flash" and member)
        ):
            raise SourceInstallationError("The installation image member is invalid.")
        command = ("fastboot", "-s", "<device>")
        if action == "flash":
            command += (("-S", chunk) if chunk else ()) + ("flash", partition, "<reviewed-image>")
        elif action == "set_active":
            command += (action, slot)
        elif action == "erase":
            command += (action, partition)
        else:
            command += (action,)
        commands.append(command)
    if (
        not isinstance(result.results, tuple)
        or len(result.results) > len(steps)
        or (result.results and not result.phone_change_attempted)
    ):
        raise SourceInstallationError("The installation result count is inconsistent.")
    for index, entry in enumerate(result.results):
        step = steps[index]
        if (
            not isinstance(entry, SourceInstallationStepResult)
            or type(entry.index) is not int
            or entry.index != index
            or entry.action != step["action"]
            or entry.partition != step["partition"]
            or entry.command != commands[index]
            or type(entry.returncode) is not int
            or type(entry.timed_out) is not bool
            or not isinstance(entry.output, str)
            or len(entry.output) > 8192
            or entry.verified_slot not in ({"", "a"} if entry.action == "set_active" else {""})
        ):
            raise SourceInstallationError(
                "An installation result does not match its declared step."
            )
    if result.phone_change_attempted:
        snapshots = document.get("image_snapshots")
        if (
            document.get("snapshots_verified") is not True
            or not isinstance(snapshots, list)
            or len(snapshots) != 50
        ):
            raise SourceInstallationError(
                "The installation has no complete private image evidence."
            )
        expected_members = {step["image_member"] for step in steps if step["action"] == "flash"}
        if len(expected_members) != 50:
            raise SourceInstallationError("The installation image inventory is incomplete.")
        observed_members = set()
        for item in snapshots:
            if (
                not isinstance(item, dict)
                or set(item)
                != {"member", "relative_path", "sha256", "size_bytes", "expanded_size_bytes"}
                or not _sha(item.get("sha256"))
                or any(
                    type(item.get(key)) is not int or item[key] <= 0
                    for key in ("size_bytes", "expanded_size_bytes")
                )
            ):
                raise SourceInstallationError(
                    "A private installation snapshot has invalid evidence."
                )
            expected_path = f"guardian/source-installation/images/{path.stem}/{item['sha256']}.img"
            if (
                item["relative_path"] != expected_path
                or item["member"] not in expected_members
                or item["member"] in observed_members
            ):
                raise SourceInstallationError(
                    "A private snapshot is not bound to this installation."
                )
            observed_members.add(item["member"])
    if result.state is LocalFlashState.COMPLETED and (
        len(result.results) != len(steps)
        or not result.phone_change_attempted
        or not all(entry.completed for entry in result.results)
        or any(
            entry.action == "set_active" and entry.verified_slot != "a" for entry in result.results
        )
        or document["in_flight_step"] is not None
        or result.reboot_requested is not document["reboot"]
    ):
        raise SourceInstallationError(
            "The completed installation is missing measured command results."
        )
    if result.state is LocalFlashState.REJECTED and result.phone_change_attempted:
        raise SourceInstallationError("A rejected installation cannot claim phone changes.")
    return {
        "relative_path": path.relative_to(flash.workspace).as_posix(),
        "record_digest": digest,
        "plan_digest": document["plan_digest"],
        "device_key": document["device_key"],
    }


def _sha(value) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _digest(value) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False
        ).encode()
    ).hexdigest()
