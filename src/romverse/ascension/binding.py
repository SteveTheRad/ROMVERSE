from __future__ import annotations

import re
from dataclasses import dataclass

from romverse.device.dna import CapabilityState, DeviceDnaStore
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.registry import DevicePackRegistry
from romverse.infrastructure.process import SubprocessRunner
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.rom.source_identity import identify_firmware_source
from romverse.rom.source_intelligence import FirmwareSourceIntelligenceService


@dataclass(frozen=True, slots=True)
class AscensionSourceBinding:
    """One source-bound identity used by every Ascension phone handoff."""

    project_id: str
    source_sha256: str
    codename: str
    manufacturer: str
    build_id: str
    authority: str
    evidence: tuple[str, ...]
    conflicts: tuple[str, ...]
    device_dna_digest: str
    device_dna_state: CapabilityState

    @property
    def confirmed(self) -> bool:
        return bool(self.codename and not self.conflicts)

    def matches(self, device: AndroidDevice) -> bool:
        return bool(
            self.confirmed
            and device.state is DeviceState.DEVICE
            and device.codename
            and device.codename.casefold() == self.codename.casefold()
        )


class AscensionSourceBindingService:
    """Resolve exact firmware identity without treating a model-name guess as proof."""

    def __init__(
        self,
        store: RomProjectStore,
        registry: DevicePackRegistry | None = None,
    ) -> None:
        self.store = store
        self.registry = registry or DevicePackRegistry(())

    def resolve(self, project_id: str) -> AscensionSourceBinding:
        project = self.store.get(project_id)
        if project.original is None:
            raise ProjectError("Ascension source binding requires a protected firmware source")
        identity = identify_firmware_source(project.original.original_name)
        candidates: list[tuple[str, str, str]] = []
        evidence: list[str] = []
        pack_manufacturer = ""
        pack_build_id = ""

        resolution = self.registry.resolve_source(project.original.sha256)
        if resolution.matched and resolution.pack is not None:
            pack_codenames = tuple(
                value.casefold()
                for value in resolution.pack.product_patterns
                if re.fullmatch(r"[A-Za-z0-9._-]{2,80}", value)
            )
            pack_manufacturer = next(iter(resolution.pack.manufacturers), "")
            if resolution.pack.build_contract is not None:
                pack_build_id = resolution.pack.build_contract.source.build_id
            if identity.codename and identity.codename.casefold() in pack_codenames:
                candidates.append(
                    (
                        identity.codename,
                        "exact-device-pack",
                        f"Exact Device Pack {resolution.pack.pack_id} and firmware identity agree.",
                    )
                )
            elif len(set(pack_codenames)) == 1:
                candidates.append(
                    (
                        pack_codenames[0],
                        "exact-device-pack",
                        f"Exact Device Pack {resolution.pack.pack_id} is bound to the source SHA-256.",
                    )
                )
            else:
                evidence.append(
                    f"Exact Device Pack {resolution.pack.pack_id} has no single source codename."
                )

        blueprint = FirmwareSourceIntelligenceService(
            self.store,
            (),
            SubprocessRunner(),
        ).load(project_id)
        if blueprint is not None and getattr(blueprint, "codename", ""):
            candidates.append(
                (
                    str(blueprint.codename),
                    "source-blueprint",
                    f"Source-bound {blueprint.source_kind} blueprint {blueprint.blueprint_digest[:16]}…",
                )
            )

        if identity.codename and identity.confidence == "high":
            candidates.append(
                (
                    identity.codename,
                    "firmware-identity",
                    "High-confidence firmware identity matched the protected source name.",
                )
            )

        normalized = {codename.casefold() for codename, _authority, _detail in candidates}
        conflicts = (
            (f"Conflicting source codenames: {', '.join(sorted(normalized))}",)
            if len(normalized) > 1
            else ()
        )
        codename = next(iter(normalized), "") if len(normalized) == 1 else ""
        priority = {"exact-device-pack": 0, "source-blueprint": 1, "firmware-identity": 2}
        selected = min(candidates, key=lambda item: priority[item[1]]) if codename else None
        evidence.extend(item[2] for item in candidates)

        dna = DeviceDnaStore(self.store).load(project_id)
        dna_digest = dna.profile_digest if dna is not None else ""
        dna_capability = dna.capability("device_identity") if dna is not None else None
        dna_state = (
            dna_capability.state if dna_capability is not None else CapabilityState.UNCONFIRMED
        )
        if dna is not None:
            evidence.append(
                f"Device DNA {dna.profile_digest[:16]}… reports identity {dna_state.value}."
            )
        else:
            evidence.append("Device DNA is not yet available for this protected source.")

        return AscensionSourceBinding(
            project_id=project_id,
            source_sha256=project.original.sha256,
            codename=codename,
            manufacturer=identity.manufacturer or pack_manufacturer,
            build_id=identity.build_id or pack_build_id,
            authority=selected[1] if selected else "unconfirmed",
            evidence=tuple(dict.fromkeys(evidence)),
            conflicts=conflicts,
            device_dna_digest=dna_digest,
            device_dna_state=dna_state,
        )
