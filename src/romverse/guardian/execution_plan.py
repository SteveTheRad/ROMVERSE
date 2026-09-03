from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path, PurePosixPath
from uuid import uuid4

from romverse.device.models import AndroidDevice
from romverse.device_packs.models import DeviceWriteContract, DeviceWriteTransport
from romverse.device_packs.registry import DevicePackRegistry
from romverse.guardian.artifact_binding import (
    GuardianArtifactBindingReceipt,
    GuardianArtifactBindingService,
)
from romverse.guardian.flash_handoff import FlashMode
from romverse.guardian.invariants import contains_bootloader_relock
from romverse.guardian.manifest_review import (
    GuardianManifestReview,
    GuardianManifestReviewService,
)
from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    ensure_private_directory,
    read_json_object,
)
from romverse.infrastructure.process import CommandRunner, SubprocessRunner
from romverse.infrastructure.tools import ToolStatus
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.rom.readiness import BuildReadinessReport


class ExecutionPlanPhase(StrEnum):
    PRECONDITION = "precondition"
    WRITE = "write"


@dataclass(frozen=True, slots=True)
class GuardianPlannedCommand:
    """One inert command template derived from exact, current evidence."""

    order: int
    operation_id: str
    phase: ExecutionPlanPhase
    executable: str
    arguments: tuple[str, ...]
    transport: DeviceWriteTransport
    partition: str
    target_slot: str
    artifact_relative_path: str
    artifact_sha256: str
    artifact_size_bytes: int
    expected_result: str
    phone_changes: bool


@dataclass(frozen=True, slots=True)
class GuardianExecutionPlan:
    """Tamper-evident command preview with deliberately zero execution authority."""

    schema_version: int
    plan_id: str
    created_at: str
    project_id: str
    handoff_digest: str
    readiness_evidence_digest: str
    manifest_digest: str
    artifact_binding_digest: str
    source_sha256: str
    device_key: str
    device_name: str
    codename: str
    mode: FlashMode
    device_pack_id: str
    device_pack_version: str
    device_pack_sha256: str
    write_contract_id: str
    write_contract_version: int
    write_attestation_sha256: str
    post_write_verification_contract_id: str
    post_write_verification_contract_version: int
    post_write_verification_contract_digest: str
    post_write_readback_count: int
    post_boot_property_count: int
    post_boot_timeout_seconds: int
    commands: tuple[GuardianPlannedCommand, ...]
    blockers: tuple[str, ...]
    plan_status: str
    final_consent_available: bool
    execution_authority: str
    phone_changed: bool
    bootloader_relock_allowed: bool
    plan_digest: str


