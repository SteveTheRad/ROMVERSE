from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from romverse.device_packs.drafts import DevicePackDraftService
from romverse.device_packs.registry import DevicePackRegistry
from romverse.infrastructure.local_store import LocalStoreError, read_regular_bytes
from romverse.rom.projects import RomProjectStore
from romverse.rom.simulation import RomSimulationService, SimulationSeverity


class FoundryEvidenceState(StrEnum):
    EVIDENCED = "evidenced"
    PARTIAL = "partial"
    PENDING = "pending"


@dataclass(frozen=True, slots=True)
class FoundryEvidenceLane:
    lane_id: str
    title: str
    state: FoundryEvidenceState
    detail: str


@dataclass(frozen=True, slots=True)
class FoundrySimulationEvidence:
    receipt_digest: str
    device_pack_id: str
    successful: bool
    blocker_count: int
    attention_count: int
    operation_count: int
    confidence_percent: int
    rollback_ready: bool
    hardware_unknown_count: int
    execution_authority: str


@dataclass(frozen=True, slots=True)
class FoundryDraftRevision:
    path: Path
    sha256: str
    pack_id: str
    version: str
    display_name: str
    manufacturers: tuple[str, ...]
    model_patterns: tuple[str, ...]
    product_patterns: tuple[str, ...]
    project_id: str
    source_sha256: str
    build_id: str
    partition_count: int
    source_avb_attached: bool
    device_dna_attached: bool
    device_dna_profile_digest: str
    device_dna_fact_count: int
    device_dna_partition_count: int
    device_dna_region: str
    simulation: FoundrySimulationEvidence | None
    missing_flash_contracts: tuple[str, ...]
    lanes: tuple[FoundryEvidenceLane, ...]
    publication_status: str
    execution_authority: str

    @property
    def evidenced_lane_count(self) -> int:
        return sum(lane.state is FoundryEvidenceState.EVIDENCED for lane in self.lanes)

    @property
    def source_bound(self) -> bool:
        return bool(self.project_id and self.source_sha256)

    @property
    def identity_keys(self) -> tuple[str, ...]:
        keys: list[str] = []
        for manufacturer in self.manufacturers:
            normalized_manufacturer = _normalized_identity(manufacturer)
            for model in self.model_patterns:
                keys.append(f"model:{normalized_manufacturer}:{_normalized_identity(model)}")
            for product in self.product_patterns:
                keys.append(f"product:{normalized_manufacturer}:{_normalized_identity(product)}")
        return tuple(dict.fromkeys(keys))


@dataclass(frozen=True, slots=True)
class FoundryIdentityConflict:
    identity_kind: str
    identity: str
    pack_ids: tuple[str, ...]
    revision_sha256s: tuple[str, ...]
    safest_action: str


@dataclass(frozen=True, slots=True)
class FoundryLoadIssue:
    filename: str
    reason: str


@dataclass(frozen=True, slots=True)
class DevicePackFoundryInventory:
    revisions: tuple[FoundryDraftRevision, ...]
    conflicts: tuple[FoundryIdentityConflict, ...]
    issues: tuple[FoundryLoadIssue, ...]
    publication_authority: str
    production_registry_changed: bool

    @property
    def pack_count(self) -> int:
        return len({revision.pack_id for revision in self.revisions})

    def best_for_identity(
        self,
        manufacturer: str,
        model: str,
        product: str,
        codename: str,
    ) -> FoundryDraftRevision | None:
        manufacturer_key = _normalized_identity(manufacturer)
        candidates = tuple(
            revision
            for revision in self.revisions
            if manufacturer_key
            and manufacturer_key
            in {_normalized_identity(value) for value in revision.manufacturers}
            and (
                _normalized_identity(model)
                in {_normalized_identity(value) for value in revision.model_patterns}
                or bool(
                    {_normalized_identity(value) for value in (product, codename) if value}
                    & {_normalized_identity(value) for value in revision.product_patterns}
                )
            )
        )
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda revision: (
                revision.evidenced_lane_count,
                revision.source_avb_attached,
                revision.device_dna_attached,
                revision.simulation is not None and revision.simulation.successful,
                revision.simulation is not None,
                revision.source_bound,
                revision.sha256,
            ),
        )


