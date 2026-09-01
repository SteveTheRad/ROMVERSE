from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from pathlib import Path

from romverse.ascension.assessment import AscensionAssessmentService
from romverse.ascension.binding import AscensionSourceBindingService
from romverse.ascension.models import AscensionMethod
from romverse.core.privacy import WorkspacePrivacy
from romverse.device.dna import CapabilityState, DeviceDnaStore
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.registry import DevicePackRegistry
from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    ensure_private_directory,
    read_json_object,
)
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore


@dataclass(frozen=True, slots=True)
class AscensionRouteRecord:
    """Evidence-bound automatic route decision with no execution authority."""

    schema_version: int
    project_id: str
    created_at: str
    state: str
    confidence: str
    candidate_method: AscensionMethod
    recommended_method: AscensionMethod | None
    ready_for_local_preparation: bool
    title: str
    reason: str
    patch_target: str
    evidence: tuple[str, ...]
    blocker_count: int
    source_original_sha256: str
    source_authority: str
    source_codename: str
    device_dna_digest: str
    device_dna_identity_state: str
    device_key: str
    device_name: str
    device_codename: str
    kernel_version: str
    execution_authority: str
    command_manifest: tuple[str, ...]
    bootloader_relock_allowed: bool
    phone_changed: bool
    record_digest: str


