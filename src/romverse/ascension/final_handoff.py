from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from romverse.ascension.manifest import AscensionGuardianManifest, ManifestState
from romverse.ascension.models import AscensionMethod
from romverse.ascension.planning import AscensionRootPlan, AscensionRootPlanService
from romverse.ascension.preparation import RootPatchPreparationService
from romverse.device.models import AndroidDevice, DeviceState
from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    ensure_private_directory,
    read_json_object,
)
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore


class GuardianManifestProvider(Protocol):
    def load(
        self,
        project_id: str,
        method: AscensionMethod,
    ) -> AscensionGuardianManifest | None: ...

    def matches_device(
        self,
        manifest: AscensionGuardianManifest,
        device: AndroidDevice,
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class AscensionFinalHandoff:
    """Exact-device review packet with deliberately zero execution authority."""

    schema_version: int
    handoff_id: str
    created_at: str
    project_id: str
    method: AscensionMethod
    manifest_id: str
    manifest_digest: str
    root_plan_id: str
    root_plan_digest: str
    source_original_sha256: str
    device_pack_id: str
    device_pack_version: str
    device_pack_sha256: str
    device_key: str
    device_name: str
    device_codename: str
    target_partition: str
    target_slot: str
    observed_slot: str
    required_transport: str
    observed_transport: str
    battery_percent: int
    bootloader_unlocked_observed: bool
    pristine_image_path: str
    pristine_image_sha256: str
    patched_image_path: str
    patched_image_sha256: str
    patched_image_size_bytes: int
    rollback_image_sha256: str
    manager_tag: str
    manager_sha256: str
    external_backup_verified: bool
    backup_handoff_ready: bool
    backup_evidence_kind: str
    final_consent_required: bool
    execution_authority: str
    command_manifest: tuple[tuple[str, ...], ...]
    bootloader_unlock_allowed: bool
    bootloader_relock_allowed: bool
    user_data_wipe_allowed: bool
    phone_changed: bool
    prohibited_actions: tuple[str, ...]
    handoff_digest: str


class AscensionFinalHandoffService:
    """Compile the last command-free review packet before a separate consent ceremony.

    This service intentionally cannot execute a process. Its only output is a signed-by-digest
    local record proving that the exact source, patched output, phone, slot, transport, backup,
    battery, and rollback evidence still agree.
    """

    FORMAT = "romverse.ascension-final-handoff"
    SCHEMA_VERSION = 2
    RECEIPT_NAME = "final-handoff.romverse"
    MAX_BYTES = 256 * 1024
    MAX_PROHIBITIONS = 32
    MAX_TEXT = 8192
    MINIMUM_BATTERY_PERCENT = 50
    ALLOWED_PARTITIONS = frozenset({"boot", "init_boot", "recovery", "vendor_boot"})
    REQUIRED_TRANSPORT = "usb-fastboot-final-handoff"
    REQUIRED_PASS_CHECKS = frozenset(
        {
            "root-plan",
            "exact-device",
            "bootloader-state",
            "source-contract",
            "patch-target",
            "flash-policy",
            "slot-policy",
            "rollback",
            "user-backup",
        }
    )
    REQUIRED_PROHIBITIONS = frozenset(
        {
            "Bootloader relock",
            "Bootloader unlock",
            "User-data wipe",
            "Write to any partition or slot not named by this manifest",
            "Use an image whose SHA-256 differs from this manifest",
        }
    )

    def __init__(
        self,
        store: RomProjectStore,
        manifests: GuardianManifestProvider,
    ) -> None:
        self.store = store
        self.manifests = manifests

    def prepare(
        self,
        project_id: str,
        method: AscensionMethod,
        device: AndroidDevice,
    ) -> AscensionFinalHandoff:
        plan, manifest, capsule, patched = self._current(project_id, method)
        self._require_ready(plan, manifest, device)

        payload: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "handoff_id": uuid4().hex,
            "created_at": datetime.now(UTC).isoformat(),
            "project_id": project_id,
            "method": method.value,
            "manifest_id": manifest.manifest_id,
            "manifest_digest": manifest.manifest_digest,
            "root_plan_id": plan.plan_id,
            "root_plan_digest": plan.plan_digest,
            "source_original_sha256": plan.source_original_sha256,
            "device_pack_id": manifest.device_pack_id,
            "device_pack_version": manifest.device_pack_version,
            "device_pack_sha256": manifest.device_pack_sha256,
            "device_key": plan.device_key,
            "device_name": plan.device_name,
            "device_codename": plan.device_codename,
            "target_partition": plan.target_partition,
            "target_slot": manifest.target_slot,
            "observed_slot": _slot(device.slot_suffix),
            "required_transport": manifest.required_transport,
            "observed_transport": device.transport.casefold(),
            "battery_percent": device.battery_percent,
            "bootloader_unlocked_observed": True,
            "pristine_image_path": capsule.input_image_path,
            "pristine_image_sha256": capsule.input_image_sha256,
            "patched_image_path": patched.patched_image_path,
            "patched_image_sha256": patched.patched_image_sha256,
            "patched_image_size_bytes": patched.patched_image_size_bytes,
            "rollback_image_sha256": manifest.rollback_image_sha256,
            "manager_tag": plan.manager_tag,
            "manager_sha256": plan.manager_sha256,
            "external_backup_verified": plan.external_backup_verified,
            "backup_handoff_ready": plan.backup_handoff_ready,
            "backup_evidence_kind": plan.backup_evidence_kind,
            "final_consent_required": True,
            "execution_authority": "none",
            "command_manifest": (),
            "bootloader_unlock_allowed": False,
            "bootloader_relock_allowed": False,
            "user_data_wipe_allowed": False,
            "phone_changed": False,
            "prohibited_actions": manifest.prohibited_actions,
        }
        materialized = dict(payload)
        materialized["method"] = method
        handoff = AscensionFinalHandoff(
            **materialized,
            handoff_digest=_digest(payload),
        )
        self.validate(handoff)
        self._write(handoff)
        return handoff

    def load(
        self,
        project_id: str,
        method: AscensionMethod,
        device: AndroidDevice | None = None,
    ) -> AscensionFinalHandoff | None:
        path = self._root(project_id) / self.RECEIPT_NAME
        try:
            data = read_json_object(
                path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            if (
                set(data) != {"format", *(field.name for field in fields(AscensionFinalHandoff))}
                or data.pop("format") != self.FORMAT
            ):
                return None
            raw_commands = data.get("command_manifest")
            raw_prohibited = data.get("prohibited_actions")
            if (
                raw_commands != []
                or not isinstance(raw_prohibited, list)
                or not 1 <= len(raw_prohibited) <= self.MAX_PROHIBITIONS
                or any(
                    not _safe_text(item, self.MAX_TEXT, allow_empty=False)
                    for item in raw_prohibited
                )
            ):
                return None
            data["method"] = AscensionMethod(str(data["method"]))
            data["command_manifest"] = ()
            data["prohibited_actions"] = tuple(raw_prohibited)
            handoff = AscensionFinalHandoff(**data)
            self.validate(handoff)
            plan, manifest, capsule, patched = self._current(project_id, method)
        except (LocalStoreError, ValueError, TypeError, KeyError, ProjectError):
            return None

        if (
            handoff.project_id != project_id
            or handoff.method is not method
            or handoff.manifest_id != manifest.manifest_id
            or handoff.manifest_digest != manifest.manifest_digest
            or handoff.root_plan_id != plan.plan_id
            or handoff.root_plan_digest != plan.plan_digest
            or handoff.source_original_sha256 != plan.source_original_sha256
            or handoff.device_pack_id != manifest.device_pack_id
            or handoff.device_pack_version != manifest.device_pack_version
            or handoff.device_pack_sha256 != manifest.device_pack_sha256
            or handoff.device_key != plan.device_key
            or handoff.device_codename != plan.device_codename
            or handoff.target_partition != plan.target_partition
            or handoff.target_slot != manifest.target_slot
            or handoff.pristine_image_path != capsule.input_image_path
            or handoff.pristine_image_sha256 != capsule.input_image_sha256
            or handoff.patched_image_path != patched.patched_image_path
            or handoff.patched_image_sha256 != patched.patched_image_sha256
            or handoff.patched_image_size_bytes != patched.patched_image_size_bytes
            or handoff.rollback_image_sha256 != manifest.rollback_image_sha256
            or handoff.manager_tag != plan.manager_tag
            or handoff.manager_sha256 != plan.manager_sha256
            or handoff.external_backup_verified != plan.external_backup_verified
            or handoff.backup_handoff_ready != plan.backup_handoff_ready
            or handoff.backup_evidence_kind != plan.backup_evidence_kind
            or not plan.backup_handoff_ready
            or not manifest.review_ready
        ):
            return None
        if device is not None:
            try:
                self._require_ready(plan, manifest, device)
            except ProjectError:
                return None
            if (
                handoff.observed_slot != _slot(device.slot_suffix)
                or handoff.observed_transport != device.transport.casefold()
                or handoff.battery_percent != device.battery_percent
            ):
                return None
        return handoff

    def validate(self, handoff: AscensionFinalHandoff) -> None:
        unsigned = asdict(handoff)
        expected = str(unsigned.pop("handoff_digest", ""))
        unsigned["method"] = handoff.method.value
        if (
            handoff.schema_version != self.SCHEMA_VERSION
            or not _valid_handoff_shape(handoff, self.MAX_TEXT)
            or handoff.target_partition not in self.ALLOWED_PARTITIONS
            or handoff.target_slot not in {"a", "b"}
            or handoff.observed_slot != handoff.target_slot
            or handoff.required_transport != self.REQUIRED_TRANSPORT
            or handoff.observed_transport != "usb"
            or handoff.battery_percent < self.MINIMUM_BATTERY_PERCENT
            or not handoff.bootloader_unlocked_observed
            or not handoff.backup_handoff_ready
            or handoff.backup_evidence_kind not in {"verified-local-file", "user-confirmed-cloud"}
            or (
                handoff.backup_evidence_kind == "verified-local-file"
                and not handoff.external_backup_verified
            )
            or (
                handoff.backup_evidence_kind == "user-confirmed-cloud"
                and handoff.external_backup_verified
            )
            or not handoff.final_consent_required
            or handoff.execution_authority != "none"
            or handoff.command_manifest
            or handoff.bootloader_unlock_allowed
            or handoff.bootloader_relock_allowed
            or handoff.user_data_wipe_allowed
            or handoff.phone_changed
            or not self.REQUIRED_PROHIBITIONS.issubset(handoff.prohibited_actions)
            or not all(
                _sha256_value(value)
                for value in (
                    handoff.manifest_digest,
                    handoff.root_plan_digest,
                    handoff.source_original_sha256,
                    handoff.device_pack_sha256,
                    handoff.pristine_image_sha256,
                    handoff.patched_image_sha256,
                    handoff.rollback_image_sha256,
                    handoff.manager_sha256,
                    expected,
                )
            )
            or expected != _digest(unsigned)
        ):
            raise ProjectError("Ascension final handoff failed integrity or safety validation")

    def _current(self, project_id: str, method: AscensionMethod):
        plan = AscensionRootPlanService(self.store).load(project_id, method)
        manifest = self.manifests.load(project_id, method)
        preparation = RootPatchPreparationService(self.store)
        capsule = preparation.load(project_id, method)
        patched = preparation.load_patched(project_id, method)
        if plan is None or manifest is None or capsule is None or patched is None:
            raise ProjectError("Ascension final handoff evidence is incomplete or changed")
        return plan, manifest, capsule, patched

    def _require_ready(
        self,
        plan: AscensionRootPlan,
        manifest: AscensionGuardianManifest,
        device: AndroidDevice,
    ) -> None:
        if manifest.root_plan_id != plan.plan_id or manifest.root_plan_digest != plan.plan_digest:
            raise ProjectError("Guardian manifest does not match the current root plan")
        if not manifest.review_ready or any(
            check.state is ManifestState.BLOCKED for check in manifest.checks
        ):
            raise ProjectError("Resolve every Guardian safety gate before final handoff")
        passed = {check.check_id for check in manifest.checks if check.state is ManifestState.PASS}
        if not self.REQUIRED_PASS_CHECKS.issubset(passed):
            raise ProjectError("Guardian manifest is missing required passing safety evidence")
        final_consent = next(
            (check for check in manifest.checks if check.check_id == "final-consent"),
            None,
        )
        if final_consent is None or final_consent.state is not ManifestState.ATTENTION:
            raise ProjectError("Final human consent must remain outstanding at handoff preparation")
        if (
            not manifest.final_consent_required
            or manifest.execution_authority != "none"
            or manifest.command_manifest
            or manifest.bootloader_relock_allowed
            or manifest.phone_changed
            or manifest.required_transport != self.REQUIRED_TRANSPORT
        ):
            raise ProjectError("Guardian manifest carries unsafe execution authority")
        if not manifest.device_pack_id or not _sha256_value(manifest.device_pack_sha256):
            raise ProjectError("Final handoff requires an exact flash-validated Device Pack")
        if not self.manifests.matches_device(manifest, device):
            raise ProjectError("Reconnect the exact phone bound to the Guardian manifest")
        if device.state is not DeviceState.DEVICE:
            raise ProjectError("The exact phone must be authorized and online")
        if device.bootloader_locked is not False:
            raise ProjectError("An explicitly unlocked bootloader signal is required")
        if device.transport.casefold() != "usb":
            raise ProjectError("Final handoff requires a direct USB connection")
        if device.battery_percent is None or device.battery_percent < self.MINIMUM_BATTERY_PERCENT:
            raise ProjectError(
                f"Charge the phone to at least {self.MINIMUM_BATTERY_PERCENT}% before final handoff"
            )
        observed_slot = _slot(device.slot_suffix)
        if observed_slot != manifest.target_slot or observed_slot not in {"a", "b"}:
            raise ProjectError("Live slot evidence does not match the exact Device Pack policy")
        if not plan.backup_handoff_ready:
            raise ProjectError(
                "Complete the exact project/device-bound backup handoff before final review"
            )
        if not self.REQUIRED_PROHIBITIONS.issubset(manifest.prohibited_actions):
            raise ProjectError("Guardian manifest is missing permanent safety prohibitions")

    def _write(self, handoff: AscensionFinalHandoff) -> None:
        root = self._root(handoff.project_id)
        document = {"format": self.FORMAT, **asdict(handoff)}
        try:
            ensure_private_directory(root, boundary=self.store.workspace)
            for path in (
                root / self.RECEIPT_NAME,
                root / f"final-handoff-{handoff.handoff_id[:12]}.romverse",
            ):
                atomic_write_json(
                    path,
                    document,
                    boundary=self.store.workspace,
                    maximum_bytes=self.MAX_BYTES,
                )
        except LocalStoreError as exc:
            raise ProjectError(
                "Ascension final-handoff evidence could not be stored safely"
            ) from exc

    def _root(self, project_id: str) -> Path:
        self.store.get(project_id)
        return self.store.projects_root / project_id / "ascension" / "guardian"


def _slot(value: str) -> str:
    normalized = value.casefold().strip().removeprefix("_")
    return normalized if normalized in {"a", "b"} else ""


def _sha256_value(value: object) -> bool:
    return bool(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value))


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _valid_handoff_shape(handoff: AscensionFinalHandoff, maximum_text: int) -> bool:
    return bool(
        type(handoff.schema_version) is int
        and type(handoff.battery_percent) is int
        and 0 <= handoff.battery_percent <= 100
        and type(handoff.patched_image_size_bytes) is int
        and handoff.patched_image_size_bytes > 0
        and all(
            type(value) is bool
            for value in (
                handoff.bootloader_unlocked_observed,
                handoff.external_backup_verified,
                handoff.backup_handoff_ready,
                handoff.final_consent_required,
                handoff.bootloader_unlock_allowed,
                handoff.bootloader_relock_allowed,
                handoff.user_data_wipe_allowed,
                handoff.phone_changed,
            )
        )
        and not handoff.command_manifest
        and len(set(handoff.prohibited_actions)) == len(handoff.prohibited_actions)
        and _hex_value(handoff.handoff_id, 32)
        and _hex_value(handoff.root_plan_id, 32)
        and _hex_value(handoff.device_key, 20)
        and all(
            _safe_text(value, maximum_text, allow_empty=False)
            for value in (
                handoff.created_at,
                handoff.project_id,
                handoff.manifest_id,
                handoff.device_pack_id,
                handoff.device_pack_version,
                handoff.device_name,
                handoff.device_codename,
                handoff.target_partition,
                handoff.target_slot,
                handoff.observed_slot,
                handoff.required_transport,
                handoff.observed_transport,
                handoff.pristine_image_path,
                handoff.patched_image_path,
                handoff.manager_tag,
                handoff.backup_evidence_kind,
                handoff.execution_authority,
            )
        )
    )


def _safe_text(value: object, maximum: int, *, allow_empty: bool) -> bool:
    return bool(
        isinstance(value, str)
        and (allow_empty or value)
        and len(value) <= maximum
        and all(ord(character) >= 32 or character in "\n\t" for character in value)
    )


def _hex_value(value: object, length: int) -> bool:
    return bool(isinstance(value, str) and re.fullmatch(rf"[0-9a-f]{{{length}}}", value))