class DevicePackFoundryService:
    """Index strict private Pack drafts without adding them to the live registry."""

    MAX_DRAFTS = 512
    MAX_DIRECTORY_ENTRIES = 1_024
    MAX_DOCUMENT_BYTES = DevicePackDraftService.MAXIMUM_REQUEST_BYTES
    _BASE_FIELDS = {
        "schema_version",
        "publication_status",
        "pack_id",
        "version",
        "display_name",
        "priority",
        "match",
        "knowledge_sources",
        "capabilities",
        "notes",
    }

    def inspect(
        self,
        output_dir: Path,
        *,
        boundary: Path,
    ) -> DevicePackFoundryInventory:
        directory = self._safe_directory(output_dir, boundary)
        if directory is None:
            return DevicePackFoundryInventory((), (), (), "none", False)
        try:
            entries = tuple(directory.iterdir())
        except OSError as exc:
            raise ValueError(f"Device Pack Foundry inventory is unavailable: {exc}") from exc
        if len(entries) > self.MAX_DIRECTORY_ENTRIES:
            raise ValueError("Device Pack Foundry directory exceeds its bounded inventory")
        candidates = tuple(
            sorted(
                (path for path in entries if path.name.endswith(".draft.json")),
                key=lambda path: path.name,
            )
        )
        if len(candidates) > self.MAX_DRAFTS:
            raise ValueError("Device Pack Foundry has too many experimental revisions")
        revisions: list[FoundryDraftRevision] = []
        issues: list[FoundryLoadIssue] = []
        for path in candidates:
            try:
                revisions.append(self._inspect_revision(path, boundary))
            except (LocalStoreError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                issues.append(FoundryLoadIssue(path.name[:180], str(exc)[:400]))
        ordered = tuple(
            sorted(
                revisions,
                key=lambda revision: (
                    revision.pack_id,
                    revision.evidenced_lane_count,
                    revision.source_avb_attached,
                    revision.device_dna_attached,
                    revision.simulation is not None and revision.simulation.successful,
                    revision.simulation is not None,
                    revision.sha256,
                ),
                reverse=True,
            )
        )
        return DevicePackFoundryInventory(
            ordered,
            self._conflicts(ordered),
            tuple(issues),
            "none",
            False,
        )

    def _inspect_revision(self, path: Path, boundary: Path) -> FoundryDraftRevision:
        payload = read_regular_bytes(
            path,
            boundary=boundary,
            maximum_bytes=self.MAX_DOCUMENT_BYTES,
        )
        document = json.loads(payload.decode("utf-8"))
        if not isinstance(document, dict):
            raise ValueError("Device Pack draft must be a JSON object")
        canonical = _canonical(document) + b"\n"
        if payload != canonical:
            raise ValueError("Device Pack draft bytes are not the canonical exported artifact")
        has_context = "draft_context" in document
        expected = self._BASE_FIELDS | ({"draft_context"} if has_context else set())
        if (
            set(document) != expected
            or document.get("schema_version") != 1
            or document.get("publication_status") != "draft"
        ):
            raise ValueError("unsupported experimental Device Pack draft")
        digest = hashlib.sha256(payload).hexdigest()
        pack_document = dict(document)
        pack_document.pop("publication_status")
        pack_document.pop("draft_context", None)
        pack = DevicePackRegistry._parse(pack_document, digest)
        if path.name != f"{pack.pack_id}-{digest[:12]}.draft.json":
            raise ValueError("Device Pack draft filename does not match its exact bytes")
        if (
            not pack.manufacturers
            or not pack.model_patterns
            or not pack.product_patterns
            or any(
                value == "*"
                for value in (*pack.manufacturers, *pack.model_patterns, *pack.product_patterns)
            )
        ):
            raise ValueError("Foundry drafts require bounded exact device identity")
        capability_contract = tuple(
            (capability.capability_id, capability.status.value, capability.scope)
            for capability in pack.capabilities
        )
        if capability_contract != (
            ("exact_identity", "limited", "evidence_only"),
            ("firmware_contract", "planned", "locked"),
            ("partition_layout", "planned", "locked"),
            ("physical_recovery", "planned", "locked"),
        ):
            raise ValueError("Device Pack draft capability boundary changed")
        joined_notes = " ".join(pack.notes)
        if (
            "DRAFT ONLY" not in joined_notes
            or "Execution authority is NONE" not in joined_notes
            or "cannot activate" not in joined_notes
        ):
            raise ValueError("Device Pack draft safety declaration is incomplete")
        draft_service = DevicePackDraftService()
        review = draft_service._review_document(path, document) if has_context else None
        if (
            review is not None
            and review.device_dna_attached
            and not draft_service.verify_device_dna_attachment(document, workspace=boundary)
        ):
            raise ValueError("Device DNA attachment no longer matches the sealed workspace profile")
        simulation = self._simulation_evidence(review, boundary)
        lanes = self._lanes(pack, review, simulation)
        return FoundryDraftRevision(
            path,
            digest,
            pack.pack_id,
            pack.version,
            pack.display_name,
            pack.manufacturers,
            pack.model_patterns,
            pack.product_patterns,
            review.project_id if review is not None else "",
            review.source_sha256 if review is not None else "",
            review.build_id if review is not None else "",
            review.partition_count if review is not None else 0,
            review.source_avb_attached if review is not None else False,
            review.device_dna_attached if review is not None else False,
            review.device_dna_profile_digest if review is not None else "",
            review.device_dna_fact_count if review is not None else 0,
            review.device_dna_partition_count if review is not None else 0,
            review.device_dna_region if review is not None else "",
            simulation,
            (
                review.missing_flash_contracts
                if review is not None
                else DevicePackDraftService.MISSING_FLASH_CONTRACTS
            ),
            lanes,
            "experimental-draft",
            "none",
        )

    @staticmethod
    def _lanes(pack, review, simulation) -> tuple[FoundryEvidenceLane, ...]:
        source_bound = review is not None
        avb_bound = source_bound and review.source_avb_attached
        dna_bound = source_bound and review.device_dna_attached
        alias_count = len(set((*pack.model_patterns, *pack.product_patterns)))
        return (
            FoundryEvidenceLane(
                "identity",
                "Observed identity",
                FoundryEvidenceState.EVIDENCED,
                f"{', '.join(pack.manufacturers)} • {', '.join(pack.model_patterns)}",
            ),
            FoundryEvidenceLane(
                "variants",
                "Observed variant",
                (FoundryEvidenceState.EVIDENCED if dna_bound else FoundryEvidenceState.PARTIAL),
                (
                    f"Sealed DNA {review.device_dna_profile_digest[:12]}… contributes "
                    f"{review.device_dna_fact_count} privacy-safe fact(s); "
                    f"region {review.device_dna_region or 'unconfirmed'} remains observation only."
                    if dna_bound
                    else f"{alias_count} exact model/product identity value(s); region is evidence, not a matcher."
                ),
            ),
            FoundryEvidenceLane(
                "firmware",
                "Factory firmware",
                FoundryEvidenceState.EVIDENCED if source_bound else FoundryEvidenceState.PENDING,
                (
                    f"Build {review.build_id} is bound to protected source {review.source_sha256[:12]}…"
                    + (
                        f" and sealed Device DNA {review.device_dna_profile_digest[:12]}…"
                        if dna_bound
                        else "."
                    )
                    if source_bound
                    else "Attach a genuine protected factory/OTA source and source blueprint."
                ),
            ),
            FoundryEvidenceLane(
                "partitions",
                "Partitions + AVB",
                FoundryEvidenceState.EVIDENCED
                if avb_bound
                else FoundryEvidenceState.PARTIAL
                if source_bound
                else FoundryEvidenceState.PENDING,
                (
                    f"{review.partition_count} source partition record(s), "
                    f"{review.device_dna_partition_count} DNA record(s); OEM AVB topology attached."
                    if avb_bound
                    else f"{review.partition_count} source partition record(s), "
                    f"{review.device_dna_partition_count} DNA record(s); OEM AVB topology pending."
                    if dna_bound
                    else f"{review.partition_count} partition record(s); OEM AVB topology pending."
                    if source_bound
                    else "Partition, slot, dynamic-group and AVB evidence are pending."
                ),
            ),
            FoundryEvidenceLane(
                "flash-contract",
                "Flash + rollback contract",
                FoundryEvidenceState.PENDING,
                "Exact writes, readbacks, transitions, slots and stock recovery remain unapproved.",
            ),
            FoundryEvidenceLane(
                "physical-test",
                "Simulation + device test",
                (
                    FoundryEvidenceState.PARTIAL
                    if simulation is not None
                    else FoundryEvidenceState.PENDING
                ),
                (
                    f"Digital Twin {simulation.receipt_digest[:12]}… passed "
                    f"{simulation.operation_count} inert operation(s) at "
                    f"{simulation.confidence_percent}% confidence; signed physical recovery and "
                    f"first-boot evidence are still required."
                    if simulation is not None and simulation.successful
                    else f"Digital Twin {simulation.receipt_digest[:12]}… reports "
                    f"{simulation.blocker_count} blocker(s) and {simulation.attention_count} "
                    "attention item(s); resolve them and still complete signed physical testing."
                    if simulation is not None
                    else "Run the source/DNA-bound Digital Twin, then complete signed physical recovery and first-boot testing."
                ),
            ),
        )

    @staticmethod
    def _simulation_evidence(
        review,
        workspace: Path,
    ) -> FoundrySimulationEvidence | None:
        if review is None or not review.device_dna_attached:
            return None
        try:
            receipt = RomSimulationService(
                RomProjectStore(workspace),
                DevicePackRegistry(()),
            ).load(review.project_id)
        except (OSError, TypeError, ValueError):
            return None
        if (
            receipt is None
            or receipt.source_sha256 != review.source_sha256
            or receipt.device_dna_digest != review.device_dna_profile_digest
            or receipt.phone_changed
            or receipt.execution_authority != "none"
            or not 0 <= receipt.confidence_percent <= 92
            or not 0 <= receipt.observed_battery_percent <= 100
            and receipt.observed_battery_percent != -1
        ):
            return None
        blocker_count = sum(
            finding.severity is SimulationSeverity.BLOCKED for finding in receipt.findings
        )
        attention_count = sum(
            finding.severity is SimulationSeverity.ATTENTION for finding in receipt.findings
        )
        expected_successful = bool(receipt.operations) and blocker_count == 0
        if receipt.successful != expected_successful or receipt.mission_ready != receipt.successful:
            return None
        successful = bool(
            receipt.successful
            and receipt.mission_ready
            and receipt.operations
            and blocker_count == 0
            and not receipt.expert_edits
        )
        return FoundrySimulationEvidence(
            receipt.receipt_digest,
            receipt.device_pack_id,
            successful,
            blocker_count,
            attention_count,
            len(receipt.operations),
            receipt.confidence_percent,
            receipt.rollback.ready,
            len(receipt.hardware_unknowns),
            "none",
        )

    @staticmethod
    def _conflicts(
        revisions: tuple[FoundryDraftRevision, ...],
    ) -> tuple[FoundryIdentityConflict, ...]:
        by_identity: dict[str, list[FoundryDraftRevision]] = {}
        for revision in revisions:
            for identity in revision.identity_keys:
                by_identity.setdefault(identity, []).append(revision)
        conflicts: list[FoundryIdentityConflict] = []
        for identity, matches in sorted(by_identity.items()):
            pack_ids = tuple(sorted({match.pack_id for match in matches}))
            if len(pack_ids) < 2:
                continue
            kind, _manufacturer, value = identity.split(":", 2)
            conflicts.append(
                FoundryIdentityConflict(
                    kind,
                    value,
                    pack_ids,
                    tuple(sorted({match.sha256 for match in matches})),
                    "Keep every matching draft experimental and reconcile measured Device DNA, "
                    "factory-source and physical-test evidence before choosing one Pack lineage.",
                )
            )
        return tuple(conflicts)

    @staticmethod
    def _safe_directory(output_dir: Path, boundary: Path) -> Path | None:
        unresolved = Path(os.path.abspath(output_dir))
        boundary_path = Path(os.path.abspath(boundary))
        try:
            boundary_resolved = boundary_path.resolve(strict=True)
            if not unresolved.exists():
                return None
            details = unresolved.lstat()
            resolved = unresolved.resolve(strict=True)
            resolved.relative_to(boundary_resolved)
        except FileNotFoundError:
            return None
        except (OSError, RuntimeError, ValueError) as exc:
            raise ValueError("Device Pack Foundry directory is outside its workspace") from exc
        if unresolved.is_symlink() or not stat.S_ISDIR(details.st_mode) or not resolved.is_dir():
            raise ValueError("Device Pack Foundry directory is unsafe")
        return resolved


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _normalized_identity(value: str) -> str:
    return " ".join(value.casefold().split())