class GuardianExecutionPlanService:
    """Compile and reload an exact inert plan before any final-consent milestone exists."""

    FORMAT = "romverse.guardian-execution-plan"
    SCHEMA_VERSION = 2
    LATEST_NAME = "execution-plan.romverse"
    MAX_BYTES = 256 * 1024
    MAX_COMMANDS = GuardianArtifactBindingService.MAX_WRITES * 3 + 4
    TARGET_TOKEN = "{CURRENT_EXACT_TARGET}"
    WORKSPACE_TOKEN = "{ROMVERSE_WORKSPACE}"
    MISSING_VERIFICATION_STATUS = "blocked-missing-exact-post-write-verification"
    MISSING_VERIFICATION_BLOCKERS = (
        "The signed write contract requires verification after every image, but it does not yet define an exact readback or post-boot Device DNA postcondition.",
        "Automatic mode transitions, slot activation, reboot, wipe, rollback, and recovery commands are absent and must never be inferred from filenames or generic Fastboot behavior.",
    )
    VERIFIED_CONTRACT_STATUS = "blocked-missing-typed-execution-gateway"
    VERIFIED_CONTRACT_BLOCKERS = (
        "The signed Device Pack defines exact partition readback digests and post-boot Device DNA, but ROMVERSE does not yet have a verified execution gateway, immutable execution receipt, or final-consent authority.",
        "Automatic mode transitions, slot activation, reboot, wipe, rollback, and recovery commands are absent and must never be inferred from filenames or generic Fastboot behavior.",
    )
    PLAN_STATUS = MISSING_VERIFICATION_STATUS
    BLOCKERS = MISSING_VERIFICATION_BLOCKERS

    def __init__(
        self,
        store: RomProjectStore,
        registry: DevicePackRegistry,
        tool_statuses: tuple[ToolStatus, ...] = (),
        avbtool: Path | None = None,
        runner: CommandRunner | None = None,
    ) -> None:
        self.store = store
        self.registry = registry
        self.tool_statuses = tool_statuses
        self.avbtool = avbtool
        self.runner = runner or SubprocessRunner()

    def compile(
        self,
        project_id: str,
        report: BuildReadinessReport,
        device: AndroidDevice,
    ) -> GuardianExecutionPlan:
        manifest, binding, write_contract = self._current_context(project_id, report, device)
        commands = self._commands(manifest)
        verification = self._verification_metadata(write_contract)
        blockers, plan_status = self._plan_boundary(write_contract)
        payload: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "plan_id": uuid4().hex,
            "created_at": datetime.now(UTC).isoformat(),
            "project_id": manifest.project_id,
            "handoff_digest": manifest.handoff_digest,
            "readiness_evidence_digest": manifest.readiness_evidence_digest,
            "manifest_digest": manifest.manifest_digest,
            "artifact_binding_digest": binding.binding_digest,
            "source_sha256": manifest.source_sha256,
            "device_key": manifest.device_key,
            "device_name": manifest.device_name,
            "codename": manifest.codename,
            "mode": manifest.mode,
            "device_pack_id": manifest.device_pack_id,
            "device_pack_version": manifest.device_pack_version,
            "device_pack_sha256": manifest.device_pack_sha256,
            "write_contract_id": binding.write_contract_id,
            "write_contract_version": binding.write_contract_version,
            "write_attestation_sha256": binding.write_attestation_sha256,
            **verification,
            "commands": [asdict(command) for command in commands],
            "blockers": blockers,
            "plan_status": plan_status,
            "final_consent_available": False,
            "execution_authority": "none",
            "phone_changed": False,
            "bootloader_relock_allowed": False,
        }
        plan = GuardianExecutionPlan(
            **{key: value for key, value in payload.items() if key != "commands"},
            commands=commands,
            plan_digest=_digest(payload),
        )
        self.validate(plan)
        self._write(plan)
        return plan

    def load(
        self,
        project_id: str,
        report: BuildReadinessReport,
        device: AndroidDevice,
    ) -> GuardianExecutionPlan | None:
        try:
            data = read_json_object(
                self._root(project_id) / self.LATEST_NAME,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            if (
                set(data) != {"format", *(field.name for field in fields(GuardianExecutionPlan))}
                or data.pop("format") != self.FORMAT
            ):
                return None
            raw_commands = data.pop("commands")
            raw_blockers = data.get("blockers")
            command_fields = {field.name for field in fields(GuardianPlannedCommand)}
            if (
                not isinstance(raw_commands, list)
                or not 1 <= len(raw_commands) <= self.MAX_COMMANDS
                or any(
                    not isinstance(item, dict) or set(item) != command_fields
                    for item in raw_commands
                )
                or not isinstance(raw_blockers, list)
                or any(type(item) is not str for item in raw_blockers)
            ):
                return None
            commands = tuple(
                GuardianPlannedCommand(
                    **{
                        **item,
                        "phase": ExecutionPlanPhase(str(item["phase"])),
                        "transport": DeviceWriteTransport(str(item["transport"])),
                        "arguments": tuple(item["arguments"]),
                    }
                )
                for item in raw_commands
            )
            data["mode"] = FlashMode(str(data["mode"]))
            data["blockers"] = tuple(raw_blockers)
            plan = GuardianExecutionPlan(**data, commands=commands)
            self.validate(plan)
            manifest, binding, write_contract = self._current_context(project_id, report, device)
            if not self._matches(plan, manifest, binding, write_contract):
                return None
            return plan
        except (
            LocalStoreError,
            OSError,
            TypeError,
            ValueError,
            KeyError,
            ProjectError,
            json.JSONDecodeError,
        ):
            return None

    def validate(self, plan: GuardianExecutionPlan) -> None:
        payload = asdict(plan)
        expected = str(payload.pop("plan_digest", ""))
        serialized_commands = tuple(
            (command.executable, *command.arguments) for command in plan.commands
        )
        if (
            type(plan.schema_version) is not int
            or plan.schema_version != self.SCHEMA_VERSION
            or not _hex(plan.plan_id, 32)
            or not _aware_timestamp(plan.created_at)
            or not _clean(plan.project_id, 128)
            or not _hex(plan.handoff_digest, 64)
            or not _hex(plan.readiness_evidence_digest, 64)
            or not _hex(plan.manifest_digest, 64)
            or not _hex(plan.artifact_binding_digest, 64)
            or not _hex(plan.source_sha256, 64)
            or not _hex(plan.device_key, 20)
            or not _clean(plan.device_name, 120)
            or not _clean(plan.codename, 80)
            or not isinstance(plan.mode, FlashMode)
            or not _clean(plan.device_pack_id, 128)
            or not _clean(plan.device_pack_version, 80)
            or not _hex(plan.device_pack_sha256, 64)
            or not _clean(plan.write_contract_id, 80)
            or type(plan.write_contract_version) is not int
            or plan.write_contract_version not in {1, 2}
            or not _hex(plan.write_attestation_sha256, 64)
            or not self._valid_verification_metadata(plan)
            or not 1 <= len(plan.commands) <= self.MAX_COMMANDS
            or tuple(command.order for command in plan.commands)
            != tuple(range(1, len(plan.commands) + 1))
            or any(not self._valid_command(command) for command in plan.commands)
            or contains_bootloader_relock(serialized_commands)
            or (plan.blockers, plan.plan_status) != self._plan_boundary_from_metadata(plan)
            or type(plan.final_consent_available) is not bool
            or plan.final_consent_available
            or plan.execution_authority != "none"
            or type(plan.phone_changed) is not bool
            or plan.phone_changed
            or type(plan.bootloader_relock_allowed) is not bool
            or plan.bootloader_relock_allowed
            or not _hex(expected, 64)
            or expected != _digest(payload)
        ):
            raise ProjectError("Guardian execution plan failed integrity or safety validation")

    def _current_context(
        self,
        project_id: str,
        report: BuildReadinessReport,
        device: AndroidDevice,
    ):
        manifests = GuardianManifestReviewService(self.store, self.registry)
        manifest = manifests.load(project_id)
        if (
            manifest is None
            or manifest.review_status != "artifact-bound-review-only"
            or not manifest.partition_writes
            or not manifests.matches_current(manifest, report, device)
        ):
            raise ProjectError(
                "A current artifact-bound Guardian manifest review is required before planning commands"
            )
        binding = GuardianArtifactBindingService(
            self.store,
            self.registry,
            self.tool_statuses,
            self.avbtool,
            self.runner,
        ).load(project_id)
        if (
            binding is None
            or binding.binding_digest != manifest.artifact_binding_digest
            or binding.writes != manifest.partition_writes
        ):
            raise ProjectError(
                "Guardian could not rehash the exact current artifact binding before planning"
            )
        pack = next(
            (item for item in self.registry.packs if item.pack_id == manifest.device_pack_id),
            None,
        )
        write_contract = (
            pack.build_contract.partition_write_contract
            if pack is not None and pack.build_contract is not None
            else None
        )
        if (
            write_contract is None
            or write_contract.contract_id != binding.write_contract_id
            or write_contract.version != binding.write_contract_version
            or write_contract.attestation_sha256 != binding.write_attestation_sha256
        ):
            raise ProjectError(
                "Guardian could not bind the current Device Pack write contract to the plan"
            )
        return manifest, binding, write_contract

    def _matches(
        self,
        plan: GuardianExecutionPlan,
        manifest: GuardianManifestReview,
        binding: GuardianArtifactBindingReceipt,
        write_contract: DeviceWriteContract,
    ) -> bool:
        return bool(
            plan.project_id == manifest.project_id
            and plan.handoff_digest == manifest.handoff_digest
            and plan.readiness_evidence_digest == manifest.readiness_evidence_digest
            and plan.manifest_digest == manifest.manifest_digest
            and plan.artifact_binding_digest == binding.binding_digest
            and plan.source_sha256 == manifest.source_sha256
            and plan.device_key == manifest.device_key
            and plan.device_name == manifest.device_name
            and plan.codename == manifest.codename
            and plan.mode is manifest.mode
            and plan.device_pack_id == manifest.device_pack_id
            and plan.device_pack_version == manifest.device_pack_version
            and plan.device_pack_sha256 == manifest.device_pack_sha256
            and plan.write_contract_id == binding.write_contract_id
            and plan.write_contract_version == binding.write_contract_version
            and plan.write_attestation_sha256 == binding.write_attestation_sha256
            and self._plan_verification_metadata(plan)
            == self._verification_metadata(write_contract)
            and (plan.blockers, plan.plan_status) == self._plan_boundary(write_contract)
            and plan.commands == self._commands(manifest)
        )

    @classmethod
    def _verification_metadata(cls, write_contract: DeviceWriteContract) -> dict[str, object]:
        verification = write_contract.post_write_verification_contract
        if verification is None:
            return {
                "post_write_verification_contract_id": "",
                "post_write_verification_contract_version": 0,
                "post_write_verification_contract_digest": "",
                "post_write_readback_count": 0,
                "post_boot_property_count": 0,
                "post_boot_timeout_seconds": 0,
            }
        return {
            "post_write_verification_contract_id": verification.contract_id,
            "post_write_verification_contract_version": verification.version,
            "post_write_verification_contract_digest": _digest(asdict(verification)),
            "post_write_readback_count": len(verification.readbacks),
            "post_boot_property_count": len(verification.post_boot_properties),
            "post_boot_timeout_seconds": verification.boot_timeout_seconds,
        }

    @staticmethod
    def _plan_verification_metadata(plan: GuardianExecutionPlan) -> dict[str, object]:
        return {
            "post_write_verification_contract_id": plan.post_write_verification_contract_id,
            "post_write_verification_contract_version": plan.post_write_verification_contract_version,
            "post_write_verification_contract_digest": plan.post_write_verification_contract_digest,
            "post_write_readback_count": plan.post_write_readback_count,
            "post_boot_property_count": plan.post_boot_property_count,
            "post_boot_timeout_seconds": plan.post_boot_timeout_seconds,
        }

    @classmethod
    def _plan_boundary(cls, write_contract: DeviceWriteContract) -> tuple[tuple[str, ...], str]:
        if write_contract.post_write_verification_contract is None:
            return cls.MISSING_VERIFICATION_BLOCKERS, cls.MISSING_VERIFICATION_STATUS
        return cls.VERIFIED_CONTRACT_BLOCKERS, cls.VERIFIED_CONTRACT_STATUS

    @classmethod
    def _plan_boundary_from_metadata(
        cls, plan: GuardianExecutionPlan
    ) -> tuple[tuple[str, ...], str]:
        if plan.post_write_verification_contract_version == 0:
            return cls.MISSING_VERIFICATION_BLOCKERS, cls.MISSING_VERIFICATION_STATUS
        return cls.VERIFIED_CONTRACT_BLOCKERS, cls.VERIFIED_CONTRACT_STATUS

    @classmethod
    def _valid_verification_metadata(cls, plan: GuardianExecutionPlan) -> bool:
        values = (
            plan.post_write_verification_contract_version,
            plan.post_write_readback_count,
            plan.post_boot_property_count,
            plan.post_boot_timeout_seconds,
        )
        if any(type(value) is not int for value in values):
            return False
        if plan.write_contract_version == 1:
            return bool(
                not plan.post_write_verification_contract_id
                and plan.post_write_verification_contract_version == 0
                and not plan.post_write_verification_contract_digest
                and plan.post_write_readback_count == 0
                and plan.post_boot_property_count == 0
                and plan.post_boot_timeout_seconds == 0
            )
        write_count = sum(command.phase is ExecutionPlanPhase.WRITE for command in plan.commands)
        return bool(
            plan.write_contract_version == 2
            and _clean(plan.post_write_verification_contract_id, 80)
            and plan.post_write_verification_contract_version == 1
            and _hex(plan.post_write_verification_contract_digest, 64)
            and plan.post_write_readback_count == write_count
            and 1 <= plan.post_write_readback_count <= GuardianArtifactBindingService.MAX_WRITES
            and 7 <= plan.post_boot_property_count <= 16
            and 30 <= plan.post_boot_timeout_seconds <= 900
        )

    @classmethod
    def _commands(cls, manifest: GuardianManifestReview) -> tuple[GuardianPlannedCommand, ...]:
        commands: list[GuardianPlannedCommand] = []

        def add_precondition(
            operation_id: str,
            arguments: tuple[str, ...],
            transport: DeviceWriteTransport,
            expected: str,
            *,
            partition: str = "",
            target_slot: str = "none",
        ) -> None:
            commands.append(
                GuardianPlannedCommand(
                    order=len(commands) + 1,
                    operation_id=operation_id,
                    phase=ExecutionPlanPhase.PRECONDITION,
                    executable="fastboot",
                    arguments=arguments,
                    transport=transport,
                    partition=partition,
                    target_slot=target_slot,
                    artifact_relative_path="",
                    artifact_sha256="",
                    artifact_size_bytes=0,
                    expected_result=expected,
                    phone_changes=False,
                )
            )

        first_transport = manifest.partition_writes[0].transport
        add_precondition(
            "guardian.preflight.product",
            ("-s", cls.TARGET_TOKEN, "getvar", "product"),
            first_transport,
            f"Exact product/codename must be {manifest.codename}.",
        )
        add_precondition(
            "guardian.preflight.unlocked",
            ("-s", cls.TARGET_TOKEN, "getvar", "unlocked"),
            first_transport,
            "Bootloader must report unlocked=yes; ROMVERSE never unlocks or relocks it.",
        )
        prior_transport: DeviceWriteTransport | None = None
        for write in manifest.partition_writes:
            if write.transport is not prior_transport:
                expected_mode = "yes" if write.transport is DeviceWriteTransport.FASTBOOTD else "no"
                add_precondition(
                    f"guardian.preflight.mode.{write.order:02d}",
                    ("-s", cls.TARGET_TOKEN, "getvar", "is-userspace"),
                    write.transport,
                    f"is-userspace must report {expected_mode} before the following write; mode changes remain manual and separately verified.",
                )
                prior_transport = write.transport
            if write.target_slot != "none":
                add_precondition(
                    f"guardian.preflight.slot.{write.order:02d}.{write.partition}",
                    (
                        "-s",
                        cls.TARGET_TOKEN,
                        "getvar",
                        f"has-slot:{write.partition}",
                    ),
                    write.transport,
                    "The partition must explicitly report has-slot=yes before using the signed target slot.",
                    partition=write.partition,
                    target_slot=write.target_slot,
                )
            artifact_token = f"{cls.WORKSPACE_TOKEN}/{write.artifact_relative_path}"
            slot_arguments = ("--slot", write.target_slot) if write.target_slot != "none" else ()
            commands.append(
                GuardianPlannedCommand(
                    order=len(commands) + 1,
                    operation_id=f"guardian.write.{write.order:02d}.{write.partition}",
                    phase=ExecutionPlanPhase.WRITE,
                    executable="fastboot",
                    arguments=(
                        "-s",
                        cls.TARGET_TOKEN,
                        *slot_arguments,
                        "flash",
                        write.partition,
                        artifact_token,
                    ),
                    transport=write.transport,
                    partition=write.partition,
                    target_slot=write.target_slot,
                    artifact_relative_path=write.artifact_relative_path,
                    artifact_sha256=write.artifact_sha256,
                    artifact_size_bytes=write.artifact_size_bytes,
                    expected_result=(
                        "Fastboot must return success for this exact hash-bound image; that response "
                        "alone is not proof of a healthy boot or complete post-write verification."
                    ),
                    phone_changes=True,
                )
            )
        return tuple(commands)

    @classmethod
    def _valid_command(cls, command: GuardianPlannedCommand) -> bool:
        common = bool(
            type(command.order) is int
            and 1 <= command.order <= cls.MAX_COMMANDS
            and re.fullmatch(r"[a-z0-9.-]{4,96}", command.operation_id)
            and isinstance(command.phase, ExecutionPlanPhase)
            and command.executable == "fastboot"
            and 4 <= len(command.arguments) <= 9
            and all(_command_token(token) for token in command.arguments)
            and command.arguments[:2] == ("-s", cls.TARGET_TOKEN)
            and isinstance(command.transport, DeviceWriteTransport)
            and command.target_slot in {"a", "b", "none"}
            and _clean(command.expected_result, 400)
            and type(command.phone_changes) is bool
        )
        if not common:
            return False
        if command.phase is ExecutionPlanPhase.PRECONDITION:
            common_getvar = command.arguments in {
                ("-s", cls.TARGET_TOKEN, "getvar", "product"),
                ("-s", cls.TARGET_TOKEN, "getvar", "unlocked"),
                ("-s", cls.TARGET_TOKEN, "getvar", "is-userspace"),
            }
            partition_getvar = bool(
                _partition(command.partition)
                and command.target_slot in {"a", "b"}
                and command.arguments
                == (
                    "-s",
                    cls.TARGET_TOKEN,
                    "getvar",
                    f"has-slot:{command.partition}",
                )
            )
            return bool(
                not command.phone_changes
                and not command.artifact_relative_path
                and not command.artifact_sha256
                and type(command.artifact_size_bytes) is int
                and command.artifact_size_bytes == 0
                and (
                    (common_getvar and not command.partition and command.target_slot == "none")
                    or partition_getvar
                )
            )
        artifact_token = f"{cls.WORKSPACE_TOKEN}/{command.artifact_relative_path}"
        expected_arguments = (
            "-s",
            cls.TARGET_TOKEN,
            *(("--slot", command.target_slot) if command.target_slot != "none" else ()),
            "flash",
            command.partition,
            artifact_token,
        )
        return bool(
            command.phone_changes
            and _partition(command.partition)
            and _safe_relative(command.artifact_relative_path)
            and _hex(command.artifact_sha256, 64)
            and type(command.artifact_size_bytes) is int
            and 0 < command.artifact_size_bytes <= GuardianArtifactBindingService.MAX_ARTIFACT_BYTES
            and command.arguments == expected_arguments
        )

    def _write(self, plan: GuardianExecutionPlan) -> None:
        root = self._root(plan.project_id)
        ensure_private_directory(root, boundary=self.store.workspace)
        atomic_write_json(
            root / self.LATEST_NAME,
            {"format": self.FORMAT, **asdict(plan)},
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_BYTES,
        )

    def _root(self, project_id: str) -> Path:
        self.store.get(project_id)
        return self.store.projects_root / project_id / "guardian"


def _hex(value: object, length: int) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(rf"[0-9a-f]{{{length}}}", value))


def _clean(value: object, maximum: int) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= maximum and "\x00" not in value


def _command_token(value: object) -> bool:
    return bool(_clean(value, 512) and all(32 <= ord(character) < 127 for character in str(value)))


def _partition(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", value))


def _safe_relative(value: object) -> bool:
    if not _clean(value, 512) or "\\" in str(value):
        return False
    path = PurePosixPath(str(value))
    return bool(
        not path.is_absolute()
        and path.parts
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


def _aware_timestamp(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 80:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed <= datetime.now(UTC) + timedelta(minutes=5)


def _digest(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
