from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import shutil
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from romverse.device.dna import DeviceDnaProfile, DeviceDnaStore
from romverse.device.models import AndroidDevice
from romverse.device_packs.models import (
    DeviceBuildContract,
    DevicePack,
    DeviceTransitionOperation,
    DeviceWriteTransport,
)
from romverse.device_packs.registry import DevicePackRegistry
from romverse.infrastructure.local_store import atomic_write_json, read_json_object
from romverse.infrastructure.process import SubprocessRunner
from romverse.infrastructure.tools import ToolStatus
from romverse.rom.build_contracts import DeviceBuildContractService
from romverse.rom.build_execution import LocalDeviceBuildExecutor
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.rom.recovery_evidence import RecoveryEvidenceService


class SimulationSeverity(StrEnum):
    VERIFIED = "verified"
    ATTENTION = "attention"
    BLOCKED = "blocked"


class PartitionIntent(StrEnum):
    WRITE = "write"
    PRESERVE = "preserve"
    ERASE = "erase"


@dataclass(frozen=True, slots=True)
class DigitalTwinPartition:
    name: str
    group: str
    filesystem: str
    capacity_bytes: int
    image_size_bytes: int
    target_slot: str
    intent: PartitionIntent
    artifact: str
    transport: str
    status: SimulationSeverity
    detail: str


@dataclass(frozen=True, slots=True)
class SimulationFinding:
    finding_id: str
    severity: SimulationSeverity
    title: str
    detail: str
    resolution: str
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SimulatedOperation:
    order: int
    operation_id: str
    phase: str
    label: str
    partition: str
    target_slot: str
    transport: str
    artifact: str
    size_bytes: int
    estimated_seconds: int
    result: str
    phone_changed: bool = False


@dataclass(frozen=True, slots=True)
class RollbackRehearsal:
    ready: bool
    strategy: str
    checks: tuple[str, ...]
    missing: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SimulationPlanEdit:
    operation_id: str
    action: str
    new_order: int
    reason: str


@dataclass(frozen=True, slots=True)
class RomSimulationReceipt:
    schema_version: int
    simulation_id: str
    project_id: str
    created_at: str
    source_sha256: str
    device_dna_digest: str
    device_pack_id: str
    device_pack_sha256: str
    device_name: str
    codename: str
    current_build: str
    candidate_build: str
    firmware_relationship: str
    partitions: tuple[DigitalTwinPartition, ...]
    operations: tuple[SimulatedOperation, ...]
    findings: tuple[SimulationFinding, ...]
    rollback: RollbackRehearsal
    total_write_bytes: int
    required_workspace_bytes: int
    available_workspace_bytes: int
    estimated_seconds: int
    minimum_battery_percent: int
    observed_battery_percent: int
    confidence_percent: int
    confidence_label: str
    hardware_unknowns: tuple[str, ...]
    expert_edits: tuple[SimulationPlanEdit, ...]
    parent_simulation_digest: str
    successful: bool
    mission_ready: bool
    phone_changed: bool
    execution_authority: str
    receipt_digest: str


@dataclass(frozen=True, slots=True)
class SimulationMission:
    schema_version: int
    mission_id: str
    project_id: str
    created_at: str
    simulation_id: str
    simulation_digest: str
    operation_ids: tuple[str, ...]
    status: str
    next_action: str
    phone_changed: bool
    execution_authority: str
    mission_digest: str


