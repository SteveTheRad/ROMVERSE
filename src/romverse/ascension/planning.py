from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from romverse.ascension.build_handoff import RootRomBuildHandoffService
from romverse.ascension.evidence import AscensionEvidenceService
from romverse.ascension.models import AscensionMethod
from romverse.ascension.preparation import RootPatchPreparationService
from romverse.backup.handoff import BackupHandoffService
from romverse.core.privacy import WorkspacePrivacy
from romverse.device.dna import CapabilityState, DeviceDnaService, DeviceDnaStore
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
from romverse.rom.recovery_evidence import RecoveryEvidenceService


@dataclass(frozen=True, slots=True)
class AscensionRootPlan:
    schema_version: int
    plan_id: str
    project_id: str
    method: AscensionMethod
    created_at: str
    source_original_sha256: str
    device_dna_digest: str
    device_dna_identity_state: str
    device_key: str
    device_name: str
    device_codename: str
    target_partition: str
    pristine_image_sha256: str
    patched_image_sha256: str
    patched_receipt_digest: str
    build_handoff_digest: str
    root_image_artifact_path: str
    root_image_artifact_sha256: str
    manager_tag: str
    manager_sha256: str
    rollback_record_digest: str
    stock_recovery_sha256: str
    external_backup_verified: bool
    backup_handoff_ready: bool
    backup_evidence_kind: str
    execution_authority: str
    command_manifest: tuple[str, ...]
    bootloader_relock_allowed: bool
    phone_changed: bool
    plan_digest: str


