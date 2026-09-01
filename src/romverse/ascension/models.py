from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AscensionMethod(StrEnum):
    MAGISK = "magisk"
    KERNELSU_LKM = "kernelsu_lkm"

    @property
    def display_name(self) -> str:
        return "Magisk" if self is self.MAGISK else "KernelSU LKM"


class GateState(StrEnum):
    PASS = "pass"
    ATTENTION = "attention"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class AscensionGate:
    gate_id: str
    title: str
    state: GateState
    detail: str
    resolution: str = ""


@dataclass(frozen=True, slots=True)
class AscensionAssessment:
    project_id: str
    method: AscensionMethod
    source_summary: str
    patch_target: str
    gates: tuple[AscensionGate, ...]
    execution_locked: bool = True

    @property
    def blocked(self) -> bool:
        return any(gate.state is GateState.BLOCKED for gate in self.gates)

    @property
    def ready_for_offline_preparation(self) -> bool:
        return not self.blocked


@dataclass(frozen=True, slots=True)
class AscensionRecommendation:
    method: AscensionMethod
    title: str
    reason: str
    evidence: tuple[str, ...]
    ready: bool = False


@dataclass(frozen=True, slots=True)
class OfficialRootAsset:
    provider: AscensionMethod
    repository: str
    tag: str
    published_at: str
    name: str
    size_bytes: int
    sha256: str
    download_url: str


@dataclass(frozen=True, slots=True)
class OfficialRootRelease:
    provider: AscensionMethod
    repository: str
    tag: str
    published_at: str
    asset: OfficialRootAsset
    source_url: str
