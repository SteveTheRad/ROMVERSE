from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass, fields, is_dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from romverse.device.dna import DeviceDnaProfile, DeviceDnaStore, EvidenceConfidence
from romverse.infrastructure.local_store import atomic_write_json, read_json_object
from romverse.nexus.compatibility import (
    CompatibilityDecision,
    CompatibilityMatrix,
    CompatibilityMatrixStore,
    CompatibilityStatus,
    EvidenceFreshness,
)
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore


class NexusObjective(StrEnum):
    BUILD_ROM = "build-rom"
    ROOT_ROM = "root-rom"
    FLASH_DEVICE = "flash-device"


class NexusPlanStatus(StrEnum):
    NEEDS_EVIDENCE = "needs-evidence"
    READY_FOR_GUARDIAN = "ready-for-guardian"


class RouteStageState(StrEnum):
    COMPLETE = "complete"
    CURRENT = "current"
    UPCOMING = "upcoming"
    BLOCKED = "blocked"
    ADAPTED = "adapted"


class ImpactLevel(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FlashMode(StrEnum):
    UNSELECTED = "unselected"
    DIRTY_FLASH = "dirty-flash"
    WIPE_DATA = "wipe-data"


@dataclass(frozen=True, slots=True)
class PathfinderStage:
    stage_id: str
    label: str
    state: RouteStageState
    explanation: str
    recommendation: str
    branch: str = ""


@dataclass(frozen=True, slots=True)
class ForesightPrediction:
    prediction_id: str
    area: str
    impact: ImpactLevel
    prediction: str
    dependencies: tuple[str, ...]
    verification: str
    confidence: EvidenceConfidence


@dataclass(frozen=True, slots=True)
class InsightDecision:
    decision_id: str
    question: str
    answer: str
    why: str
    source_ids: tuple[str, ...]
    confidence: EvidenceConfidence


@dataclass(frozen=True, slots=True)
class NexusPlan:
    schema_version: int
    plan_id: str
    mission_id: str
    project_id: str
    objective: NexusObjective
    created_at: str
    device_dna_digest: str
    compatibility_matrix_digest: str
    status: NexusPlanStatus
    understanding: tuple[str, ...]
    research_requirements: tuple[str, ...]
    route: tuple[PathfinderStage, ...]
    predictions: tuple[ForesightPrediction, ...]
    decisions: tuple[InsightDecision, ...]
    guardian_requirements: tuple[str, ...]
    flash_mode: FlashMode
    adaptation_of: str
    adaptation_reason: str
    execution_authorized: bool
    bootloader_relock_permitted: bool
    plan_digest: str

    @property
    def ready_for_guardian_review(self) -> bool:
        return self.status is NexusPlanStatus.READY_FOR_GUARDIAN


class NexusPlanStore:
    NAME = "nexus-plan.romverse"
    FORMAT = "romverse.nexus-plan"
    MAX_BYTES = 2 * 1024 * 1024

    def __init__(self, store: RomProjectStore) -> None:
        self.store = store

    def save(self, plan: NexusPlan) -> NexusPlan:
        dna, matrix = self._validate_sources(plan)
        if plan.execution_authorized or plan.bootloader_relock_permitted:
            raise ProjectError("A Nexus Plan cannot grant execution or bootloader relock authority")
        plan = _seal_plan(plan)
        if not _valid_plan(plan, dna, matrix):
            raise ProjectError("Nexus Plan metadata is invalid")
        existing = self.load(plan.project_id)
        if existing is not None and _semantic(existing) == _semantic(plan):
            return existing
        path = self.store.projects_root / plan.project_id / self.NAME
        atomic_write_json(
            path,
            {"format": self.FORMAT, **asdict(plan)},
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_BYTES,
        )
        return plan

    def load(self, project_id: str) -> NexusPlan | None:
        try:
            self.store.get(project_id)
        except ProjectError:
            return None
        path = self.store.projects_root / project_id / self.NAME
        try:
            payload = read_json_object(
                path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            if (
                set(payload) != {"format", *(field.name for field in fields(NexusPlan))}
                or payload.pop("format") != self.FORMAT
                or not _valid_raw_plan(payload)
            ):
                return None
            plan = _plan_from_mapping(payload)
            dna, matrix = self._validate_sources(plan)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError, ProjectError):
            return None
        if (
            not _valid_plan(plan, dna, matrix)
            or plan.project_id != project_id
            or plan.execution_authorized
            or plan.bootloader_relock_permitted
        ):
            return None
        return plan

    def _validate_sources(self, plan: NexusPlan) -> tuple[DeviceDnaProfile, CompatibilityMatrix]:
        dna = DeviceDnaStore(self.store).load(plan.project_id)
        matrix = CompatibilityMatrixStore(self.store).load(plan.project_id)
        if dna is None or dna.profile_digest != plan.device_dna_digest:
            raise ProjectError("Nexus Plan is not bound to current Device DNA")
        if matrix is None or matrix.matrix_digest != plan.compatibility_matrix_digest:
            raise ProjectError("Nexus Plan is not bound to the current Compatibility Matrix")
        return dna, matrix


class NexusPlanner:
    """Coordinate deterministic evidence into a plan without executing it."""

    def __init__(self, store: RomProjectStore) -> None:
        self.store = store
        self.plans = NexusPlanStore(store)

    def plan(
        self,
        profile: DeviceDnaProfile,
        matrix: CompatibilityMatrix,
        objective: NexusObjective,
        *,
        flash_mode: FlashMode = FlashMode.UNSELECTED,
        adaptation_of: str = "",
        adaptation_reason: str = "",
    ) -> NexusPlan:
        self._validate(profile, matrix)
        required = _required_capabilities(objective)
        research = _research(matrix, required, objective, flash_mode)
        status = NexusPlanStatus.NEEDS_EVIDENCE if research else NexusPlanStatus.READY_FOR_GUARDIAN
        decisions = _insight(matrix, required, objective, flash_mode)
        payload: dict[str, object] = {
            "schema_version": 2,
            "plan_id": uuid4().hex,
            "mission_id": uuid4().hex,
            "project_id": profile.project_id,
            "objective": objective,
            "created_at": datetime.now(UTC).isoformat(),
            "device_dna_digest": profile.profile_digest,
            "compatibility_matrix_digest": matrix.matrix_digest,
            "status": status,
            "understanding": _understanding(profile, objective),
            "research_requirements": research,
            "route": _route(objective, status, bool(adaptation_of)),
            "predictions": _foresight(objective, flash_mode),
            "decisions": decisions,
            "guardian_requirements": _guardian_requirements(objective, flash_mode),
            "flash_mode": flash_mode,
            "adaptation_of": adaptation_of,
            "adaptation_reason": adaptation_reason,
            "execution_authorized": False,
            "bootloader_relock_permitted": False,
        }
        plan = NexusPlan(**payload, plan_digest=_digest(payload))  # type: ignore[arg-type]
        return self.plans.save(plan)

    def adapt(
        self,
        previous: NexusPlan,
        profile: DeviceDnaProfile,
        matrix: CompatibilityMatrix,
        *,
        reason: str,
        flash_mode: FlashMode | None = None,
    ) -> NexusPlan:
        clean_reason = reason.replace("\x00", "").strip()
        if not clean_reason or len(clean_reason) > 500:
            raise ProjectError("Nexus Adaptation needs a concise evidence-backed reason")
        if self.plans.load(previous.project_id) != previous:
            raise ProjectError("Nexus Adaptation requires the current trusted plan")
        return self.plan(
            profile,
            matrix,
            previous.objective,
            flash_mode=flash_mode or previous.flash_mode,
            adaptation_of=previous.plan_id,
            adaptation_reason=clean_reason,
        )

    def _validate(self, profile: DeviceDnaProfile, matrix: CompatibilityMatrix) -> None:
        persisted_dna = DeviceDnaStore(self.store).load(profile.project_id)
        persisted_matrix = CompatibilityMatrixStore(self.store).load(profile.project_id)
        if persisted_dna is None or persisted_dna.profile_digest != profile.profile_digest:
            raise ProjectError("Nexus requires current trusted Device DNA")
        if (
            persisted_matrix is None
            or persisted_matrix.matrix_digest != matrix.matrix_digest
            or matrix.project_id != profile.project_id
            or matrix.device_dna_digest != profile.profile_digest
        ):
            raise ProjectError("Nexus requires the current source-bound Compatibility Matrix")


class InsightExporter:
    """Export a privacy-scrubbed decision timeline without raw device identifiers."""

    FORMAT = "romverse.insight-report"

    @classmethod
    def export(cls, plan: NexusPlan, destination: Path) -> Path:
        payload = {
            "format": cls.FORMAT,
            "schema_version": 1,
            "privacy": "redacted",
            "plan_id": plan.plan_id,
            "mission_id": plan.mission_id,
            "project_id": plan.project_id,
            "objective": plan.objective,
            "status": plan.status,
            "route": [asdict(item) for item in plan.route],
            "predictions": [asdict(item) for item in plan.predictions],
            "decision_timeline": [asdict(item) for item in plan.decisions],
            "guardian_requirements": plan.guardian_requirements,
            "execution_authorized": False,
            "bootloader_relock_permitted": False,
        }
        destination = destination.expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return destination


def _required_capabilities(objective: NexusObjective) -> tuple[str, ...]:
    common = ("device_identity", "firmware_detection", "partition_mapping", "rom_build")
    if objective is NexusObjective.BUILD_ROM:
        return common
    if objective is NexusObjective.ROOT_ROM:
        return (*common, "root_state")
    return (*common, "guardian_flash")


def _research(
    matrix: CompatibilityMatrix,
    required: tuple[str, ...],
    objective: NexusObjective,
    flash_mode: FlashMode,
) -> tuple[str, ...]:
    results: list[str] = []
    strong_allowed = {"device_identity", "firmware_detection"}
    for capability_id in required:
        decision = matrix.decision(capability_id)
        if decision is None:
            results.append(f"Confirm {capability_id.replace('_', ' ')}; no matrix row exists.")
            continue
        if decision.freshness is EvidenceFreshness.STALE:
            results.append(f"Refresh stale evidence for {decision.label}.")
        if decision.status is CompatibilityStatus.KNOWN_INCOMPATIBLE:
            results.append(f"Stop: {decision.label} is known incompatible for this evidence scope.")
        elif decision.status is CompatibilityStatus.UNKNOWN:
            results.append(f"Confirm {decision.label}; ROMVERSE will not infer unknown support.")
        elif decision.status is CompatibilityStatus.LIMITED_EVIDENCE:
            results.append(f"Obtain exact compatibility evidence for {decision.label}.")
        elif (
            decision.status is CompatibilityStatus.STRONG_MATCH
            and capability_id not in strong_allowed
        ):
            results.append(
                f"Prove exact compatibility for {decision.label}; a strong match is not proof."
            )
    if objective is NexusObjective.FLASH_DEVICE and flash_mode is FlashMode.UNSELECTED:
        results.append(
            "Ask the user to choose Dirty flash or Flash and wipe data; explain data impact."
        )
    return tuple(dict.fromkeys(results))


def _understanding(profile: DeviceDnaProfile, objective: NexusObjective) -> tuple[str, ...]:
    def value(fact_id: str, label: str) -> str:
        fact = profile.fact(fact_id)
        return f"{label}: {fact.value if fact is not None else 'Unconfirmed'}"

    return (
        f"Objective: {objective.value.replace('-', ' ')}",
        value("identity.marketing_name", "Device"),
        value("identity.codename", "Codename"),
        value("software.build", "Firmware build"),
        value("firmware.package_format", "Package"),
        "Bootloader relocking: never permitted",
    )


def _route(
    objective: NexusObjective,
    status: NexusPlanStatus,
    adaptation: bool,
) -> tuple[PathfinderStage, ...]:
    evidence_ready = status is NexusPlanStatus.READY_FOR_GUARDIAN
    return (
        PathfinderStage(
            "understand",
            "Understand",
            RouteStageState.ADAPTED if adaptation else RouteStageState.COMPLETE,
            "Device DNA establishes the current device and firmware evidence.",
            "Review any unconfirmed identity before continuing.",
        ),
        PathfinderStage(
            "research",
            "Research",
            RouteStageState.COMPLETE if evidence_ready else RouteStageState.CURRENT,
            "Compatibility Matrix checks evidence strength, scope, and freshness.",
            "Resolve every listed research requirement without guessing.",
        ),
        PathfinderStage(
            "plan",
            "Nexus Plan",
            RouteStageState.COMPLETE,
            f"Pathfinder generated the deterministic {objective.value.replace('-', ' ')} route.",
            "Review Foresight impacts and Insight explanations.",
        ),
        PathfinderStage(
            "guardian-review",
            "Guardian Review",
            RouteStageState.CURRENT if evidence_ready else RouteStageState.BLOCKED,
            "Guardian independently reviews safety, approvals, and exact current evidence.",
            "Never bypass a blocked Guardian requirement.",
            "Physical device operations remain locked until explicit review.",
        ),
        PathfinderStage(
            "execute",
            "Execute",
            RouteStageState.UPCOMING if evidence_ready else RouteStageState.BLOCKED,
            "Only a separate typed service may execute after Guardian approval.",
            "Nexus itself has no execution authority.",
        ),
        PathfinderStage(
            "verify",
            "Nexus Verification",
            RouteStageState.UPCOMING if evidence_ready else RouteStageState.BLOCKED,
            "Fresh post-operation evidence must prove the actual outcome.",
            "Never infer success from elapsed time, a progress bar, or a planned route.",
        ),
    )


def _foresight(objective: NexusObjective, flash_mode: FlashMode) -> tuple[ForesightPrediction, ...]:
    common = ForesightPrediction(
        "protected-source",
        "Protected firmware",
        ImpactLevel.NONE,
        "The immutable protected source should remain unchanged.",
        ("source-bound project manifest",),
        "Re-hash the protected source and compare it with the import manifest.",
        EvidenceConfidence.HIGH,
    )
    if objective is NexusObjective.BUILD_ROM:
        return (
            common,
            ForesightPrediction(
                "working-tree",
                "Isolated ROM workspace",
                ImpactLevel.HIGH,
                "Recipes and rebuild steps may change the isolated working tree and candidate images.",
                ("Time Machine snapshot", "verified Recipe receipt", "exact build contract"),
                "Verify the final tree, candidate hashes, AVB topology, and build receipts.",
                EvidenceConfidence.HIGH,
            ),
            ForesightPrediction(
                "phone-during-build",
                "Connected phone",
                ImpactLevel.NONE,
                "Local ROM build preparation should not modify the phone.",
                ("Guardian keeps device-changing operations unavailable",),
                "Confirm no device-changing receipt exists for the build mission.",
                EvidenceConfidence.VERIFIED,
            ),
        )
    if objective is NexusObjective.ROOT_ROM:
        return (
            common,
            ForesightPrediction(
                "root-candidate",
                "Boot or init_boot candidate",
                ImpactLevel.HIGH,
                "Ascension Protocol may create a source-bound Magisk or KernelSU candidate for the exact device.",
                (
                    "exact Device DNA",
                    "supported root method evidence",
                    "official verified root artifact",
                    "rollback capsule",
                ),
                "Verify the input and patched output hashes, device binding, AVB role, and rollback evidence.",
                EvidenceConfidence.MEDIUM,
            ),
            ForesightPrediction(
                "phone-during-root-prep",
                "Connected phone",
                ImpactLevel.NONE,
                "Root preparation should not install, flash, unlock, wipe, or relock the phone.",
                ("separate Guardian handoff",),
                "Confirm Ascension preparation receipts report no device command execution.",
                EvidenceConfidence.VERIFIED,
            ),
        )
    data_prediction = (
        "Dirty flash is intended to preserve user data, but backup and exact compatibility are still required."
        if flash_mode is FlashMode.DIRTY_FLASH
        else "Flash and wipe data will erase user data and requires explicit confirmation."
        if flash_mode is FlashMode.WIPE_DATA
        else "User-data impact is undecided until the user selects a flash mode."
    )
    return (
        common,
        ForesightPrediction(
            "device-write",
            "Physical device partitions",
            ImpactLevel.CRITICAL,
            "Flashing can make the device unbootable if any target, slot, image, or AVB assumption is wrong.",
            (
                "exact connected device",
                "verified build and signing receipts",
                "backup and recovery route",
                "battery and transport stability",
                "explicit user approval",
            ),
            "Verify every written partition, active slot, first boot, and recovery path with fresh evidence.",
            EvidenceConfidence.HIGH,
        ),
        ForesightPrediction(
            "userdata",
            "User data",
            ImpactLevel.CRITICAL if flash_mode is FlashMode.WIPE_DATA else ImpactLevel.HIGH,
            data_prediction,
            ("local backup option", "explicit flash-mode confirmation"),
            "Confirm backup receipts before flashing and verify expected data state after boot.",
            EvidenceConfidence.MEDIUM,
        ),
        ForesightPrediction(
            "bootloader-relock",
            "Bootloader state",
            ImpactLevel.CRITICAL,
            "Bootloader relocking is never part of a ROMVERSE route.",
            ("Guardian never-relock invariant",),
            "Verify no plan, command, or receipt contains a relock operation.",
            EvidenceConfidence.VERIFIED,
        ),
    )


def _insight(
    matrix: CompatibilityMatrix,
    required: tuple[str, ...],
    objective: NexusObjective,
    flash_mode: FlashMode,
) -> tuple[InsightDecision, ...]:
    decisions = []
    for capability_id in required:
        item = matrix.decision(capability_id)
        if item is None:
            decisions.append(
                InsightDecision(
                    f"missing-{capability_id}",
                    f"Can ROMVERSE trust {capability_id.replace('_', ' ')}?",
                    "Unknown",
                    "No Compatibility Matrix decision exists.",
                    (),
                    EvidenceConfidence.UNCONFIRMED,
                )
            )
            continue
        decisions.append(_insight_decision(item))
    if objective is NexusObjective.FLASH_DEVICE:
        decisions.append(
            InsightDecision(
                "flash-mode",
                "How will user data be handled?",
                flash_mode.value.replace("-", " ").title(),
                "The user must knowingly choose data preservation intent before Guardian review.",
                ("user.flash-mode-choice",) if flash_mode is not FlashMode.UNSELECTED else (),
                EvidenceConfidence.VERIFIED
                if flash_mode is not FlashMode.UNSELECTED
                else EvidenceConfidence.UNCONFIRMED,
            )
        )
    return tuple(decisions)


def _insight_decision(item: CompatibilityDecision) -> InsightDecision:
    source_ids = tuple(source.evidence_id for source in item.evidence)
    return InsightDecision(
        item.capability_id,
        f"What supports {item.label}?",
        item.status.value,
        (
            f"{item.summary} Scope: {item.scope}. Freshness: {item.freshness.value}. "
            f"Proven compatible: {'yes' if item.proven_compatible else 'no'}."
        ),
        source_ids,
        item.confidence,
    )


def _guardian_requirements(objective: NexusObjective, flash_mode: FlashMode) -> tuple[str, ...]:
    common = (
        "Revalidate Device DNA and Compatibility Matrix immediately before any effect.",
        "Bind approvals to exact hashes, target, operation, and current evidence.",
        "Preserve the protected source and a verified rollback path.",
        "Never relock the bootloader.",
    )
    if objective is NexusObjective.BUILD_ROM:
        return (*common, "Keep all work inside the isolated ROM workspace.")
    if objective is NexusObjective.ROOT_ROM:
        return (
            *common,
            "Use Ascension Protocol and only an exact-device Magisk or KernelSU route.",
            "Do not unlock, root, install, or flash during preparation.",
        )
    return (
        *common,
        "Require a verified local backup or an explicit informed backup decision.",
        f"Require explicit confirmation of flash mode: {flash_mode.value}.",
        "Confirm battery, cable/transport, slot, recovery, AVB, and first-boot plan.",
    )


def _seal_plan(plan: NexusPlan) -> NexusPlan:
    unsigned = replace(plan, schema_version=2, plan_digest="")
    payload = asdict(unsigned)
    payload.pop("plan_digest")
    return replace(unsigned, plan_digest=_digest(payload))


def _valid_plan(
    plan: NexusPlan,
    profile: DeviceDnaProfile,
    matrix: CompatibilityMatrix,
) -> bool:
    if not isinstance(plan, NexusPlan):
        return False
    required = _required_capabilities(plan.objective)
    research = _research(matrix, required, plan.objective, plan.flash_mode)
    expected_status = (
        NexusPlanStatus.NEEDS_EVIDENCE if research else NexusPlanStatus.READY_FOR_GUARDIAN
    )
    unsigned = asdict(plan)
    digest = unsigned.pop("plan_digest")
    adaptation_valid = (not plan.adaptation_of and not plan.adaptation_reason) or (
        _hex(plan.adaptation_of, 32) and _valid_text(plan.adaptation_reason, 500)
    )
    return bool(
        type(plan.schema_version) is int
        and plan.schema_version in {1, 2}
        and _hex(plan.plan_id, 32)
        and _hex(plan.mission_id, 32)
        and re.fullmatch(r"[a-z0-9-]{1,64}", plan.project_id)
        and plan.project_id == profile.project_id == matrix.project_id
        and isinstance(plan.objective, NexusObjective)
        and _aware_timestamp(plan.created_at)
        and _hex(plan.device_dna_digest, 64)
        and plan.device_dna_digest == profile.profile_digest
        and _hex(plan.compatibility_matrix_digest, 64)
        and plan.compatibility_matrix_digest == matrix.matrix_digest
        and plan.status is expected_status
        and isinstance(plan.understanding, tuple)
        and plan.understanding == _understanding(profile, plan.objective)
        and isinstance(plan.research_requirements, tuple)
        and plan.research_requirements == research
        and isinstance(plan.route, tuple)
        and plan.route == _route(plan.objective, expected_status, bool(plan.adaptation_of))
        and isinstance(plan.predictions, tuple)
        and plan.predictions == _foresight(plan.objective, plan.flash_mode)
        and isinstance(plan.decisions, tuple)
        and plan.decisions == _insight(matrix, required, plan.objective, plan.flash_mode)
        and isinstance(plan.guardian_requirements, tuple)
        and plan.guardian_requirements == _guardian_requirements(plan.objective, plan.flash_mode)
        and isinstance(plan.flash_mode, FlashMode)
        and (
            plan.objective is NexusObjective.FLASH_DEVICE or plan.flash_mode is FlashMode.UNSELECTED
        )
        and adaptation_valid
        and plan.execution_authorized is False
        and plan.bootloader_relock_permitted is False
        and _hex(digest, 64)
        and digest == _digest(unsigned)
    )


def _hex(value: object, length: int) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(rf"[0-9a-f]{{{length}}}", value))


