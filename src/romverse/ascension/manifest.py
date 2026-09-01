from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from romverse.ascension.models import AscensionMethod
from romverse.ascension.planning import AscensionRootPlanService
from romverse.ascension.preparation import RootPatchPreparationService
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.attestations import DevicePackAttestationStore
from romverse.device_packs.models import AvbPolicyAuthority
from romverse.device_packs.registry import DevicePackRegistry
from romverse.device_packs.validation import DevicePackValidationService
from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    ensure_private_directory,
    read_json_object,
)
from romverse.infrastructure.process import SubprocessRunner
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.rom.source_intelligence import FirmwareSourceIntelligenceService


class ManifestState(StrEnum):
    PASS = "pass"
    ATTENTION = "attention"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class AscensionManifestCheck:
    check_id: str
    label: str
    state: ManifestState
    evidence: str
    resolution: str
    action_id: str
    action_label: str


@dataclass(frozen=True, slots=True)
class AscensionGuardianManifest:
    """Tamper-evident root-write intent with deliberately zero execution authority."""

    schema_version: int
    manifest_id: str
    created_at: str
    project_id: str
    root_plan_id: str
    root_plan_digest: str
    method: AscensionMethod
    source_original_sha256: str
    device_pack_id: str
    device_pack_version: str
    device_pack_sha256: str
    device_key: str
    device_name: str
    device_codename: str
    target_partition: str
    target_slot: str
    required_transport: str
    pristine_image_sha256: str
    patched_image_sha256: str
    rollback_image_sha256: str
    checks: tuple[AscensionManifestCheck, ...]
    semantic_steps: tuple[str, ...]
    prohibited_actions: tuple[str, ...]
    final_consent_required: bool
    execution_authority: str
    command_manifest: tuple[tuple[str, ...], ...]
    bootloader_relock_allowed: bool
    phone_changed: bool
    manifest_digest: str

    @property
    def blockers(self) -> tuple[AscensionManifestCheck, ...]:
        return tuple(check for check in self.checks if check.state is ManifestState.BLOCKED)

    @property
    def review_ready(self) -> bool:
        return not self.blockers