class RomSimulationService:
    """Build a source-bound digital twin without opening a device transport."""

    FORMAT = "romverse.device-digital-twin-simulation"
    MISSION_FORMAT = "romverse.simulation-mission"
    SCHEMA_VERSION = 1
    RECEIPT_NAME = "device-digital-twin.romverse"
    MISSION_NAME = "simulation-mission.romverse"
    MAX_BYTES = 2 * 1024 * 1024
    MAX_PARTITIONS = 256
    MAX_OPERATIONS = 512
    MAX_EDITS = 64
    BUILD_RESERVE_BYTES = 4 * 1024 * 1024 * 1024

    def __init__(
        self,
        store: RomProjectStore,
        registry: DevicePackRegistry,
        tool_statuses: tuple[ToolStatus, ...] = (),
    ) -> None:
        self.store = store
        self.registry = registry
        self.tool_statuses = tool_statuses

    def rehearse(
        self,
        project_id: str,
        device: AndroidDevice | None = None,
    ) -> RomSimulationReceipt:
        project = self.store.get(project_id)
        if project.original is None:
            raise ProjectError("Import a protected firmware source before opening the Digital Twin")
        dna = DeviceDnaStore(self.store).load(project_id)
        pack = next(
            (item for item in self.registry.packs if item.pack_id == project.device_pack_id),
            None,
        )
        findings: list[SimulationFinding] = []
        if dna is None:
            findings.append(
                self._finding(
                    "device-dna",
                    SimulationSeverity.BLOCKED,
                    "Device DNA is missing or stale",
                    "The simulator cannot invent an Android identity or partition layout.",
                    "Scan Device DNA again for this exact protected firmware source.",
                    (f"projects/{project_id}/{DeviceDnaStore.NAME}",),
                )
            )
        contract = pack.build_contract if pack is not None else None
        exact_pack = bool(
            pack is not None
            and contract is not None
            and contract.source.archive_sha256 == project.original.sha256
        )
        if pack is None:
            findings.append(
                self._finding(
                    "device-pack",
                    SimulationSeverity.BLOCKED,
                    "No Device Pack is selected",
                    "A generic device name is not a partition or boot-chain contract.",
                    "Select an exact source-bound Device Pack.",
                )
            )
        elif not exact_pack:
            findings.append(
                self._finding(
                    "source-contract",
                    SimulationSeverity.BLOCKED,
                    "Device Pack is not bound to this firmware",
                    "The protected source SHA-256 does not match the selected build contract.",
                    "Use a Device Pack reviewed for this exact source, or create a new reviewed contract.",
                )
            )
        else:
            findings.append(
                self._finding(
                    "source-contract",
                    SimulationSeverity.VERIFIED,
                    "Exact source contract",
                    f"Protected source and Device Pack agree at {project.original.sha256[:16]}…",
                    "No action required.",
                )
            )

        self._identity_findings(findings, dna, pack, device)
        partitions, operations = self._model_partitions(
            project_id,
            contract if exact_pack else None,
            findings,
        )
        self._geometry_findings(findings, contract if exact_pack else None)
        self._upgrade_findings(findings, dna)
        self._avb_and_slot_findings(findings, contract if exact_pack else None, dna, device)
        rollback = self._rollback(project_id, contract if exact_pack else None, device)
        findings.append(
            self._finding(
                "rollback",
                SimulationSeverity.VERIFIED if rollback.ready else SimulationSeverity.BLOCKED,
                "Rollback rehearsal ready" if rollback.ready else "Rollback rehearsal incomplete",
                "; ".join(rollback.checks if rollback.ready else rollback.missing),
                "No action required."
                if rollback.ready
                else "Register and verify an external backup, exact stock package, and transition/recovery contract.",
            )
        )

        total_write = sum(item.size_bytes for item in operations if item.phase == "write")
        required_workspace = self._required_workspace(contract)
        available_workspace = shutil.disk_usage(self.store.workspace).free
        if required_workspace > available_workspace:
            findings.append(
                self._finding(
                    "workspace-capacity",
                    SimulationSeverity.BLOCKED,
                    "Insufficient workspace storage",
                    f"The model needs {required_workspace} bytes; {available_workspace} bytes are free.",
                    "Free space on the ROMVERSE data drive before building.",
                )
            )
        else:
            findings.append(
                self._finding(
                    "workspace-capacity",
                    SimulationSeverity.VERIFIED,
                    "Workspace capacity model passed",
                    f"{available_workspace} bytes free for an estimated {required_workspace}-byte build envelope.",
                    "No action required.",
                )
            )

        seconds = sum(item.estimated_seconds for item in operations)
        minimum_battery = min(80, max(50, 45 + seconds // 900 * 5))
        observed_battery = (
            device.battery_percent if device and device.battery_percent is not None else -1
        )
        if observed_battery >= 0 and observed_battery < minimum_battery:
            findings.append(
                self._finding(
                    "battery",
                    SimulationSeverity.BLOCKED,
                    "Battery margin is too low",
                    f"Observed {observed_battery}%; this rehearsal requires at least {minimum_battery}%.",
                    "Charge the phone and capture fresh Device DNA before a real operation.",
                )
            )
        elif observed_battery >= 0:
            findings.append(
                self._finding(
                    "battery",
                    SimulationSeverity.VERIFIED,
                    "Battery model passed",
                    f"Observed {observed_battery}%; model minimum {minimum_battery}%.",
                    "Recheck immediately before final consent.",
                )
            )
        else:
            findings.append(
                self._finding(
                    "battery",
                    SimulationSeverity.ATTENTION,
                    "Live battery cannot be rehearsed offline",
                    f"The model minimum is {minimum_battery}%; no current device reading is available.",
                    "Reconnect the exact phone and refresh Device DNA before final consent.",
                )
            )

        hardware_unknowns = (
            "USB stability and cable integrity cannot be proven by software simulation.",
            "Bootloader acceptance, storage wear, thermals and power loss require the physical phone.",
            "First boot, radio, cameras, biometrics and encryption must be observed after installation.",
            "The simulation has no execution authority and did not send a command to a phone.",
        )
        blocker_count = sum(item.severity is SimulationSeverity.BLOCKED for item in findings)
        attention_count = sum(item.severity is SimulationSeverity.ATTENTION for item in findings)
        confidence = max(0, min(92, 96 - blocker_count * 18 - attention_count * 5))
        successful = bool(operations) and blocker_count == 0
        payload: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "simulation_id": uuid4().hex,
            "project_id": project_id,
            "created_at": datetime.now(UTC).isoformat(),
            "source_sha256": project.original.sha256,
            "device_dna_digest": dna.profile_digest if dna is not None else "",
            "device_pack_id": pack.pack_id if pack is not None else "",
            "device_pack_sha256": pack.sha256 if pack is not None else "",
            "device_name": self._fact(dna, "identity.marketing_name")
            or (device.display_name if device else "Unconfirmed Android"),
            "codename": self._fact(dna, "identity.codename") or (device.codename if device else ""),
            "current_build": self._fact(dna, "software.rom")
            or (device.rom_display if device else ""),
            "candidate_build": self._fact(dna, "software.build"),
            "firmware_relationship": self._fact(dna, "firmware.upgrade_relationship"),
            "partitions": partitions,
            "operations": operations,
            "findings": tuple(findings),
            "rollback": rollback,
            "total_write_bytes": total_write,
            "required_workspace_bytes": required_workspace,
            "available_workspace_bytes": available_workspace,
            "estimated_seconds": seconds,
            "minimum_battery_percent": minimum_battery,
            "observed_battery_percent": observed_battery,
            "confidence_percent": confidence,
            "confidence_label": self._confidence_label(confidence, blocker_count),
            "hardware_unknowns": hardware_unknowns,
            "expert_edits": (),
            "parent_simulation_digest": "",
            "successful": successful,
            "mission_ready": successful,
            "phone_changed": False,
            "execution_authority": "none",
        }
        receipt = RomSimulationReceipt(**payload, receipt_digest=_digest(payload))
        self._save(receipt)
        return receipt

    def revise(
        self,
        receipt: RomSimulationReceipt,
        edits: tuple[SimulationPlanEdit, ...],
    ) -> RomSimulationReceipt:
        """Create an inert expert what-if revision; never mutate the signed operation."""

        self.validate(receipt)
        if not edits or len(edits) > self.MAX_EDITS:
            raise ProjectError("Choose between 1 and 64 bounded Digital Twin edits")
        known = {item.operation_id for item in receipt.operations}
        revised = list(receipt.operations)
        for edit in edits:
            if edit.operation_id not in known:
                raise ProjectError("Expert edit refers to an unknown simulated operation")
            if edit.action not in {"move", "exclude"}:
                raise ProjectError("Expert edits may only move or exclude simulated operations")
            if not 1 <= edit.new_order <= len(revised):
                raise ProjectError("Expert operation order is outside the simulated sequence")
            if not _clean(edit.reason, 300):
                raise ProjectError("Every expert edit needs a concise reason")
            current = next(item for item in revised if item.operation_id == edit.operation_id)
            revised.remove(current)
            if edit.action == "exclude":
                current = replace(
                    current,
                    result="EXPERT EXCLUDED • requires a new signed contract",
                )
            revised.insert(edit.new_order - 1, current)
        operations = tuple(replace(item, order=index) for index, item in enumerate(revised, 1))
        finding = self._finding(
            "expert-plan-divergence",
            SimulationSeverity.BLOCKED,
            "Expert what-if plan differs from the signed contract",
            "The revised order is available for inspection, but it cannot inherit Device Pack authority.",
            "Review the revision, then author and independently validate a new Device Pack contract before any real operation.",
        )
        revised_receipt = replace(
            receipt,
            simulation_id=uuid4().hex,
            created_at=datetime.now(UTC).isoformat(),
            operations=operations,
            findings=(*receipt.findings, finding),
            expert_edits=edits,
            parent_simulation_digest=receipt.receipt_digest,
            confidence_percent=max(0, receipt.confidence_percent - 20),
            confidence_label="BLOCKED REVISION",
            successful=False,
            mission_ready=False,
            receipt_digest="",
        )
        revised_receipt = replace(
            revised_receipt,
            receipt_digest=_digest(
                {
                    key: value
                    for key, value in asdict(revised_receipt).items()
                    if key != "receipt_digest"
                }
            ),
        )
        self._save(revised_receipt)
        return revised_receipt

    def create_mission(self, receipt: RomSimulationReceipt) -> SimulationMission:
        self.validate(receipt)
        current = self.load(receipt.project_id)
        if current is None or current.receipt_digest != receipt.receipt_digest:
            raise ProjectError("Rehearse the current Digital Twin before creating a mission")
        if not receipt.successful or not receipt.mission_ready or receipt.expert_edits:
            raise ProjectError(
                "Resolve every Digital Twin blocker before creating a ROM Studio mission"
            )
        payload: dict[str, object] = {
            "schema_version": 1,
            "mission_id": uuid4().hex,
            "project_id": receipt.project_id,
            "created_at": datetime.now(UTC).isoformat(),
            "simulation_id": receipt.simulation_id,
            "simulation_digest": receipt.receipt_digest,
            "operation_ids": tuple(item.operation_id for item in receipt.operations),
            "status": "prepared-for-rom-studio-review",
            "next_action": (
                "Review the exact simulated sequence in ROM Studio; "
                "Guardian consent remains separate."
            ),
            "phone_changed": False,
            "execution_authority": "none",
        }
        mission = SimulationMission(**payload, mission_digest=_digest(payload))
        atomic_write_json(
            self.store.projects_root / receipt.project_id / self.MISSION_NAME,
            {"format": self.MISSION_FORMAT, **asdict(mission)},
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_BYTES,
        )
        return mission

    def load_mission(self, project_id: str) -> SimulationMission | None:
        try:
            data = read_json_object(
                self.store.projects_root / project_id / self.MISSION_NAME,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            if data.pop("format") != self.MISSION_FORMAT:
                return None
            data["operation_ids"] = tuple(data["operation_ids"])
            mission = SimulationMission(**data)
            payload = asdict(mission)
            digest = payload.pop("mission_digest", "")
            receipt = self.load(project_id)
            if (
                mission.schema_version != 1
                or not re.fullmatch(r"[0-9a-f]{32}", mission.mission_id)
                or mission.project_id != project_id
                or receipt is None
                or not receipt.successful
                or receipt.expert_edits
                or mission.simulation_id != receipt.simulation_id
                or mission.simulation_digest != receipt.receipt_digest
                or mission.operation_ids != tuple(item.operation_id for item in receipt.operations)
                or mission.status != "prepared-for-rom-studio-review"
                or mission.phone_changed
                or mission.execution_authority != "none"
                or digest != _digest(payload)
            ):
                return None
            return mission
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            json.JSONDecodeError,
            ProjectError,
        ):
            return None

    def load(self, project_id: str) -> RomSimulationReceipt | None:
        path = self.store.projects_root / project_id / self.RECEIPT_NAME
        try:
            data = read_json_object(
                path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            if data.pop("format") != self.FORMAT:
                return None
            raw_partitions = data.pop("partitions")
            raw_operations = data.pop("operations")
            raw_findings = data.pop("findings")
            raw_rollback = data.pop("rollback")
            raw_edits = data.pop("expert_edits")
            data["hardware_unknowns"] = tuple(data["hardware_unknowns"])
            receipt = RomSimulationReceipt(
                **data,
                partitions=tuple(
                    DigitalTwinPartition(
                        **{
                            **item,
                            "intent": PartitionIntent(item["intent"]),
                            "status": SimulationSeverity(item["status"]),
                        }
                    )
                    for item in raw_partitions
                ),
                operations=tuple(SimulatedOperation(**item) for item in raw_operations),
                findings=tuple(
                    SimulationFinding(
                        **{
                            **item,
                            "severity": SimulationSeverity(item["severity"]),
                            "evidence_refs": tuple(item.get("evidence_refs", ())),
                        }
                    )
                    for item in raw_findings
                ),
                rollback=RollbackRehearsal(
                    **{
                        **raw_rollback,
                        "checks": tuple(raw_rollback["checks"]),
                        "missing": tuple(raw_rollback["missing"]),
                    }
                ),
                expert_edits=tuple(SimulationPlanEdit(**item) for item in raw_edits),
            )
            self.validate(receipt)
            project = self.store.get(project_id)
            if project.original is None or receipt.source_sha256 != project.original.sha256:
                return None
            return receipt
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            json.JSONDecodeError,
            ProjectError,
        ):
            return None

    def validate(self, receipt: RomSimulationReceipt) -> None:
        payload = asdict(receipt)
        expected = payload.pop("receipt_digest", "")
        if (
            receipt.schema_version != self.SCHEMA_VERSION
            or not re.fullmatch(r"[0-9a-f]{32}", receipt.simulation_id)
            or not re.fullmatch(r"[0-9a-f]{64}", receipt.source_sha256)
            or receipt.phone_changed
            or receipt.execution_authority != "none"
            or len(receipt.partitions) > self.MAX_PARTITIONS
            or len(receipt.operations) > self.MAX_OPERATIONS
            or len(receipt.expert_edits) > self.MAX_EDITS
            or any(item.phone_changed for item in receipt.operations)
            or any(item.intent is PartitionIntent.ERASE for item in receipt.partitions)
            or tuple(item.order for item in receipt.operations)
            != tuple(range(1, len(receipt.operations) + 1))
            or expected != _digest(payload)
        ):
            raise ProjectError("Digital Twin receipt failed integrity validation")

    def _model_partitions(
        self,
        project_id: str,
        contract: DeviceBuildContract | None,
        findings: list[SimulationFinding],
    ) -> tuple[tuple[DigitalTwinPartition, ...], tuple[SimulatedOperation, ...]]:
        if contract is None:
            return (), ()
        writes = contract.partition_write_contract
        if writes is None:
            findings.append(
                self._finding(
                    "write-contract",
                    SimulationSeverity.BLOCKED,
                    "No reviewed partition-write contract",
                    "The build layout is known, but no partition-to-artifact write sequence is authorized.",
                    "Add a physically validated write, verification, transition and recovery contract to this exact Device Pack.",
                )
            )
        build_plan = DeviceBuildContractService(self.store, self.registry, self.tool_statuses).load(
            project_id
        )
        build_receipt = LocalDeviceBuildExecutor(
            self.store,
            self.registry,
            self.tool_statuses,
            SubprocessRunner(),
        ).load_receipt(project_id)
        self._script_findings(findings, build_plan)
        outputs = {item.name: item for item in build_receipt.outputs} if build_receipt else {}
        write_rules = {item.partition: item for item in writes.writes} if writes else {}
        partitions: list[DigitalTwinPartition] = []
        for rule in contract.partitions:
            write = write_rules.get(rule.name)
            artifact = write.artifact if write else ""
            output = outputs.get(artifact)
            status = SimulationSeverity.VERIFIED
            detail = "Preserved by the reviewed write contract."
            if write is not None and output is None:
                status = SimulationSeverity.BLOCKED
                detail = "Planned artifact is missing from the current verified local build."
            elif write is not None:
                detail = "Artifact is present in the current verified local build receipt."
            partitions.append(
                DigitalTwinPartition(
                    rule.name,
                    rule.group,
                    rule.filesystem,
                    rule.size_bytes,
                    output.size_bytes if output else rule.source_size_bytes,
                    write.target_slot if write else "unchanged",
                    PartitionIntent.WRITE if write else PartitionIntent.PRESERVE,
                    artifact,
                    write.transport.value if write else "none",
                    status,
                    detail,
                )
            )
        if writes:
            known_partitions = {rule.name for rule in contract.partitions} | {"super"}
            if "super" in {item.partition for item in writes.writes}:
                super_write = next(item for item in writes.writes if item.partition == "super")
                super_output = outputs.get(super_write.artifact)
                fits = bool(
                    super_output is not None
                    and super_output.size_bytes <= contract.super_size_bytes
                )
                partitions.insert(
                    0,
                    DigitalTwinPartition(
                        "super",
                        "physical container",
                        "dynamic partition container",
                        contract.super_size_bytes,
                        super_output.size_bytes if super_output else 0,
                        super_write.target_slot,
                        PartitionIntent.WRITE,
                        super_write.artifact,
                        super_write.transport.value,
                        SimulationSeverity.VERIFIED if fits else SimulationSeverity.BLOCKED,
                        "Sparse super artifact fits the exact physical container."
                        if fits
                        else "The super artifact is missing or exceeds the exact container.",
                    ),
                )
                if super_output is not None and super_output.size_bytes > contract.super_size_bytes:
                    findings.append(
                        self._finding(
                            "super-capacity",
                            SimulationSeverity.BLOCKED,
                            "Super image exceeds device capacity",
                            f"{super_output.size_bytes} bytes cannot fit the {contract.super_size_bytes}-byte container.",
                            "Rebuild against the exact Device Pack geometry.",
                        )
                    )
            unknown = tuple(
                item.partition for item in writes.writes if item.partition not in known_partitions
            )
            if unknown:
                findings.append(
                    self._finding(
                        "unknown-write-target",
                        SimulationSeverity.BLOCKED,
                        "Write contract targets unknown partitions",
                        ", ".join(unknown),
                        "Correct the Device Pack partition map and validate it physically.",
                    )
                )
            missing = tuple(item.artifact for item in writes.writes if item.artifact not in outputs)
            if missing:
                findings.append(
                    self._finding(
                        "missing-images",
                        SimulationSeverity.BLOCKED,
                        "Planned images are missing",
                        ", ".join(missing),
                        "Build and verify every exact artifact before rehearsing again.",
                    )
                )
            else:
                findings.append(
                    self._finding(
                        "write-artifacts",
                        SimulationSeverity.VERIFIED,
                        "Every planned image is present",
                        f"{len(writes.writes)} write artifact(s) are bound to the current local build receipt.",
                        "No action required.",
                    )
                )
        operations = self._operations(contract, writes, outputs, build_plan)
        return tuple(partitions), operations

    @staticmethod
    def _operations(contract, writes, outputs, build_plan) -> tuple[SimulatedOperation, ...]:
        results: list[SimulatedOperation] = [
            SimulatedOperation(
                1,
                "source:verify",
                "source",
                "Verify protected firmware SHA-256",
                "",
                "",
                "local",
                "",
                0,
                2,
                "REHEARSED • immutable source binding",
            ),
            SimulatedOperation(
                2,
                "source:parse",
                "extract",
                "Parse payload and inventory partition images",
                "",
                "",
                "local",
                "",
                sum(item.source_size_bytes for item in contract.partitions),
                max(4, len(contract.partitions) * 2),
                "REHEARSED • bounded source contract",
            ),
            SimulatedOperation(
                3,
                "partition:map",
                "map",
                "Map dynamic groups, slots and image capacities",
                "",
                "",
                "local",
                "",
                contract.super_size_bytes,
                max(3, len(contract.partitions)),
                "REHEARSED • exact Device Pack geometry",
            ),
        ]
        order = 4
        if build_plan is not None:
            for step in build_plan.steps:
                results.append(
                    SimulatedOperation(
                        order,
                        f"build:{step.step_id}",
                        "build",
                        step.label,
                        "",
                        "",
                        "local",
                        ", ".join(step.outputs),
                        0,
                        5,
                        "REHEARSED • local command shape and dependency order",
                    )
                )
                order += 1
        if writes is None:
            return tuple(results)
        transition = writes.transition_recovery_contract
        if transition is not None:
            for item in sorted(transition.transitions, key=lambda value: value.order):
                if item.after_write_order != 0:
                    continue
                results.append(
                    SimulatedOperation(
                        order,
                        f"transition:{item.order}",
                        "transition",
                        _transition_label(item.operation),
                        "",
                        item.target_slot,
                        "device-mode",
                        "",
                        0,
                        max(1, item.timeout_seconds // 3),
                        "REHEARSED • state transition contract present",
                    )
                )
                order += 1
        for index, item in enumerate(writes.writes, 1):
            output = outputs.get(item.artifact)
            size = output.size_bytes if output is not None else 0
            speed = (
                25 * 1024 * 1024
                if item.transport is DeviceWriteTransport.FASTBOOTD
                else 35 * 1024 * 1024
            )
            results.append(
                SimulatedOperation(
                    order,
                    f"write:{index}:{item.partition}",
                    "write",
                    f"Write {item.partition} from {item.artifact}",
                    item.partition,
                    item.target_slot,
                    item.transport.value,
                    item.artifact,
                    size,
                    max(2, size // speed + 2),
                    "REHEARSED" if output is not None else "BLOCKED • artifact unavailable",
                )
            )
            order += 1
            if transition is not None:
                for move in sorted(transition.transitions, key=lambda value: value.order):
                    if move.after_write_order != index:
                        continue
                    results.append(
                        SimulatedOperation(
                            order,
                            f"transition:{move.order}",
                            "transition",
                            _transition_label(move.operation),
                            "",
                            move.target_slot,
                            "device-mode",
                            "",
                            0,
                            max(1, move.timeout_seconds // 3),
                            "REHEARSED • state transition contract present",
                        )
                    )
                    order += 1
        verification = writes.post_write_verification_contract
        if verification is not None:
            for index, item in enumerate(verification.readbacks, 1):
                results.append(
                    SimulatedOperation(
                        order,
                        f"verify:{index}:{item.partition}",
                        "verify",
                        f"Read back and hash {item.partition}",
                        item.partition,
                        item.target_slot,
                        item.transport.value,
                        "",
                        item.expected_size_bytes,
                        max(
                            2,
                            item.expected_size_bytes // (30 * 1024 * 1024) + 2,
                        ),
                        "REHEARSED • expected size and SHA-256 are declared",
                    )
                )
                order += 1
        if transition is not None:
            for index, action in enumerate(transition.recovery.actions, 1):
                results.append(
                    SimulatedOperation(
                        order,
                        f"rollback:{index}:{action.operation.value}",
                        "rollback",
                        f"Recovery rehearsal: {action.operation.value.replace('_', ' ')}",
                        "",
                        action.target_slot,
                        transition.recovery.adapter_id,
                        "",
                        0,
                        max(1, action.timeout_seconds // 3),
                        "ROLLBACK REHEARSED • adapter-scoped action",
                    )
                )
                order += 1
        return tuple(results)

    def _script_findings(
        self,
        findings: list[SimulationFinding],
        build_plan,
    ) -> None:
        if build_plan is None:
            findings.append(
                self._finding(
                    "command-order",
                    SimulationSeverity.ATTENTION,
                    "Deterministic local command order is not frozen",
                    "Source and partition evidence can be modelled, but no current build plan is available.",
                    "Prepare the exact local build plan, then rehearse again.",
                )
            )
            return
        danger_tokens = (
            "erase",
            "format",
            "wipe",
            "delete-logical-partition",
            "flashing lock",
            "oem lock",
        )
        dangerous: list[str] = []
        for step in build_plan.steps:
            command = " ".join((step.tool, *step.arguments)).casefold()
            if any(token in command for token in danger_tokens):
                dangerous.append(step.step_id)
        findings.append(
            self._finding(
                "command-order",
                SimulationSeverity.BLOCKED if dangerous else SimulationSeverity.VERIFIED,
                "Dangerous build/install command detected"
                if dangerous
                else "Deterministic command order scanned",
                ", ".join(dangerous)
                if dangerous
                else f"{len(build_plan.steps)} local step(s) contain no erase, wipe, format, partition-delete or relock action.",
                "Remove the dangerous command and create a new reviewed plan."
                if dangerous
                else "No action required.",
            )
        )

    def _identity_findings(
        self,
        findings: list[SimulationFinding],
        dna: DeviceDnaProfile | None,
        pack: DevicePack | None,
        device: AndroidDevice | None,
    ) -> None:
        if dna is None:
            return
        source_target = self._fact(dna, "firmware.ota_post_device")
        live_target = (
            device.codename if device is not None else self._fact(dna, "identity.codename")
        )
        targets = {part.casefold().strip() for part in source_target.split("|") if part.strip()}
        if source_target and live_target and live_target.casefold() not in targets:
            findings.append(
                self._finding(
                    "codename",
                    SimulationSeverity.BLOCKED,
                    "Firmware codename mismatch",
                    f"Device reports {live_target}; firmware targets {source_target}.",
                    "Choose firmware for the exact device codename.",
                )
            )
            return
        if device is not None and pack is not None:
            product = device.product.casefold().strip()
            matched = bool(
                product
                and any(
                    fnmatch.fnmatchcase(product, pattern.casefold())
                    for pattern in pack.product_patterns
                )
            )
            if pack.product_patterns and not matched:
                findings.append(
                    self._finding(
                        "device-match",
                        SimulationSeverity.BLOCKED,
                        "Live device is outside the Device Pack",
                        f"Product {product or 'unreported'} does not match the reviewed pack.",
                        "Select the exact Device Pack and scan Device DNA again.",
                    )
                )
                return
        findings.append(
            self._finding(
                "device-match",
                SimulationSeverity.VERIFIED,
                "Device identity model agrees",
                f"Digital Twin target: {live_target or 'source-bound identity'}.",
                "Re-identify the physical phone immediately before final consent.",
            )
        )

    def _upgrade_findings(
        self,
        findings: list[SimulationFinding],
        dna: DeviceDnaProfile | None,
    ) -> None:
        relationship = self._fact(dna, "firmware.upgrade_relationship")
        upper = relationship.upper()
        if "INCOMPATIBLE" in upper:
            severity = SimulationSeverity.BLOCKED
            resolution = "Use firmware for the exact device."
        elif "DOWNGRADE" in upper:
            severity = SimulationSeverity.BLOCKED
            resolution = "Use an upgrade, or require a separately reviewed anti-rollback contract."
        elif "UNCONFIRMED" in upper or not upper:
            severity = SimulationSeverity.ATTENTION
            resolution = "Refresh live Device DNA and exact OTA metadata."
        elif "SAME " in upper:
            severity = SimulationSeverity.ATTENTION
            resolution = "Confirm that reinstalling the same build is intentional."
        else:
            severity = SimulationSeverity.VERIFIED
            resolution = "No action required."
        findings.append(
            self._finding(
                "firmware-relationship",
                severity,
                relationship or "Firmware relationship is unconfirmed",
                "The relationship is classified from source metadata and Device DNA; it grants no write authority.",
                resolution,
            )
        )

    def _geometry_findings(
        self,
        findings: list[SimulationFinding],
        contract: DeviceBuildContract | None,
    ) -> None:
        if contract is None:
            return
        group_limits = {item.name: item.maximum_size_bytes for item in contract.groups}
        group_used: dict[str, int] = {}
        invalid: list[str] = []
        for partition in contract.partitions:
            group_used[partition.group] = group_used.get(partition.group, 0) + partition.size_bytes
            if partition.source_size_bytes > partition.size_bytes:
                invalid.append(
                    f"{partition.name} image exceeds its {partition.size_bytes}-byte capacity"
                )
        for group, used in group_used.items():
            limit = group_limits.get(group, 0)
            if limit <= 0 or used > limit:
                invalid.append(f"{group} allocates {used} bytes against limit {limit}")
        if sum(group_limits.values()) < contract.super_size_bytes:
            # A/B group maxima can intentionally overlap the same physical super space.
            pass
        findings.append(
            self._finding(
                "partition-geometry",
                SimulationSeverity.BLOCKED if invalid else SimulationSeverity.VERIFIED,
                "Partition geometry mismatch" if invalid else "Partition geometry fits",
                "; ".join(invalid)
                if invalid
                else f"{len(contract.partitions)} logical partitions fit their declared groups and image capacities.",
                "Correct the exact Device Pack sizes." if invalid else "No action required.",
            )
        )

    def _avb_and_slot_findings(
        self,
        findings: list[SimulationFinding],
        contract: DeviceBuildContract | None,
        dna: DeviceDnaProfile | None,
        device: AndroidDevice | None,
    ) -> None:
        if contract is None:
            return
        policy = contract.avb_execution_policy
        writes = contract.partition_write_contract
        if policy is None:
            findings.append(
                self._finding(
                    "avb",
                    SimulationSeverity.BLOCKED,
                    "AVB policy is missing",
                    "The boot-chain and rollback-index handling cannot be inferred.",
                    "Add reviewed AVB evidence for this exact source.",
                )
            )
        elif policy.authority.value != "flash_validated":
            findings.append(
                self._finding(
                    "avb",
                    SimulationSeverity.BLOCKED,
                    "AVB evidence is reference-only",
                    f"Mode {policy.mode.value}; chain {policy.chain_partition}; authority {policy.authority.value}.",
                    "Physically validate and attest the exact AVB policy before a real operation.",
                )
            )
        else:
            findings.append(
                self._finding(
                    "avb",
                    SimulationSeverity.VERIFIED,
                    "AVB chain contract is flash-validated",
                    f"Mode {policy.mode.value}; chain {policy.chain_partition}; rollback location {policy.candidate_rollback_index_location}.",
                    "Recheck live boot state immediately before final consent.",
                )
            )
        locked = device.bootloader_locked if device is not None else None
        if writes is not None and writes.require_unlocked_bootloader:
            if locked is True:
                findings.append(
                    self._finding(
                        "bootloader",
                        SimulationSeverity.BLOCKED,
                        "Bootloader is locked",
                        "The reviewed write contract requires an unlocked bootloader.",
                        "Use the manufacturer's supported unlock process outside ROMVERSE, then rescan.",
                    )
                )
            elif locked is None:
                findings.append(
                    self._finding(
                        "bootloader",
                        SimulationSeverity.ATTENTION,
                        "Live bootloader state is unconfirmed",
                        self._fact(dna, "bootloader.state") or "No current physical reading.",
                        "Reconnect in the required mode and re-identify before final consent.",
                    )
                )
        active_slot = (
            device.slot_suffix.removeprefix("_")
            if device is not None
            else self._fact(dna, "boot.active_slot")
        )
        target_slots = (
            {
                item.target_slot
                for item in writes.writes
                if writes is not None and item.target_slot not in {"", "none"}
            }
            if writes is not None
            else set()
        )
        if target_slots and not active_slot:
            findings.append(
                self._finding(
                    "slot",
                    SimulationSeverity.ATTENTION,
                    "Active slot is not available offline",
                    f"Contract targets {', '.join(sorted(target_slots))}.",
                    "Capture the active slot immediately before the operation.",
                )
            )
        dangerous = []
        if writes and writes.transition_recovery_contract:
            recovery = writes.transition_recovery_contract.recovery
            dangerous.extend(
                action.adapter_action_id for action in recovery.actions if action.may_wipe_user_data
            )
            if recovery.automatic_wipe_allowed or recovery.bootloader_relock_allowed:
                dangerous.append("automatic wipe or bootloader relock authority")
        findings.append(
            self._finding(
                "dangerous-actions",
                SimulationSeverity.BLOCKED if dangerous else SimulationSeverity.VERIFIED,
                "Dangerous erase/relock action detected"
                if dangerous
                else "No automatic erase or relock action",
                ", ".join(dangerous)
                if dangerous
                else "The simulated sequence contains no erase, format, wipe, or bootloader-relock command.",
                "Remove dangerous automatic actions; require a separate explicit human decision."
                if dangerous
                else "No action required.",
            )
        )

    def _rollback(
        self,
        project_id: str,
        contract: DeviceBuildContract | None,
        device: AndroidDevice | None,
    ) -> RollbackRehearsal:
        evidence = RecoveryEvidenceService(self.store).assess(project_id, device)
        transition = (
            contract.partition_write_contract.transition_recovery_contract
            if contract is not None and contract.partition_write_contract is not None
            else None
        )
        missing: list[str] = []
        checks: list[str] = []
        if evidence.external_backup_ready:
            checks.append("External user-data backup evidence is current")
        else:
            missing.append("External user-data backup is missing or stale")
        if evidence.stock_recovery_ready:
            checks.append("Exact stock recovery package is current")
        else:
            missing.append("Exact stock recovery package is missing or stale")
        if transition is not None:
            checks.append(f"{len(transition.transitions)} mode/slot transition(s) are ordered")
            checks.append(
                f"{len(transition.recovery.actions)} recovery action(s) use adapter "
                f"{transition.recovery.adapter_id}"
            )
            if transition.recovery.bootloader_relock_allowed:
                missing.append("Recovery contract improperly permits bootloader relocking")
            if transition.recovery.automatic_wipe_allowed:
                missing.append("Recovery contract improperly permits an automatic wipe")
        else:
            missing.append("Signed transition and recovery orchestration is absent")
        return RollbackRehearsal(
            ready=not missing,
            strategy=(
                transition.recovery.strategy.value if transition is not None else "unconfirmed"
            ),
            checks=tuple(checks),
            missing=tuple(missing),
        )

    @classmethod
    def _required_workspace(cls, contract: DeviceBuildContract | None) -> int:
        if contract is None:
            return 0
        return (
            contract.super_size_bytes
            + sum(item.source_size_bytes for item in contract.partitions)
            + sum(item.size_bytes for item in contract.partitions if item.mode == "rebuild")
            + cls.BUILD_RESERVE_BYTES
        )

    @staticmethod
    def _fact(dna: DeviceDnaProfile | None, fact_id: str) -> str:
        fact = dna.fact(fact_id) if dna is not None else None
        return fact.value.strip() if fact is not None else ""

    @staticmethod
    def _finding(
        finding_id: str,
        severity: SimulationSeverity,
        title: str,
        detail: str,
        resolution: str,
        evidence_refs: tuple[str, ...] = (),
    ) -> SimulationFinding:
        return SimulationFinding(
            finding_id,
            severity,
            title,
            detail,
            resolution,
            evidence_refs,
        )

    @staticmethod
    def _confidence_label(confidence: int, blockers: int) -> str:
        if blockers:
            return "BLOCKED"
        if confidence >= 85:
            return "HIGH"
        if confidence >= 65:
            return "MEDIUM"
        return "LOW"

    def _save(self, receipt: RomSimulationReceipt) -> None:
        self.validate(receipt)
        atomic_write_json(
            self.store.projects_root / receipt.project_id / self.RECEIPT_NAME,
            {"format": self.FORMAT, **asdict(receipt)},
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_BYTES,
        )


def _transition_label(operation: DeviceTransitionOperation) -> str:
    return {
        DeviceTransitionOperation.REBOOT_FASTBOOTD: "Transition to userspace Fastboot",
        DeviceTransitionOperation.REBOOT_BOOTLOADER: "Transition to bootloader Fastboot",
        DeviceTransitionOperation.SET_ACTIVE_SLOT: "Activate the reviewed target slot",
        DeviceTransitionOperation.REBOOT_SYSTEM: "Reboot to Android for post-boot checks",
    }[operation]


def _clean(value: str, maximum: int) -> bool:
    return bool(
        isinstance(value, str)
        and 0 < len(value.strip()) <= maximum
        and "\x00" not in value
        and "\r" not in value
        and "\n" not in value
    )


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            default=_json_default,
        ).encode("utf-8")
    ).hexdigest()


def _json_default(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    raise TypeError(f"Unsupported simulation receipt value: {type(value).__name__}")
