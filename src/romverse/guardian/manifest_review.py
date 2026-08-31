from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from romverse.device.models import AndroidDevice
from romverse.device_packs.models import AvbPolicyAuthority, DeviceWriteTransport
from romverse.device_packs.registry import DevicePackRegistry
from romverse.guardian.artifact_binding import (
    GuardianArtifactBindingReceipt,
    GuardianArtifactBindingService,
    GuardianBoundArtifact,
)
from romverse.guardian.flash_handoff import (
    FlashMode,
    GuardianFlashHandoffService,
)
from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    ensure_private_directory,
    read_json_object,
)
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.rom.readiness import BuildReadinessReport


class ManifestReviewState(StrEnum):
    PASS = "pass"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class GuardianManifestCheck:
    check_id: str
    label: str
    state: ManifestReviewState
    evidence: str
    recommendation: str


@dataclass(frozen=True, slots=True)
class GuardianManifestReview:
    """Command-free final review packet; it is never device execution authority."""

    schema_version: int
    manifest_id: str
    created_at: str
    project_id: str
    handoff_digest: str
    readiness_evidence_digest: str
    source_sha256: str
    device_key: str
    device_name: str
    model: str
    codename: str
    mode: FlashMode
    preserve_user_data: bool
    wipe_user_data: bool
    device_pack_id: str
    device_pack_version: str
    device_pack_sha256: str
    checks: tuple[GuardianManifestCheck, ...]
    partition_writes: tuple[GuardianBoundArtifact, ...]
    blockers: tuple[str, ...]
    review_status: str
    final_consent_available: bool
    execution_authority: str
    phone_changed: bool
    bootloader_relock_allowed: bool
    command_manifest: tuple[tuple[str, ...], ...]
    artifact_binding_digest: str
    manifest_digest: str


