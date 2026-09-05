from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Protocol

from romverse.rom.models import ProjectError


class FirmwareAdapter(StrEnum):
    """The complete, frozen set of firmware evidence adapters."""

    OTA_PAYLOAD = "ota-payload"
    FASTBOOT_SUPER = "fastboot-super"
    PARTITION_BUNDLE = "partition-bundle"


@dataclass(frozen=True, slots=True)
class FirmwareSourceSnapshot:
    """One immutable, authority-free observation of an isolated source tree."""

    payload_paths: tuple[str, ...]
    super_paths: tuple[str, ...]
    partition_images: tuple[str, ...]

    def __post_init__(self) -> None:
        collections = (
            ("payload", self.payload_paths, "payload.bin"),
            ("super", self.super_paths, "super.img"),
            ("partition image", self.partition_images, ".img"),
        )
        for label, paths, expected in collections:
            if type(paths) is not tuple or paths != tuple(sorted(set(paths))):
                raise ProjectError(f"Firmware {label} evidence must be unique and deterministic")
            for value in paths:
                if not isinstance(value, str) or not value:
                    raise ProjectError(f"Firmware {label} evidence contains an invalid path")
                path = PurePosixPath(value)
                if path.is_absolute() or ".." in path.parts:
                    raise ProjectError(f"Firmware {label} evidence escaped the workspace")
                if expected.startswith("."):
                    valid_name = path.suffix.casefold() == expected
                else:
                    valid_name = path.name.casefold() == expected
                if not valid_name:
                    raise ProjectError(f"Firmware {label} evidence has an unexpected file name")


@dataclass(frozen=True, slots=True)
class FirmwareSourceAnalysis:
    """Evidence-only classification; it grants no build, device, or execution authority."""

    adapter: FirmwareAdapter
    payload_path: str
    super_path: str
    partition_images: tuple[str, ...]
    explanation: str


ProgressCallback = Callable[[int], None]
PrepareEvidence = Callable[[str, FirmwareSourceAnalysis, ProgressCallback | None], object]
LoadEvidence = Callable[[str], object | None]
MatchEvidence = Callable[[FirmwareSourceSnapshot], FirmwareSourceAnalysis | None]


class FirmwareSourceEvidenceAdapter(Protocol):
    """Read/derive-only boundary for one known firmware evidence representation."""

    adapter_id: FirmwareAdapter
    evidence_authority: str

    def match(self, snapshot: FirmwareSourceSnapshot) -> FirmwareSourceAnalysis | None: ...

    def prepare(
        self,
        project_id: str,
        analysis: FirmwareSourceAnalysis,
        progress: ProgressCallback | None,
    ) -> object: ...

    def load(self, project_id: str) -> object | None: ...


@dataclass(frozen=True, slots=True)
class BoundedFirmwareSourceEvidenceAdapter:
    """Internally bound implementation for one of the three frozen evidence handlers."""

    adapter_id: FirmwareAdapter
    evidence_authority: str
    _matcher: MatchEvidence
    _preparer: PrepareEvidence
    _loader: LoadEvidence

    def match(self, snapshot: FirmwareSourceSnapshot) -> FirmwareSourceAnalysis | None:
        return self._matcher(snapshot)

    def prepare(
        self,
        project_id: str,
        analysis: FirmwareSourceAnalysis,
        progress: ProgressCallback | None,
    ) -> object:
        return self._preparer(project_id, analysis, progress)

    def load(self, project_id: str) -> object | None:
        return self._loader(project_id)