def _aware_timestamp(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 80:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed <= datetime.now(UTC) + timedelta(minutes=5)


def _valid_text(value: object, maximum: int) -> bool:
    return bool(
        isinstance(value, str)
        and 1 <= len(value) <= maximum
        and all(character.isprintable() or character == "\t" for character in value)
    )


def _semantic(plan: NexusPlan) -> dict[str, object]:
    payload = asdict(plan)
    for key in ("plan_id", "mission_id", "created_at", "plan_digest"):
        payload.pop(key, None)
    return payload


def _digest(payload: object) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _json_default(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    raise TypeError(f"Unsupported Nexus Plan value: {type(value).__name__}")


def _valid_raw_plan(data: dict[str, object]) -> bool:
    route = data.get("route")
    predictions = data.get("predictions")
    decisions = data.get("decisions")
    return bool(
        type(data.get("schema_version")) is int
        and data.get("schema_version") in {1, 2}
        and all(
            isinstance(data.get(key), str)
            for key in (
                "plan_id",
                "mission_id",
                "project_id",
                "objective",
                "created_at",
                "device_dna_digest",
                "compatibility_matrix_digest",
                "status",
                "flash_mode",
                "adaptation_of",
                "adaptation_reason",
                "plan_digest",
            )
        )
        and _raw_string_list(data.get("understanding"), 64)
        and _raw_string_list(data.get("research_requirements"), 64)
        and _raw_string_list(data.get("guardian_requirements"), 64)
        and isinstance(route, list)
        and 1 <= len(route) <= 16
        and all(_valid_raw_route(item) for item in route)
        and isinstance(predictions, list)
        and 1 <= len(predictions) <= 32
        and all(_valid_raw_prediction(item) for item in predictions)
        and isinstance(decisions, list)
        and 1 <= len(decisions) <= 32
        and all(_valid_raw_insight(item) for item in decisions)
        and type(data.get("execution_authorized")) is bool
        and type(data.get("bootloader_relock_permitted")) is bool
    )


def _valid_raw_route(item: object) -> bool:
    expected = {field.name for field in fields(PathfinderStage)}
    return bool(
        isinstance(item, dict)
        and set(item) == expected
        and all(isinstance(item.get(key), str) for key in expected)
    )


def _valid_raw_prediction(item: object) -> bool:
    expected = {field.name for field in fields(ForesightPrediction)}
    return bool(
        isinstance(item, dict)
        and set(item) == expected
        and all(
            isinstance(item.get(key), str)
            for key in (
                "prediction_id",
                "area",
                "impact",
                "prediction",
                "verification",
                "confidence",
            )
        )
        and _raw_string_list(item.get("dependencies"), 32)
    )


def _valid_raw_insight(item: object) -> bool:
    expected = {field.name for field in fields(InsightDecision)}
    return bool(
        isinstance(item, dict)
        and set(item) == expected
        and all(
            isinstance(item.get(key), str)
            for key in ("decision_id", "question", "answer", "why", "confidence")
        )
        and _raw_string_list(item.get("source_ids"), 32)
    )


def _raw_string_list(value: object, maximum: int) -> bool:
    return (
        isinstance(value, list)
        and len(value) <= maximum
        and all(isinstance(item, str) for item in value)
    )


def _plan_from_mapping(data: dict[str, object]) -> NexusPlan:
    route = tuple(_route_from_mapping(item) for item in _mapping_list(data.pop("route"), "route"))
    predictions = tuple(
        _prediction_from_mapping(item)
        for item in _mapping_list(data.pop("predictions"), "predictions")
    )
    decisions = tuple(
        _insight_from_mapping(item) for item in _mapping_list(data.pop("decisions"), "decisions")
    )
    return NexusPlan(
        schema_version=data["schema_version"],  # type: ignore[arg-type]
        plan_id=data["plan_id"],  # type: ignore[arg-type]
        mission_id=data["mission_id"],  # type: ignore[arg-type]
        project_id=data["project_id"],  # type: ignore[arg-type]
        objective=NexusObjective(data["objective"]),  # type: ignore[arg-type]
        created_at=data["created_at"],  # type: ignore[arg-type]
        device_dna_digest=data["device_dna_digest"],  # type: ignore[arg-type]
        compatibility_matrix_digest=data["compatibility_matrix_digest"],  # type: ignore[arg-type]
        status=NexusPlanStatus(data["status"]),  # type: ignore[arg-type]
        understanding=tuple(data["understanding"]),  # type: ignore[arg-type]
        research_requirements=tuple(data["research_requirements"]),  # type: ignore[arg-type]
        route=route,
        predictions=predictions,
        decisions=decisions,
        guardian_requirements=tuple(data["guardian_requirements"]),  # type: ignore[arg-type]
        flash_mode=FlashMode(data["flash_mode"]),  # type: ignore[arg-type]
        adaptation_of=data["adaptation_of"],  # type: ignore[arg-type]
        adaptation_reason=data["adaptation_reason"],  # type: ignore[arg-type]
        execution_authorized=data["execution_authorized"],  # type: ignore[arg-type]
        bootloader_relock_permitted=data["bootloader_relock_permitted"],  # type: ignore[arg-type]
        plan_digest=data["plan_digest"],  # type: ignore[arg-type]
    )


def _route_from_mapping(item: dict[str, object]) -> PathfinderStage:
    return PathfinderStage(
        item["stage_id"],  # type: ignore[arg-type]
        item["label"],  # type: ignore[arg-type]
        RouteStageState(item["state"]),  # type: ignore[arg-type]
        item["explanation"],  # type: ignore[arg-type]
        item["recommendation"],  # type: ignore[arg-type]
        item["branch"],  # type: ignore[arg-type]
    )


def _prediction_from_mapping(item: dict[str, object]) -> ForesightPrediction:
    return ForesightPrediction(
        item["prediction_id"],  # type: ignore[arg-type]
        item["area"],  # type: ignore[arg-type]
        ImpactLevel(item["impact"]),  # type: ignore[arg-type]
        item["prediction"],  # type: ignore[arg-type]
        tuple(item["dependencies"]),  # type: ignore[arg-type]
        item["verification"],  # type: ignore[arg-type]
        EvidenceConfidence(item["confidence"]),  # type: ignore[arg-type]
    )


def _insight_from_mapping(item: dict[str, object]) -> InsightDecision:
    return InsightDecision(
        item["decision_id"],  # type: ignore[arg-type]
        item["question"],  # type: ignore[arg-type]
        item["answer"],  # type: ignore[arg-type]
        item["why"],  # type: ignore[arg-type]
        tuple(item["source_ids"]),  # type: ignore[arg-type]
        EvidenceConfidence(item["confidence"]),  # type: ignore[arg-type]
    )


def _mapping_list(value: object, label: str) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise TypeError(f"Nexus {label} must be a list of objects")
    return tuple(value)  # type: ignore[return-value]