class AscensionGuardianManifestService:
    """Compile exact review evidence; never construct or execute a flash command."""

    FORMAT = "romverse.ascension-guardian-manifest"
    SCHEMA_VERSION = 3
    RECEIPT_NAME = "guardian-manifest.romverse"
    MAX_BYTES = 512 * 1024
    MAX_CHECKS = 32
    MAX_LIST_ITEMS = 32
    MAX_TEXT = 8192
    REQUIRED_TRANSPORT = "usb-fastboot-final-handoff"

    def __init__(
        self,
        store: RomProjectStore,
        registry: DevicePackRegistry,
        attestation_store: DevicePackAttestationStore | None = None,
    ) -> None:
        self.store = store
        self.registry = registry
        self.attestation_store = attestation_store

    def prepare(
        self,
        project_id: str,
        method: AscensionMethod,
        device: AndroidDevice,
    ) -> AscensionGuardianManifest:
        project = self.store.get(project_id)
        plan_service = AscensionRootPlanService(self.store)
        plan = plan_service.load(project_id, method)
        if project.original is None or plan is None:
            raise ProjectError("Prepare the source-bound Ascension root plan first")
        if not plan_service.matches_device(plan, device):
            raise ProjectError("Reconnect the exact phone bound to the Ascension root plan")
        patched = RootPatchPreparationService(self.store).load_patched(project_id, method)
        if patched is None:
            raise ProjectError("Re-verify the patched image lineage before Guardian review")

        resolved = self.registry.resolve_source(project.original.sha256)
        pack = resolved.pack if resolved.matched else None
        contract = pack.build_contract if pack is not None else None
        policy = contract.avb_execution_policy if contract is not None else None
        attestation = (
            self.attestation_store.load_exact(pack, device)
            if self.attestation_store is not None and pack is not None
            else None
        )
        validation = (
            DevicePackValidationService().assess(pack, device, attestation)
            if pack is not None
            else None
        )
        exact_policy = bool(
            validation is not None
            and validation.flash_contract_ready
            and policy is not None
            and policy.authority is AvbPolicyAuthority.FLASH_VALIDATED
            and contract is not None
            and policy.evidence_build_id == contract.source.build_id
        )
        source_blueprint = FirmwareSourceIntelligenceService(
            self.store,
            (),
            SubprocessRunner(),
        ).load(project_id)
        blueprint_codename = str(getattr(source_blueprint, "codename", "")).casefold()
        blueprint_source_sha256 = str(getattr(source_blueprint, "source_archive_sha256", ""))
        private_source_review = bool(
            source_blueprint is not None
            and source_blueprint.baseline_candidate_ready
            and blueprint_source_sha256 == project.original.sha256
            and blueprint_codename
            and blueprint_codename == device.codename.casefold()
            and device.bootloader_locked is False
        )
        live_slot = _slot(device.slot_suffix)
        target_slot = policy.target_slot if exact_policy and policy is not None else live_slot
        slot_matches = bool(exact_policy and target_slot and live_slot == target_slot)
        private_slot_review = bool(private_source_review and live_slot)
        source_bound_target = plan.target_partition in {
            "boot",
            "init_boot",
            "recovery",
            "vendor_boot",
        }

        checks = (
            AscensionManifestCheck(
                "root-plan",
                "Source-bound root plan",
                ManifestState.PASS,
                f"Plan {plan.plan_id[:12]} binds pristine, patched, manager, sealed build input {plan.build_handoff_digest[:12]}…, device, and rollback digests.",
                "Return to Ascension Protocol and rebuild the plan if any bound artifact changes.",
                "refresh-ascension",
                "Re-check Ascension evidence",
            ),
            AscensionManifestCheck(
                "patch-lineage",
                "Patched-image immutable lineage",
                (
                    ManifestState.PASS
                    if patched.lineage_confidence == "high"
                    else ManifestState.ATTENTION
                ),
                (
                    "The normalized Android header and kernel are byte-identical to the pristine capsule input; only the manager-controlled ramdisk path changed."
                    if patched.lineage_confidence == "high"
                    else "The normalized Android header matches, but this kernel-less image provides no kernel bytes for comparison; exact-source confidence still relies on the protected capsule and same-phone manager handoff."
                    if patched.lineage_confidence == "limited"
                    else "The normalized Android header matches, but Magisk changed kernel bytes. Magisk supports specific legacy and Samsung kernel patches, so ROMVERSE records caution instead of inventing either failure or certainty."
                ),
                "Review the lineage explanation and keep the pristine rollback image. Recreate the patch from the ROMVERSE handoff if this change was unexpected.",
                "refresh-ascension",
                "Re-check patched image",
            ),
            AscensionManifestCheck(
                "exact-device",
                "Exact authorized phone",
                ManifestState.PASS,
                f"{device.display_name} ({device.codename}) matches the pseudonymous plan identity.",
                "Reconnect and authorize the same phone used for the root assessment.",
                "refresh-device",
                "Open device scan",
            ),
            AscensionManifestCheck(
                "bootloader-state",
                "Unlocked bootloader evidence",
                ManifestState.PASS if device.bootloader_locked is False else ManifestState.BLOCKED,
                (
                    "The read-only device scan reports the bootloader is unlocked."
                    if device.bootloader_locked is False
                    else "ROMVERSE has no verified unlocked-bootloader signal for this phone."
                ),
                "Verify the bootloader state on the phone. ROMVERSE will never unlock or relock it automatically.",
                "refresh-device",
                "Re-scan phone safely",
            ),
            AscensionManifestCheck(
                "source-contract",
                "Exact firmware Device Pack",
                ManifestState.PASS
                if contract is not None or private_source_review
                else ManifestState.BLOCKED,
                (
                    f"{pack.display_name} binds protected source {project.original.sha256[:16]}…."
                    if pack is not None and contract is not None
                    else f"Project-local {source_blueprint.source_kind} evidence binds protected source {project.original.sha256[:16]}… to exact live {device.codename}; authority remains private Guardian review only."
                    if private_source_review and source_blueprint is not None
                    else resolved.reason
                ),
                "For public release authority, acquire or publish a signed Device Pack bound to this exact protected firmware SHA-256. A private source-derived review never grants execution authority.",
                "open-device-atlas",
                "Open Device Atlas",
            ),
            AscensionManifestCheck(
                "patch-target",
                "Exact root patch target",
                ManifestState.PASS if source_bound_target else ManifestState.BLOCKED,
                (
                    f"The verified rollback capsule binds patched output to {plan.target_partition}."
                    if source_bound_target
                    else "The root plan does not identify a supported boot partition."
                ),
                "Re-scan and extract the exact firmware so ROMVERSE can prove boot or init_boot placement.",
                "refresh-ascension",
                "Re-scan firmware",
            ),
            AscensionManifestCheck(
                "flash-policy",
                "Model-specific write and recovery policy",
                ManifestState.PASS
                if exact_policy
                else ManifestState.ATTENTION
                if private_source_review
                else ManifestState.BLOCKED,
                (
                    f"Flash-validated policy for {policy.evidence_build_id} is bound to the exact Pack."
                    if exact_policy and policy is not None
                    else "Exact source, unlocked phone, patched partition, and pristine rollback are bound for private Guardian review; no public certification or execution authority is claimed."
                    if private_source_review
                    else (
                        "The matching Device Pack contains reference evidence only; it cannot authorize a phone write."
                        if policy is not None
                        else "The matching Device Pack has no flash-validated AVB execution policy."
                    )
                ),
                "Install a signed Pack update containing exact AVB, slot, stock-recovery, and physical recovery-test evidence.",
                "open-device-atlas",
                "Find exact Device Pack",
            ),
            AscensionManifestCheck(
                "slot-policy",
                "Exact target slot",
                ManifestState.PASS
                if slot_matches
                else ManifestState.ATTENTION
                if private_slot_review
                else ManifestState.BLOCKED,
                (
                    f"The flash-validated Pack selects slot {target_slot}; live Android reports {live_slot or 'no slot'}"
                    if slot_matches
                    else f"Live Android reports slot {live_slot}; private Guardian review records it but final handoff must re-check the slot in fastboot."
                    if private_slot_review
                    else (
                        f"The Pack selects slot {target_slot}, but live Android reports {live_slot or 'no verified slot'}."
                        if exact_policy and target_slot
                        else f"Live Android reports {live_slot or 'no verified slot'}, but no flash-validated slot policy is active."
                    )
                ),
                "ROMVERSE must re-check the active slot in fastboot and compare it with the exact Device Pack at final handoff.",
                "refresh-device",
                "Re-scan phone and slot",
            ),
            AscensionManifestCheck(
                "rollback",
                "Pristine partition rollback",
                ManifestState.PASS,
                f"Pristine {plan.target_partition} rollback SHA-256 {plan.pristine_image_sha256[:16]}… is source-bound.",
                "Rebuild the rollback capsule from the protected source if verification changes.",
                "refresh-ascension",
                "Re-check rollback",
            ),
            AscensionManifestCheck(
                "user-backup",
                "User-data backup handoff",
                ManifestState.PASS if plan.backup_handoff_ready else ManifestState.BLOCKED,
                (
                    "A local-drive backup archive was hash-verified by ROMVERSE."
                    if plan.backup_evidence_kind == "verified-local-file"
                    else (
                        "An exact project/device-bound cloud backup was confirmed by the user; ROMVERSE did not inspect private cloud contents."
                        if plan.backup_evidence_kind == "user-confirmed-cloud"
                        else "No user-data backup handoff is registered for this exact project and phone."
                    )
                ),
                "Create or register a local-drive backup, or confirm a completed cloud backup before final Guardian review.",
                "open-backup-guide",
                "Create or verify backup",
            ),
            AscensionManifestCheck(
                "final-consent",
                "Final human confirmation",
                ManifestState.ATTENTION,
                "No device write is authorized. A plain-language final review remains mandatory.",
                "At the final handoff, review the exact phone, partition, hashes, consequences, and rollback path.",
                "none",
                "",
            ),
        )
        semantic_steps = (
            "Re-identify the exact phone in fastboot without changing it.",
            f"Re-hash the patched {plan.target_partition} image and pristine rollback image.",
            "Re-check the Device Pack, AVB policy, slot, battery, cable, and backup evidence.",
            f"After separate final consent only: write the exact patched digest to {plan.target_partition} on the validated slot.",
            "Reboot without relocking, then record boot and root-manager health evidence.",
        )
        prohibited_actions = (
            "Bootloader relock",
            "Bootloader unlock",
            "User-data wipe",
            "EDL or OEM service-mode write",
            "Write to any partition or slot not named by this manifest",
            "Use an image whose SHA-256 differs from this manifest",
        )
        payload: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "manifest_id": uuid4().hex,
            "created_at": datetime.now(UTC).isoformat(),
            "project_id": project_id,
            "root_plan_id": plan.plan_id,
            "root_plan_digest": plan.plan_digest,
            "method": method.value,
            "source_original_sha256": project.original.sha256,
            "device_pack_id": pack.pack_id if pack is not None else "",
            "device_pack_version": pack.version if pack is not None else "",
            "device_pack_sha256": pack.sha256 if pack is not None else "",
            "device_key": plan.device_key,
            "device_name": plan.device_name,
            "device_codename": plan.device_codename,
            "target_partition": plan.target_partition,
            "target_slot": target_slot,
            "required_transport": self.REQUIRED_TRANSPORT,
            "pristine_image_sha256": plan.pristine_image_sha256,
            "patched_image_sha256": plan.patched_image_sha256,
            "rollback_image_sha256": plan.stock_recovery_sha256,
            "checks": [asdict(check) for check in checks],
            "semantic_steps": semantic_steps,
            "prohibited_actions": prohibited_actions,
            "final_consent_required": True,
            "execution_authority": "none",
            "command_manifest": (),
            "bootloader_relock_allowed": False,
            "phone_changed": False,
        }
        materialized = dict(payload)
        materialized["method"] = method
        materialized["checks"] = checks
        manifest = AscensionGuardianManifest(
            **materialized,
            manifest_digest=_digest(payload),
        )
        self._write(project_id, manifest)
        return manifest

    def load(
        self,
        project_id: str,
        method: AscensionMethod,
    ) -> AscensionGuardianManifest | None:
        path = self._root(project_id) / self.RECEIPT_NAME
        try:
            data = read_json_object(
                path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            if (
                set(data)
                != {"format", *(field.name for field in fields(AscensionGuardianManifest))}
                or data.pop("format") != self.FORMAT
            ):
                return None
            raw_checks = data.get("checks")
            raw_steps = data.get("semantic_steps")
            raw_prohibited = data.get("prohibited_actions")
            raw_commands = data.get("command_manifest")
            check_fields = {field.name for field in fields(AscensionManifestCheck)}
            if (
                not isinstance(raw_checks, list)
                or not 1 <= len(raw_checks) <= self.MAX_CHECKS
                or any(
                    not isinstance(item, dict) or set(item) != check_fields for item in raw_checks
                )
                or not _valid_text_list(raw_steps, self.MAX_LIST_ITEMS, self.MAX_TEXT)
                or not _valid_text_list(raw_prohibited, self.MAX_LIST_ITEMS, self.MAX_TEXT)
                or raw_commands != []
            ):
                return None
            data["method"] = AscensionMethod(str(data["method"]))
            checks: list[AscensionManifestCheck] = []
            for item in raw_checks:
                values = dict(item)
                values["state"] = ManifestState(str(values["state"]))
                checks.append(AscensionManifestCheck(**values))
            data["checks"] = tuple(checks)
            data["semantic_steps"] = tuple(raw_steps)
            data["prohibited_actions"] = tuple(raw_prohibited)
            data["command_manifest"] = ()
            manifest = AscensionGuardianManifest(**data)
        except (LocalStoreError, ValueError, TypeError, KeyError):
            return None
        plan = AscensionRootPlanService(self.store).load(project_id, method)
        unsigned = asdict(manifest)
        expected = str(unsigned.pop("manifest_digest", ""))
        unsigned["method"] = manifest.method.value
        if (
            plan is None
            or not _valid_manifest_shape(manifest, self.MAX_TEXT)
            or manifest.schema_version != self.SCHEMA_VERSION
            or manifest.project_id != project_id
            or manifest.method is not method
            or manifest.root_plan_id != plan.plan_id
            or manifest.root_plan_digest != plan.plan_digest
            or manifest.source_original_sha256 != plan.source_original_sha256
            or manifest.device_key != plan.device_key
            or manifest.patched_image_sha256 != plan.patched_image_sha256
            or manifest.pristine_image_sha256 != plan.pristine_image_sha256
            or manifest.execution_authority != "none"
            or manifest.command_manifest
            or manifest.bootloader_relock_allowed
            or manifest.phone_changed
            or not manifest.final_consent_required
            or expected != _digest(unsigned)
            or "Bootloader relock" not in manifest.prohibited_actions
        ):
            return None
        return manifest

    def matches_device(
        self,
        manifest: AscensionGuardianManifest,
        device: AndroidDevice,
    ) -> bool:
        plan = AscensionRootPlanService(self.store).load(manifest.project_id, manifest.method)
        return bool(
            plan is not None
            and device.state is DeviceState.DEVICE
            and AscensionRootPlanService(self.store).matches_device(plan, device)
        )

    def _write(self, project_id: str, manifest: AscensionGuardianManifest) -> None:
        root = self._root(project_id)
        document = {"format": self.FORMAT, **asdict(manifest)}
        try:
            ensure_private_directory(root, boundary=self.store.workspace)
            for path in (
                root / self.RECEIPT_NAME,
                root / f"guardian-manifest-{manifest.manifest_id[:12]}.romverse",
            ):
                atomic_write_json(
                    path,
                    document,
                    boundary=self.store.workspace,
                    maximum_bytes=self.MAX_BYTES,
                )
        except LocalStoreError as exc:
            raise ProjectError(
                "Ascension Guardian manifest evidence could not be stored safely"
            ) from exc

    def _root(self, project_id: str) -> Path:
        self.store.get(project_id)
        return self.store.projects_root / project_id / "ascension" / "guardian"


def _slot(value: str) -> str:
    normalized = value.casefold().strip().removeprefix("_")
    return normalized if normalized in {"a", "b"} else ""


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _valid_manifest_shape(manifest: AscensionGuardianManifest, maximum_text: int) -> bool:
    check_ids = tuple(check.check_id for check in manifest.checks)
    return bool(
        type(manifest.schema_version) is int
        and type(manifest.final_consent_required) is bool
        and type(manifest.bootloader_relock_allowed) is bool
        and type(manifest.phone_changed) is bool
        and not manifest.command_manifest
        and len(set(check_ids)) == len(check_ids)
        and all(
            all(
                _safe_text(value, maximum_text, allow_empty=allow_empty)
                for value, allow_empty in (
                    (check.check_id, False),
                    (check.label, False),
                    (check.evidence, False),
                    (check.resolution, False),
                    (check.action_id, False),
                    (check.action_label, True),
                )
            )
            for check in manifest.checks
        )
        and all(
            _hex_text(value, 64)
            for value in (
                manifest.root_plan_digest,
                manifest.source_original_sha256,
                manifest.pristine_image_sha256,
                manifest.patched_image_sha256,
                manifest.rollback_image_sha256,
                manifest.manifest_digest,
            )
        )
        and (manifest.device_pack_sha256 == "" or _hex_text(manifest.device_pack_sha256, 64))
        and _hex_text(manifest.manifest_id, 32)
        and _hex_text(manifest.root_plan_id, 32)
        and _hex_text(manifest.device_key, 20)
        and all(
            _safe_text(value, maximum_text, allow_empty=allow_empty)
            for value, allow_empty in (
                (manifest.created_at, False),
                (manifest.project_id, False),
                (manifest.device_pack_id, True),
                (manifest.device_pack_version, True),
                (manifest.device_name, False),
                (manifest.device_codename, False),
                (manifest.target_partition, False),
                (manifest.target_slot, True),
                (manifest.required_transport, False),
                (manifest.execution_authority, False),
            )
        )
    )


def _valid_text_list(value: object, maximum_items: int, maximum_text: int) -> bool:
    return bool(
        isinstance(value, list)
        and 1 <= len(value) <= maximum_items
        and all(_safe_text(item, maximum_text, allow_empty=False) for item in value)
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