class FirmwareSourceEvidenceAdapterRegistry:
    """Deterministic, closed registry for evidence adapters; never an execution registry."""

    _EXPECTED_IDS = frozenset(FirmwareAdapter)

    def __init__(self, adapters: tuple[FirmwareSourceEvidenceAdapter, ...]) -> None:
        if type(adapters) is not tuple:
            raise ProjectError("Firmware evidence adapters must be registered deterministically")
        identities = tuple(adapter.adapter_id for adapter in adapters)
        if any(type(identity) is not FirmwareAdapter for identity in identities):
            raise ProjectError("Firmware evidence registry contains an unknown adapter identity")
        if len(set(identities)) != len(identities):
            raise ProjectError("Firmware evidence registry contains a duplicate adapter identity")
        if frozenset(identities) != self._EXPECTED_IDS:
            raise ProjectError(
                "Firmware evidence registry must contain exactly the frozen adapters"
            )
        self._adapters = tuple(sorted(adapters, key=lambda adapter: adapter.adapter_id.value))

    @property
    def adapter_ids(self) -> tuple[FirmwareAdapter, ...]:
        return tuple(adapter.adapter_id for adapter in self._adapters)

    def analyze(self, snapshot: FirmwareSourceSnapshot) -> FirmwareSourceAnalysis:
        matches = tuple(
            match for adapter in self._adapters if (match := adapter.match(snapshot)) is not None
        )
        if not matches:
            raise ProjectError(
                "ROMVERSE could not find payload.bin, super.img, or a supported partition image bundle"
            )
        if len(matches) != 1:
            names = ", ".join(sorted(match.adapter.value for match in matches))
            raise ProjectError(
                f"Firmware source matches multiple evidence adapters ({names}); source is ambiguous"
            )
        match = matches[0]
        self._adapter(match.adapter)
        return match

    def prepare(
        self,
        project_id: str,
        snapshot: FirmwareSourceSnapshot,
        progress: ProgressCallback | None = None,
    ) -> object:
        analysis = self.analyze(snapshot)
        adapter = self._adapter(analysis.adapter)
        blueprint = adapter.prepare(project_id, analysis, progress)
        self._validate_blueprint(project_id, adapter, blueprint)
        return blueprint

    def load(self, project_id: str) -> object | None:
        matches: list[tuple[FirmwareSourceEvidenceAdapter, object]] = []
        for adapter in self._adapters:
            blueprint = adapter.load(project_id)
            if blueprint is None:
                continue
            self._validate_blueprint(project_id, adapter, blueprint)
            matches.append((adapter, blueprint))
        if len(matches) > 1:
            names = ", ".join(adapter.adapter_id.value for adapter, _blueprint in matches)
            raise ProjectError(
                f"Multiple valid firmware evidence blueprints were found ({names}); source is ambiguous"
            )
        return matches[0][1] if matches else None

    def _adapter(self, identity: FirmwareAdapter) -> FirmwareSourceEvidenceAdapter:
        adapter = next((item for item in self._adapters if item.adapter_id is identity), None)
        if adapter is None:
            raise ProjectError("Firmware evidence adapter is not registered")
        return adapter

    @staticmethod
    def _validate_blueprint(
        project_id: str,
        adapter: FirmwareSourceEvidenceAdapter,
        blueprint: object,
    ) -> None:
        if (
            getattr(blueprint, "project_id", None) != project_id
            or getattr(blueprint, "source_kind", None) != adapter.adapter_id.value
            or getattr(blueprint, "authority", None) != adapter.evidence_authority
            or getattr(blueprint, "phone_changed", None) is not False
            or getattr(blueprint, "baseline_candidate_ready", None) is not True
        ):
            raise ProjectError("Firmware adapter returned invalid or authority-bearing evidence")


def match_ota_payload(snapshot: FirmwareSourceSnapshot) -> FirmwareSourceAnalysis | None:
    if len(snapshot.payload_paths) > 1:
        raise ProjectError(
            "Multiple payload.bin files were found; the firmware source is ambiguous"
        )
    if not snapshot.payload_paths:
        return None
    return FirmwareSourceAnalysis(
        FirmwareAdapter.OTA_PAYLOAD,
        snapshot.payload_paths[0],
        snapshot.super_paths[0] if len(snapshot.super_paths) == 1 else "",
        snapshot.partition_images,
        "OTA payload detected; ROMVERSE selected Payload Atlas extraction and OTA provenance rules.",
    )


def match_fastboot_super(snapshot: FirmwareSourceSnapshot) -> FirmwareSourceAnalysis | None:
    if len(snapshot.super_paths) > 1:
        raise ProjectError("Multiple super.img files were found; the firmware source is ambiguous")
    if not snapshot.super_paths:
        return None
    return FirmwareSourceAnalysis(
        FirmwareAdapter.FASTBOOT_SUPER,
        "",
        snapshot.super_paths[0],
        snapshot.partition_images,
        "Fastboot super image detected; ROMVERSE selected sparse-super and logical-partition tools.",
    )


def match_partition_bundle(snapshot: FirmwareSourceSnapshot) -> FirmwareSourceAnalysis | None:
    # A raw bundle is deliberately a fallback. A payload or super source is handled by its
    # exact adapter even though super.img is itself part of the observed image inventory.
    if snapshot.payload_paths or snapshot.super_paths or not snapshot.partition_images:
        return None
    return FirmwareSourceAnalysis(
        FirmwareAdapter.PARTITION_BUNDLE,
        "",
        "",
        snapshot.partition_images,
        "Raw partition image bundle detected; ROMVERSE selected per-image inspection.",
    )