class GuardianManifestReviewService:
    """Compile the real post-handoff review without guessing partition write authority."""

    FORMAT = "romverse.guardian-manifest-review"
    SCHEMA_VERSION = 2
    LATEST_NAME = "manifest-review.romverse"
    MAX_BYTES = 128 * 1024
    MAX_CHECKS = 16
    MAX_BLOCKERS = 8

    def __init__(self, store: RomProjectStore, registry: DevicePackRegistry) -> None:
        self.store = store
        self.registry = registry

    def compile(
        self,
        project_id: str,
        report: BuildReadinessReport,
        device: AndroidDevice,
        binding: GuardianArtifactBindingReceipt | None = None,
        binding_error: str = "",
    ) -> GuardianManifestReview:
        project = self.store.get(project_id)
        handoffs = GuardianFlashHandoffService(self.store)
        handoff = handoffs.load(project_id)
        if handoff is None or not handoffs.matches_current(project_id, handoff, device, report):
            raise ProjectError(
                "Prepare a fresh current Guardian keep-data or wipe-data handoff first"
            )
        pack = next(
            (
                candidate
                for candidate in self.registry.packs
                if candidate.pack_id == project.device_pack_id
            ),
            None,
        )
        pack_id = pack.pack_id if pack is not None else project.device_pack_id
        pack_version = pack.version if pack is not None else "unconfirmed"
        pack_sha256 = pack.sha256 if pack is not None else ""
        contract_blocker = _write_contract_blocker(pack, project.original.sha256)
        contract_ready = _write_contract_ready(pack, project.original.sha256)
        binding_ready = bool(
            binding is not None
            and contract_ready
            and _binding_matches(binding, handoff, pack, project.original.sha256)
        )
        if binding is not None:
            GuardianArtifactBindingService(self.store, self.registry).validate(binding)
            if not binding_ready:
                raise ProjectError(
                    "Guardian artifact binding does not match the current handoff and Device Pack"
                )
        binding_problem = _bounded_problem(binding_error) if binding_error else ""
        contract_evidence = _write_contract_evidence(pack, project.original.sha256)
        binding_evidence = (
            _binding_evidence(binding)
            if binding_ready and binding is not None
            else binding_problem
            or "No current immutable artifact-binding receipt is available for every declared write."
        )
        checks = (
            GuardianManifestCheck(
                "readiness",
                "Current readiness evidence",
                ManifestReviewState.PASS,
                f"Every required card is green • evidence {handoff.readiness_evidence_digest[:16]}…",
                "Re-run Guardian readiness whenever project evidence changes.",
            ),
            GuardianManifestCheck(
                "exact-device",
                "Exact connected phone",
                ManifestReviewState.PASS,
                f"{handoff.device_name} • {handoff.model} • {handoff.codename}",
                "Keep this exact authorized phone connected for any later final review.",
            ),
            GuardianManifestCheck(
                "data-choice",
                "User-data handling",
                ManifestReviewState.PASS,
                handoff.mode.display_name,
                "Changing this choice requires a fresh Guardian handoff.",
            ),
            GuardianManifestCheck(
                "bootloader-relock",
                "Bootloader relock prohibition",
                ManifestReviewState.PASS,
                "Relock allowed: NEVER • relock commands: NONE",
                "ROMVERSE will never generate or offer bootloader relocking.",
            ),
            GuardianManifestCheck(
                "partition-write-contract",
                "Exact partition-write contract",
                ManifestReviewState.PASS if contract_ready else ManifestReviewState.BLOCKED,
                contract_evidence,
                "Attach a signed, exact-build, physically recovery-tested Device Pack write contract. ROMVERSE cannot infer partition writes from filenames or a successful local build.",
            ),
            GuardianManifestCheck(
                "current-artifact-binding",
                "Current immutable artifact binding",
                ManifestReviewState.PASS if binding_ready else ManifestReviewState.BLOCKED,
                binding_evidence,
                "Rebuild or re-sign the exact current candidate, then let Guardian rehash every declared image in the background. No phone write occurs.",
            ),
            GuardianManifestCheck(
                "execution-manifest",
                "Executable command manifest and final consent",
                ManifestReviewState.BLOCKED,
                "No executable command manifest, final-consent authority, or device-write path is enabled.",
                "A later Guardian milestone must compile and independently verify exact commands, preconditions, recovery actions, and post-write checks before final consent can become available.",
            ),
        )
        if binding_ready:
            blockers = (
                "Exact current image hashes are bound for review, but no executable command manifest or final-consent authority exists.",
            )
            review_status = "artifact-bound-review-only"
        elif contract_ready:
            blockers = (
                binding_evidence,
                "No partition write is authorized and final device-write consent remains unavailable.",
            )
            review_status = "blocked-missing-current-artifact-binding"
        else:
            blockers = (
                contract_blocker,
                "No exact partition writes or commands are present, so final device-write consent remains unavailable.",
            )
            review_status = "blocked-missing-exact-write-contract"
        bound_writes = binding.writes if binding_ready and binding is not None else ()
        payload: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "manifest_id": uuid4().hex,
            "created_at": datetime.now(UTC).isoformat(),
            "project_id": project_id,
            "handoff_digest": handoff.handoff_digest,
            "readiness_evidence_digest": handoff.readiness_evidence_digest,
            "source_sha256": handoff.source_sha256,
            "device_key": handoff.device_key,
            "device_name": handoff.device_name,
            "model": handoff.model,
            "codename": handoff.codename,
            "mode": handoff.mode,
            "preserve_user_data": handoff.preserve_user_data,
            "wipe_user_data": handoff.wipe_user_data,
            "device_pack_id": pack_id,
            "device_pack_version": pack_version,
            "device_pack_sha256": pack_sha256,
            "checks": [asdict(check) for check in checks],
            "partition_writes": [asdict(item) for item in bound_writes],
            "blockers": blockers,
            "review_status": review_status,
            "final_consent_available": False,
            "execution_authority": "none",
            "phone_changed": False,
            "bootloader_relock_allowed": False,
            "command_manifest": (),
            "artifact_binding_digest": (
                binding.binding_digest if binding_ready and binding is not None else ""
            ),
        }
        manifest = GuardianManifestReview(
            **{
                key: value
                for key, value in payload.items()
                if key not in {"checks", "partition_writes"}
            },
            checks=checks,
            partition_writes=bound_writes,
            manifest_digest=_digest(payload),
        )
        self.validate(manifest)
        self._write(manifest)
        return manifest

    def load(self, project_id: str) -> GuardianManifestReview | None:
        path = self._root(project_id) / self.LATEST_NAME
        try:
            data = read_json_object(
                path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            schema_version = data.get("schema_version")
            expected_fields = {field.name for field in fields(GuardianManifestReview)}
            if schema_version == 1:
                expected_fields.remove("artifact_binding_digest")
            elif schema_version != self.SCHEMA_VERSION:
                return None
            if (
                set(data) != {"format", *expected_fields}
                or data.pop("format") != self.FORMAT
                or not _valid_raw_manifest(data, schema_version)
            ):
                return None
            raw_checks = data.pop("checks")
            raw_writes = data.pop("partition_writes")
            raw_blockers = data.pop("blockers")
            raw_commands = data.pop("command_manifest")
            check_fields = {field.name for field in fields(GuardianManifestCheck)}
            if (
                not isinstance(raw_checks, list)
                or not 1 <= len(raw_checks) <= self.MAX_CHECKS
                or any(
                    not isinstance(item, dict) or set(item) != check_fields for item in raw_checks
                )
                or not isinstance(raw_writes, list)
                or len(raw_writes) > GuardianArtifactBindingService.MAX_WRITES
                or not isinstance(raw_blockers, list)
                or not 1 <= len(raw_blockers) <= self.MAX_BLOCKERS
                or raw_commands != []
            ):
                return None
            checks = tuple(
                GuardianManifestCheck(
                    str(item["check_id"]),
                    str(item["label"]),
                    ManifestReviewState(str(item["state"])),
                    str(item["evidence"]),
                    str(item["recommendation"]),
                )
                for item in raw_checks
            )
            if schema_version == 1:
                if raw_writes:
                    return None
                writes: tuple[GuardianBoundArtifact, ...] = ()
                data["artifact_binding_digest"] = ""
            else:
                write_fields = {field.name for field in fields(GuardianBoundArtifact)}
                if any(
                    not isinstance(item, dict) or set(item) != write_fields for item in raw_writes
                ):
                    return None
                writes = tuple(
                    GuardianBoundArtifact(
                        **{
                            **item,
                            "transport": DeviceWriteTransport(str(item["transport"])),
                        }
                    )
                    for item in raw_writes
                )
            data["mode"] = FlashMode(str(data["mode"]))
            manifest = GuardianManifestReview(
                **data,
                checks=checks,
                partition_writes=writes,
                blockers=tuple(str(item) for item in raw_blockers),
                command_manifest=(),
            )
            self.validate(manifest)
            project = self.store.get(project_id)
            pack = next(
                (
                    candidate
                    for candidate in self.registry.packs
                    if candidate.pack_id == manifest.device_pack_id
                ),
                None,
            )
            if (
                manifest.project_id != project_id
                or project.original is None
                or manifest.source_sha256 != project.original.sha256
                or manifest.device_pack_id != project.device_pack_id
                or (
                    pack is not None
                    and (
                        manifest.device_pack_version != pack.version
                        or manifest.device_pack_sha256 != pack.sha256
                    )
                )
                or not _loaded_review_matches_pack(
                    manifest,
                    pack,
                    project.original.sha256,
                    self._root(project_id),
                )
            ):
                return None
            return manifest
        except (LocalStoreError, OSError, TypeError, ValueError, KeyError, ProjectError):
            return None

    def matches_current(
        self,
        manifest: GuardianManifestReview,
        report: BuildReadinessReport,
        device: AndroidDevice,
    ) -> bool:
        handoff = GuardianFlashHandoffService(self.store).load(manifest.project_id)
        return bool(
            handoff is not None
            and GuardianFlashHandoffService(self.store).matches_current(
                manifest.project_id,
                handoff,
                device,
                report,
            )
            and manifest.handoff_digest == handoff.handoff_digest
            and manifest.readiness_evidence_digest == handoff.readiness_evidence_digest
            and manifest.source_sha256 == handoff.source_sha256
            and manifest.device_key == handoff.device_key
            and manifest.mode is handoff.mode
        )

    def validate(self, manifest: GuardianManifestReview) -> None:
        payload = asdict(manifest)
        expected = str(payload.pop("manifest_digest", ""))
        if manifest.schema_version == 1:
            payload.pop("artifact_binding_digest", None)
            self._validate_legacy(manifest, payload, expected)
            return
        check_states = {check.check_id: check.state for check in manifest.checks}
        contract_ready = manifest.review_status != "blocked-missing-exact-write-contract"
        binding_ready = bool(manifest.partition_writes)
        expected_status = (
            "artifact-bound-review-only"
            if binding_ready
            else "blocked-missing-current-artifact-binding"
            if contract_ready
            else "blocked-missing-exact-write-contract"
        )
        if (
            manifest.schema_version != self.SCHEMA_VERSION
            or not re.fullmatch(r"[0-9a-f]{32}", manifest.manifest_id)
            or not _aware_timestamp(manifest.created_at)
            or not _clean_text(manifest.project_id, 128)
            or not re.fullmatch(r"[0-9a-f]{64}", manifest.handoff_digest)
            or not re.fullmatch(r"[0-9a-f]{64}", manifest.readiness_evidence_digest)
            or not re.fullmatch(r"[0-9a-f]{64}", manifest.source_sha256)
            or not re.fullmatch(r"[0-9a-f]{20}", manifest.device_key)
            or not _clean_text(manifest.device_name, 120)
            or not _clean_text(manifest.model, 120)
            or not _clean_text(manifest.codename, 80)
            or not _clean_text(manifest.device_pack_id, 128)
            or not _clean_text(manifest.device_pack_version, 80)
            or (
                bool(manifest.device_pack_sha256)
                and not re.fullmatch(r"[0-9a-f]{64}", manifest.device_pack_sha256)
            )
            or not 1 <= len(manifest.checks) <= self.MAX_CHECKS
            or len({check.check_id for check in manifest.checks}) != len(manifest.checks)
            or any(not _valid_check(check) for check in manifest.checks)
            or check_states
            != {
                "readiness": ManifestReviewState.PASS,
                "exact-device": ManifestReviewState.PASS,
                "data-choice": ManifestReviewState.PASS,
                "bootloader-relock": ManifestReviewState.PASS,
                "partition-write-contract": (
                    ManifestReviewState.PASS if contract_ready else ManifestReviewState.BLOCKED
                ),
                "current-artifact-binding": (
                    ManifestReviewState.PASS if binding_ready else ManifestReviewState.BLOCKED
                ),
                "execution-manifest": ManifestReviewState.BLOCKED,
            }
            or len(manifest.partition_writes) > GuardianArtifactBindingService.MAX_WRITES
            or any(
                not GuardianArtifactBindingService._valid_write(item)
                for item in manifest.partition_writes
            )
            or (
                binding_ready
                and not re.fullmatch(r"[0-9a-f]{64}", manifest.artifact_binding_digest)
            )
            or (not binding_ready and bool(manifest.artifact_binding_digest))
            or not 1 <= len(manifest.blockers) <= self.MAX_BLOCKERS
            or any(not _clean_text(item, 600) for item in manifest.blockers)
            or manifest.review_status != expected_status
            or manifest.final_consent_available
            or manifest.execution_authority != "none"
            or manifest.phone_changed
            or manifest.bootloader_relock_allowed
            or manifest.command_manifest
            or manifest.preserve_user_data == manifest.wipe_user_data
            or manifest.preserve_user_data != (manifest.mode is FlashMode.DIRTY_KEEP_DATA)
            or expected != _digest(payload)
        ):
            raise ProjectError("Guardian manifest review failed integrity or safety validation")

    def _validate_legacy(
        self,
        manifest: GuardianManifestReview,
        payload: dict[str, object],
        expected: str,
    ) -> None:
        check_states = {check.check_id: check.state for check in manifest.checks}
        if (
            not _valid_manifest_common(manifest)
            or manifest.partition_writes
            or manifest.artifact_binding_digest
            or check_states
            != {
                "readiness": ManifestReviewState.PASS,
                "exact-device": ManifestReviewState.PASS,
                "data-choice": ManifestReviewState.PASS,
                "bootloader-relock": ManifestReviewState.PASS,
                "partition-write-contract": ManifestReviewState.BLOCKED,
            }
            or manifest.review_status != "blocked-missing-exact-write-contract"
            or manifest.final_consent_available
            or manifest.execution_authority != "none"
            or manifest.phone_changed
            or manifest.bootloader_relock_allowed
            or manifest.command_manifest
            or manifest.preserve_user_data == manifest.wipe_user_data
            or manifest.preserve_user_data != (manifest.mode is FlashMode.DIRTY_KEEP_DATA)
            or expected != _digest(payload)
        ):
            raise ProjectError("Legacy Guardian manifest review failed safety validation")

    def _write(self, manifest: GuardianManifestReview) -> None:
        root = self._root(manifest.project_id)
        ensure_private_directory(root, boundary=self.store.workspace)
        document = {"format": self.FORMAT, **asdict(manifest)}
        atomic_write_json(
            root / f"manifest-review-{manifest.manifest_id[:12]}.romverse",
            document,
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_BYTES,
        )
        atomic_write_json(
            root / self.LATEST_NAME,
            document,
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_BYTES,
        )

    def _root(self, project_id: str):
        self.store.get(project_id)
        return self.store.projects_root / project_id / "guardian"


def _write_contract_blocker(pack, source_sha256: str) -> str:
    if pack is None:
        return "No exact Device Pack is bound to this project."
    contract = pack.build_contract
    if contract is None:
        return "The selected Device Pack has no source-bound build or partition-write contract."
    if contract.source.archive_sha256 != source_sha256:
        return "The Device Pack contract belongs to a different protected firmware source."
    policy = contract.avb_execution_policy
    if policy is None:
        return "The exact build contract has no AVB execution policy or partition-write authority."
    if policy.authority is not AvbPolicyAuthority.FLASH_VALIDATED:
        return "The current Device Pack AVB policy is reference-only, not flash-validated write authority."
    write_contract = contract.partition_write_contract
    if write_contract is None:
        return "The exact Device Pack has no explicit signed partition-to-artifact write contract."
    return (
        f"Device Pack write contract {write_contract.contract_id} declares "
        f"{len(write_contract.writes)} image write(s), but Guardian has not bound each image "
        "to the current immutable build receipt; no partition writes or commands are available."
    )


def _write_contract_ready(pack, source_sha256: str) -> bool:
    if pack is None or pack.build_contract is None:
        return False
    contract = pack.build_contract
    policy = contract.avb_execution_policy
    write_contract = contract.partition_write_contract
    return bool(
        contract.source.archive_sha256 == source_sha256
        and policy is not None
        and policy.authority is AvbPolicyAuthority.FLASH_VALIDATED
        and write_contract is not None
        and write_contract.source_build_id == contract.source.build_id
        and write_contract.attestation_sha256 == policy.attestation_sha256
        and not write_contract.bootloader_relock_allowed
        and write_contract.writes
    )


def _write_contract_evidence(pack, source_sha256: str) -> str:
    if not _write_contract_ready(pack, source_sha256):
        return _write_contract_blocker(pack, source_sha256)
    write_contract = pack.build_contract.partition_write_contract
    return (
        f"Write contract {write_contract.contract_id} binds "
        f"{len(write_contract.writes)} ordered image write(s) to the exact signed "
        "physical-attestation digest; relocking is prohibited"
    )


def _binding_evidence(binding: GuardianArtifactBindingReceipt) -> str:
    return (
        f"ROMVERSE rehashed {len(binding.writes)} current image(s); binding "
        f"{binding.binding_digest[:20]}… is tied to this handoff and data mode"
    )


def _binding_matches(binding, handoff, pack, source_sha256: str) -> bool:
    if pack is None or pack.build_contract is None:
        return False
    write_contract = pack.build_contract.partition_write_contract
    return bool(
        write_contract is not None
        and binding.project_id == handoff.project_id
        and binding.handoff_digest == handoff.handoff_digest
        and binding.device_key == handoff.device_key
        and binding.mode is handoff.mode
        and binding.pack_id == pack.pack_id
        and binding.pack_version == pack.version
        and binding.pack_sha256 == pack.sha256
        and binding.build_contract_id == pack.build_contract.contract_id
        and binding.build_contract_version == pack.build_contract.version
        and binding.write_contract_id == write_contract.contract_id
        and binding.write_contract_version == write_contract.version
        and binding.write_attestation_sha256 == write_contract.attestation_sha256
        and binding.source_build_id == pack.build_contract.source.build_id
        and binding.source_archive_sha256 == source_sha256
        and tuple(
            (item.partition, item.artifact_name, item.transport, item.target_slot)
            for item in binding.writes
        )
        == tuple(
            (item.partition, item.artifact, item.transport, item.target_slot)
            for item in write_contract.writes
        )
    )


def _bounded_problem(value: str) -> str:
    cleaned = " ".join(str(value).replace("\x00", " ").split())
    return cleaned[:600] or "Guardian could not create the current artifact binding."


def _loaded_review_matches_pack(manifest, pack, source_sha256: str, root) -> bool:
    contract_ready = _write_contract_ready(pack, source_sha256)
    checks = {check.check_id: check for check in manifest.checks}
    if manifest.schema_version == 1:
        blocker = _write_contract_blocker(pack, source_sha256)
        return bool(
            manifest.blockers[0] == blocker
            and next(
                check.evidence
                for check in manifest.checks
                if check.check_id == "partition-write-contract"
            )
            == blocker
        )
    if manifest.review_status == "blocked-missing-exact-write-contract":
        return bool(
            not contract_ready
            and checks["partition-write-contract"].evidence
            == _write_contract_evidence(pack, source_sha256)
        )
    if not contract_ready:
        return False
    if checks["partition-write-contract"].evidence != _write_contract_evidence(pack, source_sha256):
        return False
    if not manifest.partition_writes:
        return manifest.review_status == "blocked-missing-current-artifact-binding"
    try:
        document = read_json_object(
            root / GuardianArtifactBindingService.LATEST_NAME,
            boundary=root.parent.parent.parent,
            maximum_bytes=GuardianArtifactBindingService.MAX_BYTES,
        )
    except (LocalStoreError, OSError):
        return False
    if not bool(
        document.get("format") == GuardianArtifactBindingService.FORMAT
        and document.get("project_id") == manifest.project_id
        and document.get("handoff_digest") == manifest.handoff_digest
        and document.get("binding_digest") == manifest.artifact_binding_digest
        and document.get("writes") == [asdict(item) for item in manifest.partition_writes]
    ):
        return False
    return checks["current-artifact-binding"].evidence == (
        f"ROMVERSE rehashed {len(manifest.partition_writes)} current image(s); binding "
        f"{manifest.artifact_binding_digest[:20]}… is tied to this handoff and data mode"
    )


def _valid_check(check: GuardianManifestCheck) -> bool:
    return bool(
        re.fullmatch(r"[a-z0-9-]{2,48}", check.check_id)
        and _clean_text(check.label, 120)
        and _clean_text(check.evidence, 600)
        and _clean_text(check.recommendation, 800)
    )


def _valid_manifest_common(manifest: GuardianManifestReview) -> bool:
    return bool(
        re.fullmatch(r"[0-9a-f]{32}", manifest.manifest_id)
        and _aware_timestamp(manifest.created_at)
        and _clean_text(manifest.project_id, 128)
        and re.fullmatch(r"[0-9a-f]{64}", manifest.handoff_digest)
        and re.fullmatch(r"[0-9a-f]{64}", manifest.readiness_evidence_digest)
        and re.fullmatch(r"[0-9a-f]{64}", manifest.source_sha256)
        and re.fullmatch(r"[0-9a-f]{20}", manifest.device_key)
        and _clean_text(manifest.device_name, 120)
        and _clean_text(manifest.model, 120)
        and _clean_text(manifest.codename, 80)
        and _clean_text(manifest.device_pack_id, 128)
        and _clean_text(manifest.device_pack_version, 80)
        and (
            not manifest.device_pack_sha256
            or bool(re.fullmatch(r"[0-9a-f]{64}", manifest.device_pack_sha256))
        )
        and 1 <= len(manifest.checks) <= GuardianManifestReviewService.MAX_CHECKS
        and len({check.check_id for check in manifest.checks}) == len(manifest.checks)
        and all(_valid_check(check) for check in manifest.checks)
        and 1 <= len(manifest.blockers) <= GuardianManifestReviewService.MAX_BLOCKERS
        and all(_clean_text(item, 600) for item in manifest.blockers)
    )


def _valid_raw_manifest(data: dict[str, object], schema_version: object) -> bool:
    string_fields = (
        "manifest_id",
        "created_at",
        "project_id",
        "handoff_digest",
        "readiness_evidence_digest",
        "source_sha256",
        "device_key",
        "device_name",
        "model",
        "codename",
        "mode",
        "device_pack_id",
        "device_pack_version",
        "device_pack_sha256",
        "review_status",
        "execution_authority",
        "manifest_digest",
    )
    if schema_version == GuardianManifestReviewService.SCHEMA_VERSION:
        string_fields += ("artifact_binding_digest",)
    bool_fields = (
        "preserve_user_data",
        "wipe_user_data",
        "final_consent_available",
        "phone_changed",
        "bootloader_relock_allowed",
    )
    raw_checks = data.get("checks")
    return bool(
        type(schema_version) is int
        and all(type(data.get(name)) is str for name in string_fields)
        and all(type(data.get(name)) is bool for name in bool_fields)
        and isinstance(raw_checks, list)
        and all(
            isinstance(item, dict)
            and type(item.get("check_id")) is str
            and type(item.get("label")) is str
            and type(item.get("state")) is str
            and type(item.get("evidence")) is str
            and type(item.get("recommendation")) is str
            for item in raw_checks
        )
        and isinstance(data.get("partition_writes"), list)
        and isinstance(data.get("blockers"), list)
        and all(type(item) is str for item in data["blockers"])
        and isinstance(data.get("command_manifest"), list)
    )


def _clean_text(value: object, maximum: int) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= maximum and "\x00" not in value


def _aware_timestamp(value: str) -> bool:
    try:
        return datetime.fromisoformat(value).tzinfo is not None
    except ValueError:
        return False


def _digest(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
