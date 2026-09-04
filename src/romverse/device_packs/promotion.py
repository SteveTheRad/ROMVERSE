from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from romverse.device_packs.contributions import DevicePackContributionReport
from romverse.device_packs.foundry import (
    DevicePackFoundryInventory,
    FoundryDraftRevision,
    FoundryEvidenceState,
)
from romverse.infrastructure.local_store import atomic_write_bytes


@dataclass(frozen=True, slots=True)
class DevicePackPromotionCheck:
    check_id: str
    label: str
    passed: bool
    evidence: str
    resolution: str


@dataclass(frozen=True, slots=True)
class DevicePackPromotionReview:
    schema_version: int
    pack_id: str
    pack_version: str
    draft_sha256: str
    checks: tuple[DevicePackPromotionCheck, ...]
    contribution_envelope_sha256s: tuple[str, ...]
    eligible_for_governed_review: bool
    status: str
    publication_authority: str
    production_registry_changed: bool
    runtime_promotion_supported: bool
    report_digest: str

    @property
    def passed_count(self) -> int:
        return sum(check.passed for check in self.checks)

    @property
    def blocker_count(self) -> int:
        return len(self.checks) - self.passed_count


@dataclass(frozen=True, slots=True)
class DevicePackPromotionReviewExport:
    output_path: Path
    sha256: str
    size_bytes: int


