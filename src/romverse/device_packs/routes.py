from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

from romverse.device_packs.drafts import DevicePackDraftService
from romverse.device_packs.foundry import FoundryDraftRevision
from romverse.infrastructure.local_store import atomic_write_bytes, read_regular_bytes


class FoundryRouteState(StrEnum):
    NEEDS_EVIDENCE = "needs-evidence"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class FoundryRouteObservation:
    fact_id: str
    value: str
    confidence: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FoundryDeviceRoute:
    route_id: str
    title: str
    state: FoundryRouteState
    observation_ids: tuple[str, ...]
    requirements: tuple[str, ...]
    authority: str


@dataclass(frozen=True, slots=True)
class DevicePackRouteBlueprint:
    schema_version: int
    pack_id: str
    pack_version: str
    draft_sha256: str
    project_id: str
    source_sha256: str
    device_dna_profile_digest: str
    observations: tuple[FoundryRouteObservation, ...]
    routes: tuple[FoundryDeviceRoute, ...]
    operational_characteristics: tuple[str, ...]
    minimum_identity_facts_present: bool
    bootloader_relock_allowed: bool
    automatic_device_actions: bool
    execution_authority: str
    blueprint_digest: str

    @property
    def evidenced_observation_count(self) -> int:
        return len(self.observations)

    @property
    def blocked_route_count(self) -> int:
        return sum(route.state is FoundryRouteState.BLOCKED for route in self.routes)


@dataclass(frozen=True, slots=True)
class DevicePackRouteBlueprintExport:
    output_path: Path
    sha256: str
    size_bytes: int