class AscensionRootPlanService:
    """Create a review artifact for root installation without authorizing a write."""

    FORMAT = "romverse.ascension-root-plan"
    SCHEMA_VERSION = 4
    RECEIPT_NAME = "root-plan.romverse"
    MAX_BYTES = 256 * 1024

    def __init__(self, store: RomProjectStore) -> None:
        self.store = store

    def create(
        self,
        project_id: str,
        method: AscensionMethod,
        device: AndroidDevice,
    ) -> AscensionRootPlan:
        project = self.store.get(project_id)
        if project.original is None:
            raise ProjectError("Ascension root planning requires a protected firmware source")
        if device.state is not DeviceState.DEVICE or not device.serial or not device.codename:
            raise ProjectError("Ascension root planning requires one authorized exact phone")
        dna = DeviceDnaStore(self.store).load(project_id)
        if dna is None:
            dna = DeviceDnaService(self.store, DevicePackRegistry(())).refresh(
                project_id,
                device,
            )
        identity_capability = dna.capability("device_identity")
        dna_codename = dna.fact("identity.codename")
        if (
            identity_capability is None
            or identity_capability.state is not CapabilityState.SUPPORTED
            or dna_codename is None
            or not dna_codename.confirmed
            or dna_codename.value.casefold() != device.codename.casefold()
            or dna.bootloader_relock_permitted
        ):
            raise ProjectError(
                "Ascension root planning requires supported Device DNA bound to this exact phone"
            )
        capsule_service = RootPatchPreparationService(self.store)
        capsule = capsule_service.load(project_id, method)
        patched = capsule_service.load_patched(project_id, method)
        rollback = AscensionEvidenceService(self.store).load(project_id)
        build_handoff = RootRomBuildHandoffService(self.store).load(project_id, method)
        if capsule is None or patched is None or rollback is None or build_handoff is None:
            raise ProjectError(
                "Integrate and seal the verified rooted ROM build input before Guardian planning"
            )
        partition = Path(rollback.patch_target.source_relative_path).stem.casefold()
        if partition not in {"boot", "init_boot", "recovery", "vendor_boot"}:
            raise ProjectError("Ascension patch target is not a recognized boot partition")
        if method is AscensionMethod.KERNELSU_LKM and partition not in {"boot", "init_boot"}:
            raise ProjectError("KernelSU LKM requires an exact boot or init_boot target")
        recovery = RecoveryEvidenceService(self.store).assess(project_id)
        cloud_backup = BackupHandoffService(self.store).load(project_id, device)
        backup_handoff_ready = recovery.external_backup_ready or cloud_backup is not None
        backup_evidence_kind = (
            "verified-local-file"
            if recovery.external_backup_ready
            else "user-confirmed-cloud"
            if cloud_backup is not None
            else "none"
        )
        payload: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "plan_id": uuid4().hex,
            "project_id": project_id,
            "method": method.value,
            "created_at": datetime.now(UTC).isoformat(),
            "source_original_sha256": project.original.sha256,
            "device_dna_digest": dna.profile_digest,
            "device_dna_identity_state": identity_capability.state.value,
            "device_key": WorkspacePrivacy(self.store.workspace).pseudonym(device.serial),
            "device_name": device.display_name,
            "device_codename": device.codename,
            "target_partition": partition,
            "pristine_image_sha256": capsule.input_image_sha256,
            "patched_image_sha256": patched.patched_image_sha256,
            "patched_receipt_digest": patched.receipt_digest,
            "build_handoff_digest": build_handoff.handoff_digest,
            "root_image_artifact_path": build_handoff.artifact_relative_path,
            "root_image_artifact_sha256": build_handoff.artifact_sha256,
            "manager_tag": capsule.manager_tag,
            "manager_sha256": capsule.manager_sha256,
            "rollback_record_digest": rollback.record_digest,
            "stock_recovery_sha256": (
                rollback.stock_recovery.sha256
                if rollback.stock_recovery is not None
                else project.original.sha256
            ),
            "external_backup_verified": recovery.external_backup_ready,
            "backup_handoff_ready": backup_handoff_ready,
            "backup_evidence_kind": backup_evidence_kind,
            "execution_authority": "guardian-review-only",
            "command_manifest": (),
            "bootloader_relock_allowed": False,
            "phone_changed": False,
        }
        digest = _digest(payload)
        materialized = dict(payload)
        materialized["method"] = method
        plan = AscensionRootPlan(**materialized, plan_digest=digest)
        root = self.store.projects_root / project_id / "ascension" / "plan"
        try:
            ensure_private_directory(root, boundary=self.store.workspace)
            atomic_write_json(
                root / self.RECEIPT_NAME,
                {"format": self.FORMAT, **asdict(plan), "method": method.value},
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
        except LocalStoreError as exc:
            raise ProjectError("Ascension root-plan evidence could not be stored safely") from exc
        return plan

    def load(self, project_id: str, method: AscensionMethod) -> AscensionRootPlan | None:
        path = self.store.projects_root / project_id / "ascension" / "plan" / self.RECEIPT_NAME
        try:
            data = read_json_object(
                path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            if (
                set(data) != {"format", *(field.name for field in fields(AscensionRootPlan))}
                or data.pop("format") != self.FORMAT
                or data.get("command_manifest") != []
            ):
                return None
            data["method"] = AscensionMethod(str(data["method"]))
            data["command_manifest"] = ()
            plan = AscensionRootPlan(**data)
        except (LocalStoreError, ValueError, TypeError, KeyError):
            return None
        project = self.store.get(project_id)
        dna = DeviceDnaStore(self.store).load(project_id)
        capsule_service = RootPatchPreparationService(self.store)
        capsule = capsule_service.load(project_id, method)
        patched = capsule_service.load_patched(project_id, method)
        rollback = AscensionEvidenceService(self.store).load(project_id)
        build_handoff = RootRomBuildHandoffService(self.store).load(project_id, method)
        recovery = RecoveryEvidenceService(self.store).assess(project_id)
        cloud_backup = BackupHandoffService(self.store).load(project_id)
        cloud_backup_ready = bool(
            cloud_backup is not None
            and cloud_backup.device_pseudonym == plan.device_key
            and cloud_backup.codename.casefold() == plan.device_codename.casefold()
            and cloud_backup.device_name.casefold() == plan.device_name.casefold()
        )
        backup_handoff_ready = recovery.external_backup_ready or cloud_backup_ready
        backup_evidence_kind = (
            "verified-local-file"
            if recovery.external_backup_ready
            else "user-confirmed-cloud"
            if cloud_backup_ready
            else "none"
        )
        unsigned = asdict(plan)
        unsigned.pop("plan_digest")
        unsigned["method"] = plan.method.value
        if (
            project.original is None
            or not _valid_plan_shape(plan)
            or plan.schema_version != self.SCHEMA_VERSION
            or plan.project_id != project_id
            or plan.method is not method
            or plan.source_original_sha256 != project.original.sha256
            or dna is None
            or plan.device_dna_digest != dna.profile_digest
            or plan.device_dna_identity_state != CapabilityState.SUPPORTED.value
            or dna.capability("device_identity") is None
            or dna.capability("device_identity").state is not CapabilityState.SUPPORTED
            or capsule is None
            or patched is None
            or rollback is None
            or build_handoff is None
            or plan.pristine_image_sha256 != capsule.input_image_sha256
            or plan.patched_image_sha256 != patched.patched_image_sha256
            or plan.patched_receipt_digest != patched.receipt_digest
            or plan.build_handoff_digest != build_handoff.handoff_digest
            or plan.root_image_artifact_path != build_handoff.artifact_relative_path
            or plan.root_image_artifact_sha256 != build_handoff.artifact_sha256
            or plan.manager_sha256 != capsule.manager_sha256
            or plan.rollback_record_digest != rollback.record_digest
            or plan.external_backup_verified != recovery.external_backup_ready
            or plan.backup_handoff_ready != backup_handoff_ready
            or plan.backup_evidence_kind != backup_evidence_kind
            or plan.execution_authority != "guardian-review-only"
            or plan.command_manifest
            or plan.bootloader_relock_allowed
            or plan.phone_changed
            or plan.plan_digest != _digest(unsigned)
        ):
            return None
        return plan

    def matches_device(self, plan: AscensionRootPlan, device: AndroidDevice) -> bool:
        return bool(
            device.state is DeviceState.DEVICE
            and device.serial
            and device.codename.casefold() == plan.device_codename.casefold()
            and WorkspacePrivacy(self.store.workspace).pseudonym(device.serial) == plan.device_key
        )


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _valid_plan_shape(plan: AscensionRootPlan) -> bool:
    hashes = (
        plan.source_original_sha256,
        plan.device_dna_digest,
        plan.pristine_image_sha256,
        plan.patched_image_sha256,
        plan.patched_receipt_digest,
        plan.build_handoff_digest,
        plan.root_image_artifact_sha256,
        plan.manager_sha256,
        plan.rollback_record_digest,
        plan.stock_recovery_sha256,
        plan.plan_digest,
    )
    return bool(
        type(plan.schema_version) is int
        and type(plan.external_backup_verified) is bool
        and type(plan.backup_handoff_ready) is bool
        and type(plan.bootloader_relock_allowed) is bool
        and type(plan.phone_changed) is bool
        and not plan.command_manifest
        and all(_hex_text(value, 64) for value in hashes)
        and _hex_text(plan.plan_id, 32)
        and _hex_text(plan.device_key, 20)
        and all(
            _safe_text(value, limit)
            for value, limit in (
                (plan.project_id, 160),
                (plan.created_at, 80),
                (plan.device_dna_identity_state, 40),
                (plan.device_name, 256),
                (plan.device_codename, 160),
                (plan.target_partition, 40),
                (plan.root_image_artifact_path, 1024),
                (plan.manager_tag, 80),
                (plan.backup_evidence_kind, 40),
                (plan.execution_authority, 40),
            )
        )
    )


def _safe_text(value: object, maximum: int) -> bool:
    return bool(
        isinstance(value, str)
        and value
        and len(value) <= maximum
        and all(ord(character) >= 32 for character in value)
    )


def _hex_text(value: object, length: int) -> bool:
    return bool(isinstance(value, str) and re.fullmatch(rf"[0-9a-f]{{{length}}}", value))