class DevicePackPromotionService:
    """Build a fail-closed release review; the running app cannot promote a Pack."""

    FORMAT = "romverse.device-pack-promotion-review"
    SCHEMA_VERSION = 1
    MAXIMUM_REVIEW_BYTES = 256 * 1024
    FACTUAL_SCOPES = frozenset({"identity", "variant", "factory-firmware", "partitions-avb"})
    EXPERT_SCOPES = frozenset({"flash-rollback-contract", "simulation", "physical-device-test"})

    def assess(
        self,
        revision: FoundryDraftRevision,
        inventory: DevicePackFoundryInventory,
        contributions: tuple[DevicePackContributionReport, ...],
    ) -> DevicePackPromotionReview:
        exact_revision = any(
            candidate.pack_id == revision.pack_id
            and candidate.version == revision.version
            and candidate.sha256 == revision.sha256
            and candidate.path == revision.path
            for candidate in inventory.revisions
        )
        conflicts = tuple(
            conflict
            for conflict in inventory.conflicts
            if revision.pack_id in conflict.pack_ids or revision.sha256 in conflict.revision_sha256s
        )
        lanes = {lane.lane_id: lane for lane in revision.lanes}
        accepted = tuple(
            report
            for report in contributions
            if report.verified
            and report.contributor_role in {"manufacturer", "qualified-expert"}
            and report.pack_id == revision.pack_id
            and report.pack_version == revision.version
            and report.draft_sha256 == revision.sha256
            and report.publication_authority == "none"
            and not report.production_registry_changed
            and report.review_required
        )
        factual_scopes = {scope for report in accepted for scope in report.evidence_scopes}
        expert_scopes = {
            scope
            for report in accepted
            if report.contributor_role == "qualified-expert"
            for scope in report.evidence_scopes
        }
        missing_factual_scopes = self.FACTUAL_SCOPES - factual_scopes
        missing_expert_scopes = self.EXPERT_SCOPES - expert_scopes
        source_dna_ready = bool(
            revision.source_bound
            and revision.device_dna_attached
            and revision.source_sha256
            and revision.device_dna_profile_digest
        )
        avb_ready = bool(
            revision.source_avb_attached
            and revision.partition_count > 0
            and _lane_evidenced(lanes, "partitions")
        )
        flash_ready = _lane_evidenced(lanes, "flash-contract")
        simulation_ready = bool(
            revision.simulation is not None
            and revision.simulation.successful
            and revision.simulation.operation_count > 0
            and revision.simulation.blocker_count == 0
            and revision.simulation.execution_authority == "none"
        )
        physical_ready = _lane_evidenced(lanes, "physical-test")
        checks = (
            DevicePackPromotionCheck(
                "exact-revision",
                "Exact immutable Foundry revision",
                exact_revision,
                (
                    f"Inventory contains {revision.pack_id} v{revision.version} at "
                    f"{revision.sha256[:16]}…."
                    if exact_revision
                    else "The requested revision is absent from the current strict Foundry inventory."
                ),
                "Reopen the unchanged canonical content-addressed draft from this workspace.",
            ),
            DevicePackPromotionCheck(
                "identity-conflicts",
                "No unresolved exact-identity conflict",
                not conflicts,
                (
                    "No other experimental Pack lineage claims this exact measured identity."
                    if not conflicts
                    else f"{len(conflicts)} unresolved Foundry identity conflict(s) include this revision."
                ),
                "Reconcile measured Device DNA, source and physical evidence; never choose by name alone.",
            ),
            DevicePackPromotionCheck(
                "source-device-dna",
                "Protected source and sealed Device DNA",
                source_dna_ready,
                (
                    f"Source {revision.source_sha256[:12]}… and sealed DNA "
                    f"{revision.device_dna_profile_digest[:12]}… are bound."
                    if source_dna_ready
                    else "The revision lacks an exact protected-source plus sealed-DNA binding."
                ),
                "Attach a genuine protected factory source and the current sealed Device DNA revision.",
            ),
            DevicePackPromotionCheck(
                "partitions-avb",
                "Measured partitions and OEM AVB topology",
                avb_ready,
                (
                    f"{revision.partition_count} source partition record(s) and OEM AVB evidence are attached."
                    if avb_ready
                    else "Measured source partitions or OEM AVB topology remain incomplete."
                ),
                "Verify the source partition inventory and OEM vbmeta topology from unchanged bytes.",
            ),
            DevicePackPromotionCheck(
                "flash-rollback-contract",
                "Exact flash, readback, rollback and recovery contract",
                flash_ready,
                (
                    "The Foundry flash/rollback lane is fully evidenced."
                    if flash_ready
                    else "The Foundry flash/rollback lane is not fully evidenced."
                ),
                "Define exact writes, readbacks, transitions, slots, AVB policy and stock recovery.",
            ),
            DevicePackPromotionCheck(
                "simulation",
                "Successful exact-bound Simulation Lab rehearsal",
                simulation_ready,
                (
                    f"Digital Twin {revision.simulation.receipt_digest[:12]}… passed "
                    f"{revision.simulation.operation_count} inert operation(s)."
                    if simulation_ready and revision.simulation is not None
                    else "No current successful source/DNA-bound, blocker-free rehearsal exists."
                ),
                "Resolve every Digital Twin blocker and rerun the unchanged exact plan.",
            ),
            DevicePackPromotionCheck(
                "factual-contribution",
                "Signed device and firmware evidence",
                not missing_factual_scopes,
                (
                    "Trusted manufacturer or qualified-expert contributions cover identity, "
                    "variant, firmware and partitions/AVB."
                    if not missing_factual_scopes
                    else "Signed factual evidence is missing for: "
                    + ", ".join(sorted(missing_factual_scopes))
                    + "."
                ),
                "Import exact-revision evidence signed by a trusted qualified expert or manufacturer.",
            ),
            DevicePackPromotionCheck(
                "expert-contribution",
                "Signed qualified-expert validation evidence",
                not missing_expert_scopes,
                (
                    "Trusted qualified-expert contributions cover flash/rollback, simulation "
                    "and physical testing."
                    if not missing_expert_scopes
                    else "Signed qualified-expert validation is missing for: "
                    + ", ".join(sorted(missing_expert_scopes))
                    + "."
                ),
                "Import exact-revision evidence signed by a trusted qualified expert.",
            ),
            DevicePackPromotionCheck(
                "physical-device-test",
                "Independent physical recovery and first-boot proof",
                physical_ready,
                (
                    "The physical-device lane is fully evidenced."
                    if physical_ready
                    else "Simulation evidence is not physical recovery or first-boot proof."
                ),
                "Complete and sign the exact real-device recovery, failure and first-boot matrix.",
            ),
        )
        eligible = all(check.passed for check in checks)
        partial = {
            "schema_version": self.SCHEMA_VERSION,
            "pack_id": revision.pack_id,
            "pack_version": revision.version,
            "draft_sha256": revision.sha256,
            "checks": [asdict(check) for check in checks],
            "contribution_envelope_sha256s": sorted(report.envelope_sha256 for report in accepted),
            "eligible_for_governed_review": eligible,
            "status": "eligible-for-governed-review" if eligible else "blocked",
            "publication_authority": "none",
            "production_registry_changed": False,
            "runtime_promotion_supported": False,
        }
        digest = hashlib.sha256(_canonical(partial)).hexdigest()
        return DevicePackPromotionReview(
            self.SCHEMA_VERSION,
            revision.pack_id,
            revision.version,
            revision.sha256,
            checks,
            tuple(partial["contribution_envelope_sha256s"]),
            eligible,
            str(partial["status"]),
            "none",
            False,
            False,
            digest,
        )

    def export(
        self,
        review: DevicePackPromotionReview,
        output_dir: Path,
        *,
        boundary: Path,
    ) -> DevicePackPromotionReviewExport:
        document = {
            "format": self.FORMAT,
            **asdict(review),
        }
        payload = _canonical(document) + b"\n"
        digest = hashlib.sha256(payload).hexdigest()
        safe_pack = _safe_name(review.pack_id)
        output = output_dir / f"{safe_pack}-{digest[:12]}.promotion-review.json"
        atomic_write_bytes(
            output,
            payload,
            boundary=boundary,
            maximum_bytes=self.MAXIMUM_REVIEW_BYTES,
        )
        return DevicePackPromotionReviewExport(output, digest, len(payload))


def _lane_evidenced(lanes: dict[str, object], lane_id: str) -> bool:
    lane = lanes.get(lane_id)
    return bool(lane is not None and getattr(lane, "state", None) is FoundryEvidenceState.EVIDENCED)


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