class AscensionRouteRecordService:
    """Resolve and persist one conservative root route for the current evidence."""

    FORMAT = "romverse.ascension-route-record"
    SCHEMA_VERSION = 2
    RECORD_NAME = "route-record.romverse"
    MAX_BYTES = 256 * 1024
    MAX_EVIDENCE = 64
    MAX_EVIDENCE_TEXT = 4096
    VALID_STATES = {"ready-local-only", "blocked", "unconfirmed"}
    VALID_CONFIDENCE = {"verified", "high", "unconfirmed"}

    def __init__(
        self,
        store: RomProjectStore,
        registry: DevicePackRegistry,
        assessment_service: AscensionAssessmentService | None = None,
    ) -> None:
        self.store = store
        self.registry = registry
        self.assessment_service = assessment_service or AscensionAssessmentService(
            store,
            registry,
        )

    def resolve(
        self,
        project_id: str,
        device: AndroidDevice | None = None,
        companion: object | None = None,
    ) -> AscensionRouteRecord:
        project = self.store.get(project_id)
        if project.original is None:
            raise ProjectError("Ascension route resolution requires a protected firmware source")

        binding = AscensionSourceBindingService(self.store, self.registry).resolve(project_id)
        recommendation = self.assessment_service.recommend(project_id, device, companion)
        report = self.assessment_service.assess(
            project_id,
            recommendation.method,
            device,
            companion,
        )
        blockers = tuple(gate for gate in report.gates if gate.state.value == "blocked")
        exact_device = (
            device
            if device is not None and device.state is DeviceState.DEVICE and bool(device.serial)
            else None
        )
        dna_confirmed = binding.device_dna_state is CapabilityState.SUPPORTED
        context_confirmed = bool(binding.confirmed and dna_confirmed and exact_device is not None)
        state = (
            "ready-local-only"
            if recommendation.ready and binding.confirmed
            else "blocked"
            if blockers
            else "unconfirmed"
        )
        confidence = (
            "verified"
            if recommendation.ready and context_confirmed
            else "high"
            if recommendation.ready and binding.confirmed
            else "unconfirmed"
        )
        evidence = tuple(
            dict.fromkeys(
                (
                    *binding.evidence,
                    *recommendation.evidence,
                    *(gate.detail for gate in blockers),
                )
            )
        )
        payload: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "project_id": project_id,
            "created_at": datetime.now(UTC).isoformat(),
            "state": state,
            "confidence": confidence,
            "candidate_method": recommendation.method.value,
            "recommended_method": (recommendation.method.value if recommendation.ready else None),
            "ready_for_local_preparation": recommendation.ready,
            "title": recommendation.title,
            "reason": recommendation.reason,
            "patch_target": report.patch_target,
            "evidence": evidence,
            "blocker_count": len(blockers),
            "source_original_sha256": project.original.sha256,
            "source_authority": binding.authority,
            "source_codename": binding.codename,
            "device_dna_digest": binding.device_dna_digest,
            "device_dna_identity_state": binding.device_dna_state.value,
            "device_key": (
                WorkspacePrivacy(self.store.workspace).pseudonym(exact_device.serial)
                if exact_device is not None
                else ""
            ),
            "device_name": exact_device.display_name if exact_device is not None else "",
            "device_codename": exact_device.codename if exact_device is not None else "",
            "kernel_version": exact_device.kernel_version if exact_device is not None else "",
            "execution_authority": "none",
            "command_manifest": (),
            "bootloader_relock_allowed": False,
            "phone_changed": False,
        }
        existing = self.load(project_id)
        if existing is not None and _semantic_payload(existing) == _semantic_payload(payload):
            return existing

        digest = _digest(payload)
        materialized = dict(payload)
        materialized["candidate_method"] = recommendation.method
        materialized["recommended_method"] = recommendation.method if recommendation.ready else None
        record = AscensionRouteRecord(**materialized, record_digest=digest)
        root = self.store.projects_root / project_id / "ascension" / "route"
        try:
            ensure_private_directory(root, boundary=self.store.workspace)
            atomic_write_json(
                root / self.RECORD_NAME,
                {
                    "format": self.FORMAT,
                    **asdict(record),
                    "candidate_method": record.candidate_method.value,
                    "recommended_method": (
                        record.recommended_method.value if record.recommended_method else None
                    ),
                },
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
        except LocalStoreError as exc:
            raise ProjectError("Ascension route evidence could not be stored safely") from exc
        return record

    def load(self, project_id: str) -> AscensionRouteRecord | None:
        path = self._path(project_id)
        try:
            data = read_json_object(
                path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            if (
                set(data) != {"format", *(field.name for field in fields(AscensionRouteRecord))}
                or data.pop("format") != self.FORMAT
            ):
                return None
            raw_evidence = data.get("evidence")
            raw_commands = data.get("command_manifest")
            if (
                not isinstance(raw_evidence, list)
                or len(raw_evidence) > self.MAX_EVIDENCE
                or any(
                    not _safe_text(item, self.MAX_EVIDENCE_TEXT, allow_empty=False)
                    for item in raw_evidence
                )
                or raw_commands != []
            ):
                return None
            data["candidate_method"] = AscensionMethod(str(data["candidate_method"]))
            recommended = data.get("recommended_method")
            data["recommended_method"] = (
                AscensionMethod(str(recommended)) if recommended is not None else None
            )
            data["evidence"] = tuple(raw_evidence)
            data["command_manifest"] = ()
            record = AscensionRouteRecord(**data)
        except (LocalStoreError, ValueError, TypeError, KeyError):
            return None

        project = self.store.get(project_id)
        dna = DeviceDnaStore(self.store).load(project_id)
        current_dna_digest = dna.profile_digest if dna is not None else ""
        unsigned = asdict(record)
        unsigned.pop("record_digest")
        unsigned["candidate_method"] = record.candidate_method.value
        unsigned["recommended_method"] = (
            record.recommended_method.value if record.recommended_method else None
        )
        if (
            project.original is None
            or record.schema_version != self.SCHEMA_VERSION
            or record.project_id != project_id
            or record.state not in self.VALID_STATES
            or record.confidence not in self.VALID_CONFIDENCE
            or not _valid_record_shape(record, self.MAX_EVIDENCE, self.MAX_EVIDENCE_TEXT)
            or record.source_original_sha256 != project.original.sha256
            or record.device_dna_digest != current_dna_digest
            or record.execution_authority != "none"
            or record.command_manifest
            or record.bootloader_relock_allowed
            or record.phone_changed
            or (record.ready_for_local_preparation and not record.patch_target)
            or record.ready_for_local_preparation != (record.recommended_method is not None)
            or (
                record.recommended_method is not None
                and record.recommended_method is not record.candidate_method
            )
            or record.record_digest != _digest(unsigned)
        ):
            return None
        return record

    def matches_device(
        self,
        record: AscensionRouteRecord,
        device: AndroidDevice | None,
    ) -> bool:
        if device is None or device.state is not DeviceState.DEVICE or not device.serial:
            return not record.device_key
        return bool(
            record.device_key
            and WorkspacePrivacy(self.store.workspace).pseudonym(device.serial) == record.device_key
            and device.codename.casefold() == record.device_codename.casefold()
            and device.kernel_version == record.kernel_version
        )

    def _path(self, project_id: str) -> Path:
        return self.store.projects_root / project_id / "ascension" / "route" / self.RECORD_NAME


def _semantic_payload(value: AscensionRouteRecord | dict[str, object]) -> dict[str, object]:
    payload = asdict(value) if isinstance(value, AscensionRouteRecord) else dict(value)
    payload.pop("created_at", None)
    payload.pop("record_digest", None)
    candidate = payload.get("candidate_method")
    recommended = payload.get("recommended_method")
    if isinstance(candidate, AscensionMethod):
        payload["candidate_method"] = candidate.value
    if isinstance(recommended, AscensionMethod):
        payload["recommended_method"] = recommended.value
    return payload


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _valid_record_shape(
    record: AscensionRouteRecord,
    maximum_evidence: int,
    maximum_evidence_text: int,
) -> bool:
    return bool(
        type(record.schema_version) is int
        and type(record.ready_for_local_preparation) is bool
        and type(record.blocker_count) is int
        and 0 <= record.blocker_count <= maximum_evidence
        and type(record.bootloader_relock_allowed) is bool
        and type(record.phone_changed) is bool
        and len(record.evidence) <= maximum_evidence
        and all(
            _safe_text(item, maximum_evidence_text, allow_empty=False) for item in record.evidence
        )
        and all(
            _safe_text(value, limit, allow_empty=allow_empty)
            for value, limit, allow_empty in (
                (record.project_id, 160, False),
                (record.created_at, 80, False),
                (record.state, 40, False),
                (record.confidence, 40, False),
                (record.title, 512, False),
                (record.reason, 4096, False),
                (record.patch_target, 512, True),
                (record.source_authority, 80, False),
                (record.source_codename, 160, True),
                (record.device_dna_identity_state, 40, False),
                (record.device_name, 256, True),
                (record.device_codename, 160, True),
                (record.kernel_version, 256, True),
                (record.execution_authority, 40, False),
            )
        )
        and _hex_text(record.source_original_sha256, 64)
        and (not record.device_dna_digest or _hex_text(record.device_dna_digest, 64))
        and (not record.device_key or _hex_text(record.device_key, 20))
        and _hex_text(record.record_digest, 64)
    )


def _safe_text(value: object, maximum: int, *, allow_empty: bool) -> bool:
    return bool(
        isinstance(value, str)
        and (allow_empty or value)
        and len(value) <= maximum
        and all(ord(character) >= 32 or character in "\n\t" for character in value)
    )


def _hex_text(value: object, length: int) -> bool:
    return bool(isinstance(value, str) and re.fullmatch(rf"[0-9a-f]{{{length}}}", value))