class DevicePackRouteBlueprintService:
    """Derive route-engineering requirements from sealed facts, never raw commands."""

    FORMAT = "romverse.device-pack-route-blueprint"
    SCHEMA_VERSION = 1
    MAXIMUM_BYTES = 256 * 1024
    ROUTE_FACT_IDS = (
        "bootloader.state",
        "boot.active_slot",
        "partition.ab_scheme",
        "partition.architecture",
        "security.verified_boot",
        "capability.fastboot",
        "capability.recovery",
    )

    def derive(
        self,
        revision: FoundryDraftRevision,
        *,
        boundary: Path,
    ) -> DevicePackRouteBlueprint:
        try:
            payload = read_regular_bytes(
                revision.path,
                boundary=boundary,
                maximum_bytes=DevicePackDraftService.MAXIMUM_REQUEST_BYTES,
            )
            document = json.loads(payload)
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("Foundry route source is unreadable or unsafe") from exc
        if (
            not isinstance(document, dict)
            or payload != _canonical(document) + b"\n"
            or hashlib.sha256(payload).hexdigest() != revision.sha256
            or revision.path.name != f"{revision.pack_id}-{revision.sha256[:12]}.draft.json"
        ):
            raise ValueError("Foundry route source no longer matches the exact draft revision")
        draft_service = DevicePackDraftService()
        try:
            review = draft_service._review_document(revision.path, document)
        except (TypeError, ValueError) as exc:
            raise ValueError("Foundry route source is not an exact-source draft") from exc
        if (
            review.sha256 != revision.sha256
            or review.pack_id != revision.pack_id
            or review.project_id != revision.project_id
            or review.source_sha256 != revision.source_sha256
            or not review.device_dna_attached
            or review.device_dna_profile_digest != revision.device_dna_profile_digest
            or not draft_service.verify_device_dna_attachment(document, workspace=boundary)
        ):
            raise ValueError("Foundry route source lacks the current sealed Device DNA binding")
        context = document.get("draft_context")
        if not isinstance(context, dict):
            raise ValueError("Foundry route source context is unavailable")
        dna = context.get("device_dna_evidence")
        if not isinstance(dna, dict) or not isinstance(dna.get("facts"), list):
            raise ValueError("Foundry route source has no measured route facts")
        fact_map = {
            str(item.get("fact_id")): item for item in dna["facts"] if isinstance(item, dict)
        }
        observations: list[FoundryRouteObservation] = []
        for fact_id in self.ROUTE_FACT_IDS:
            fact = fact_map.get(fact_id)
            if fact is None:
                continue
            evidence_ids = fact.get("evidence_ids")
            if not isinstance(evidence_ids, list):
                raise ValueError("Foundry route fact evidence is invalid")
            observations.append(
                FoundryRouteObservation(
                    fact_id,
                    str(fact.get("value", "")),
                    str(fact.get("confidence", "")),
                    tuple(map(str, evidence_ids)),
                )
            )
        source_avb = context.get("source_avb_evidence")
        if isinstance(source_avb, dict):
            observations.extend(
                (
                    FoundryRouteObservation(
                        "avb.algorithm",
                        str(source_avb.get("algorithm", "")),
                        "verified",
                        ("source.avb",),
                    ),
                    FoundryRouteObservation(
                        "avb.chain_partitions",
                        ", ".join(map(str, source_avb.get("top_level_chain_partitions", ()))),
                        "verified",
                        ("source.avb",),
                    ),
                )
            )
        observations.append(
            FoundryRouteObservation(
                "partition.source_count",
                str(revision.partition_count),
                "verified",
                ("source.blueprint",),
            )
        )
        observation_map = {item.fact_id: item for item in observations}
        characteristics = self._characteristics(observation_map)
        required_identity_facts = {
            "bootloader.state",
            "partition.ab_scheme",
            "partition.architecture",
            "security.verified_boot",
        }
        identity_ready = required_identity_facts.issubset(observation_map)
        routes = (
            FoundryDeviceRoute(
                "backup",
                "Pre-change backup route",
                FoundryRouteState.NEEDS_EVIDENCE,
                ("boot.active_slot", "partition.ab_scheme", "partition.architecture"),
                (
                    "Independent user-data backup location and completion proof",
                    "Exact pre-write slot and Device DNA checkpoint",
                    "Verified stock package and restore rehearsal",
                    "Explicit wipe consequences and restore verification",
                ),
                "review-only",
            ),
            FoundryDeviceRoute(
                "flash",
                "Exact partition flash route",
                FoundryRouteState.BLOCKED,
                (
                    "bootloader.state",
                    "boot.active_slot",
                    "partition.ab_scheme",
                    "partition.architecture",
                    "security.verified_boot",
                    "capability.fastboot",
                    "avb.algorithm",
                    "avb.chain_partitions",
                ),
                (
                    "Ordered partition-to-artifact mapping with exact target slot and transport",
                    "Full artifact hashes, size limits and pre-write checks",
                    "Post-write full-partition readback hashes",
                    "Contiguous bootloader/fastbootd/system transitions with timeouts",
                    "Exact AVB execution policy bound to independent physical evidence",
                ),
                "none",
            ),
            FoundryDeviceRoute(
                "rollback",
                "Exact rollback route",
                FoundryRouteState.BLOCKED,
                (
                    "bootloader.state",
                    "boot.active_slot",
                    "partition.ab_scheme",
                    "security.verified_boot",
                ),
                (
                    "Exact stock package hash and anti-rollback compatibility proof",
                    "Recorded original slot plus supported slot-restoration sequence",
                    "Data-loss disclosure and separate final consent",
                    "Successful Simulation Lab rollback rehearsal",
                ),
                "none",
            ),
            FoundryDeviceRoute(
                "recovery",
                "Failure and stock recovery route",
                FoundryRouteState.BLOCKED,
                (
                    "bootloader.state",
                    "partition.ab_scheme",
                    "capability.fastboot",
                    "capability.recovery",
                ),
                (
                    "Exact entry state and bounded adapter action sequence",
                    "Verified stock restore plus failed-flash and slot-recovery tests",
                    "Measured first-boot properties and bounded reconnect timeout",
                    "Independent signed physical-device report",
                ),
                "none",
            ),
        )
        partial = {
            "schema_version": self.SCHEMA_VERSION,
            "pack_id": revision.pack_id,
            "pack_version": revision.version,
            "draft_sha256": revision.sha256,
            "project_id": revision.project_id,
            "source_sha256": revision.source_sha256,
            "device_dna_profile_digest": revision.device_dna_profile_digest,
            "observations": [asdict(item) for item in observations],
            "routes": [asdict(route) for route in routes],
            "operational_characteristics": list(characteristics),
            "bootloader_relock_allowed": False,
            "automatic_device_actions": False,
            "execution_authority": "none",
            "minimum_identity_facts_present": identity_ready,
        }
        digest = hashlib.sha256(_canonical(partial)).hexdigest()
        return DevicePackRouteBlueprint(
            self.SCHEMA_VERSION,
            revision.pack_id,
            revision.version,
            revision.sha256,
            revision.project_id,
            revision.source_sha256,
            revision.device_dna_profile_digest,
            tuple(observations),
            routes,
            characteristics,
            identity_ready,
            False,
            False,
            "none",
            digest,
        )

    def export(
        self,
        blueprint: DevicePackRouteBlueprint,
        output_dir: Path,
        *,
        boundary: Path,
    ) -> DevicePackRouteBlueprintExport:
        document = {"format": self.FORMAT, **asdict(blueprint)}
        payload = _canonical(document) + b"\n"
        digest = hashlib.sha256(payload).hexdigest()
        output = output_dir / (
            f"{_safe_name(blueprint.pack_id)}-{digest[:12]}.route-blueprint.json"
        )
        atomic_write_bytes(
            output,
            payload,
            boundary=boundary,
            maximum_bytes=self.MAXIMUM_BYTES,
        )
        return DevicePackRouteBlueprintExport(output, digest, len(payload))

    @staticmethod
    def _characteristics(
        observations: dict[str, FoundryRouteObservation],
    ) -> tuple[str, ...]:
        results: list[str] = []

        def value(fact_id: str) -> str:
            fact = observations.get(fact_id)
            return fact.value if fact is not None else ""

        bootloader = value("bootloader.state").casefold()
        if bootloader:
            results.append(
                f"Bootloader was observed {bootloader}; every future operation must revalidate it."
            )
        scheme = value("partition.ab_scheme")
        if scheme:
            results.append(
                f"{scheme} slot layout observed; target and recovery slots cannot be inferred."
            )
        architecture = value("partition.architecture")
        if architecture:
            results.append(
                f"Partition architecture: {architecture}; exact group geometry still requires review."
            )
        verified_boot = value("security.verified_boot")
        if verified_boot:
            results.append(
                f"Verified Boot state was {verified_boot}; this observation is not an AVB execution policy."
            )
        fastboot = value("capability.fastboot")
        if fastboot:
            results.append(
                f"Fastboot evidence: {fastboot}; transport availability does not prove writable partitions."
            )
        return tuple(results)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _safe_name(value: str) -> str:
    safe = "".join(
        character if character.isalnum() or character in ".-_" else "-" for character in value
    )
    return safe.strip(".-") or "device-pack"
