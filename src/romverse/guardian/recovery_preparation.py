from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import asdict, fields
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from romverse.core.privacy import WorkspacePrivacy
from romverse.core.recovery_contracts import (
    GuardianPreparedRecoveryStep,
    GuardianRecoveryPreparation,
    RecoveryContractError,
    RecoveryIncident,
    RecoveryIncidentEvidenceStore,
    RecoveryRoute,
    RecoveryRouteKind,
)
from romverse.device.models import AndroidDevice
from romverse.device_packs.models import DeviceRecoveryOperation
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


class GuardianRecoveryPreparationError(ProjectError):
    """A Recovery route could not become an exact, zero-authority preparation."""


class GuardianRecoveryPreparationService:
    """Prepare one current signed Recovery route without inheriting authority.

    Recovery owns the incident and recommendation.  This service independently
    revalidates the exact current device, project, protected source, Device Pack,
    recovery evidence and signed adapter actions before Guardian can display a
    consequential review.  It intentionally exposes no execute/approve method.
    """

    FORMAT = "romverse.guardian-recovery-preparation"
    SCHEMA_VERSION = 1
    LATEST_NAME = "latest.romverse"
    MAX_BYTES = 256 * 1024
    STATUS = "prepared-awaiting-guardian-live-target-and-consent"
    SUPPORTED_ROUTES = {
        RecoveryRouteKind.EXACT_STOCK_RESTORE: DeviceRecoveryOperation.RESTORE_STOCK_PACKAGE,
    }

    def __init__(
        self,
        store: RomProjectStore,
        registry: DevicePackRegistry,
        autopilot: RecoveryIncidentEvidenceStore,
    ) -> None:
        if not isinstance(autopilot, RecoveryIncidentEvidenceStore):
            raise GuardianRecoveryPreparationError(
                "Recovery preparation requires the nominal incident evidence boundary"
            )
        self.store = store
        self.registry = registry
        self.autopilot = autopilot
        self.evidence = RecoveryEvidenceService(store)
        self.privacy = WorkspacePrivacy(store.workspace)

    def prepare(
        self,
        incident_id: str,
        route_id: str,
        devices: tuple[AndroidDevice, ...] | list[AndroidDevice],
    ) -> GuardianRecoveryPreparation:
        incident, route, device = self._current_context(incident_id, route_id, devices)
        project = self.store.get(incident.project_id)
        pack = next(
            (
                item
                for item in self.registry.packs
                if item.pack_id == incident.pack_id
                and hmac.compare_digest(item.sha256, incident.pack_sha256)
            ),
            None,
        )
        if pack is None or project.device_pack_id != pack.pack_id or project.original is None:
            raise GuardianRecoveryPreparationError(
                "The Recovery project or signed Device Pack no longer matches this incident"
            )
        resolution = self.registry.resolve(device)
        if (
            resolution.pack is None
            or resolution.pack.pack_id != pack.pack_id
            or not hmac.compare_digest(resolution.pack.sha256, pack.sha256)
        ):
            raise GuardianRecoveryPreparationError(
                "The freshly scanned phone no longer matches the incident Device Pack"
            )
        build = pack.build_contract
        write = build.partition_write_contract if build is not None else None
        transition = write.transition_recovery_contract if write is not None else None
        if (
            build is None
            or write is None
            or transition is None
            or not self.registry.transition_recovery_contract_is_valid(write, build.source)
            or project.original.sha256 != build.source.archive_sha256
            or transition.recovery.stock_package_sha256 != project.original.sha256
        ):
            raise GuardianRecoveryPreparationError(
                "The project has no current exact source-bound recovery contract"
            )
        evidence_record = self.evidence.load(project.project_id)
        assessment = self.evidence.assess(project.project_id, device)
        if evidence_record is None or not assessment.ready:
            raise GuardianRecoveryPreparationError(
                "Verify the external backup and exact stock package in Time Machine first"
            )
        external_backup = evidence_record.external_backup
        if (
            external_backup is not None
            and external_backup.device_key
            and not hmac.compare_digest(external_backup.device_key, incident.device_key)
        ):
            raise GuardianRecoveryPreparationError(
                "The verified external backup belongs to a different phone"
            )
        focused = self.SUPPORTED_ROUTES[route.kind]
        try:
            start = next(
                index
                for index, step in enumerate(transition.recovery.actions)
                if step.operation is focused
            )
        except StopIteration as exc:
            raise GuardianRecoveryPreparationError(
                "The signed Device Pack does not declare the requested recovery action"
            ) from exc
        selected = transition.recovery.actions[start:]
        steps = tuple(
            GuardianPreparedRecoveryStep(
                order=index,
                operation=step.operation,
                adapter_action_id=step.adapter_action_id,
                from_mode=step.from_mode.value,
                to_mode=step.to_mode.value,
                target_slot=step.target_slot,
                timeout_seconds=step.timeout_seconds,
                may_wipe_user_data=step.may_wipe_user_data,
            )
            for index, step in enumerate(selected, 1)
        )
        steps_digest = _digest({"steps": [asdict(item) for item in steps]})
        transition_digest = _digest(asdict(transition))
        payload: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "preparation_id": uuid4().hex,
            "created_at": datetime.now(UTC).isoformat(),
            "incident_id": incident.incident_id,
            "incident_record_digest": incident.record_digest,
            "route_id": route.route_id,
            "route_kind": route.kind,
            "project_id": project.project_id,
            "device_key": incident.device_key,
            "device_name": incident.device_name,
            "expected_product": device.product,
            "expected_entry_mode": steps[0].from_mode,
            "source_original_sha256": project.original.sha256,
            "device_pack_id": pack.pack_id,
            "device_pack_version": pack.version,
            "device_pack_sha256": pack.sha256,
            "transition_contract_id": transition.contract_id,
            "transition_contract_digest": transition_digest,
            "recovery_strategy": transition.recovery.strategy.value,
            "recovery_adapter_id": transition.recovery.adapter_id,
            "stock_package_sha256": transition.recovery.stock_package_sha256,
            "recovery_evidence_digest": evidence_record.record_digest,
            "focused_operation": focused,
            "step_count": len(steps),
            "steps_digest": steps_digest,
            "steps": [asdict(item) for item in steps],
            "may_wipe_user_data": any(item.may_wipe_user_data for item in steps),
            "recorded_prewrite_slot_required": any(
                item.target_slot == "recorded_prewrite" for item in steps
            ),
            "guardian_validation_required": True,
            "user_confirmation_required": True,
            "execution_authority": "none",
            "runtime_invoked": False,
            "phone_changed": False,
            "bootloader_relock_allowed": False,
            "preparation_status": self.STATUS,
        }
        preparation = GuardianRecoveryPreparation(
            **{key: value for key, value in payload.items() if key != "steps"},
            steps=steps,
            preparation_digest=_digest(payload),
        )
        self.validate(preparation)
        self._write(preparation)
        return preparation

    def load(
        self,
        incident_id: str,
        route_id: str,
        devices: tuple[AndroidDevice, ...] | list[AndroidDevice],
    ) -> GuardianRecoveryPreparation | None:
        try:
            incident, route, _device = self._current_context(incident_id, route_id, devices)
            data = read_json_object(
                self._path(incident.incident_id),
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            expected = {"format", *(field.name for field in fields(GuardianRecoveryPreparation))}
            if set(data) != expected or data.pop("format") != self.FORMAT:
                return None
            raw_steps = data.pop("steps")
            step_fields = {field.name for field in fields(GuardianPreparedRecoveryStep)}
            if not isinstance(raw_steps, list) or any(
                not isinstance(item, dict) or set(item) != step_fields for item in raw_steps
            ):
                return None
            preparation = GuardianRecoveryPreparation(
                **{
                    **data,
                    "route_kind": RecoveryRouteKind(str(data["route_kind"])),
                    "focused_operation": DeviceRecoveryOperation(str(data["focused_operation"])),
                },
                steps=tuple(
                    GuardianPreparedRecoveryStep(
                        **{
                            **item,
                            "operation": DeviceRecoveryOperation(str(item["operation"])),
                        }
                    )
                    for item in raw_steps
                ),
            )
            self.validate(preparation)
            if (
                preparation.incident_record_digest != incident.record_digest
                or preparation.route_id != route.route_id
                or not self._matches_current(preparation, incident, route, _device)
            ):
                return None
            return preparation
        except (
            GuardianRecoveryPreparationError,
            RecoveryContractError,
            LocalStoreError,
            OSError,
            ProjectError,
            TypeError,
            ValueError,
            KeyError,
            json.JSONDecodeError,
        ):
            return None

    @classmethod
    def validate(cls, preparation: GuardianRecoveryPreparation) -> None:
        payload = asdict(preparation)
        digest = str(payload.pop("preparation_digest", ""))
        steps = preparation.steps
        if (
            type(preparation.schema_version) is not int
            or preparation.schema_version != cls.SCHEMA_VERSION
            or not _hex(preparation.preparation_id, 32)
            or not _aware_timestamp(preparation.created_at)
            or not _hex(preparation.incident_id, 32)
            or not _hex(preparation.incident_record_digest, 64)
            or not _clean(preparation.route_id, 80)
            or preparation.route_kind not in cls.SUPPORTED_ROUTES
            or not _clean(preparation.project_id, 100)
            or not _hex(preparation.device_key, 20)
            or not _clean(preparation.device_name, 120)
            or not _clean(preparation.expected_product, 120)
            or preparation.expected_entry_mode not in {"bootloader", "fastbootd"}
            or not _hex(preparation.source_original_sha256, 64)
            or not _clean(preparation.device_pack_id, 128)
            or not _clean(preparation.device_pack_version, 80)
            or not _hex(preparation.device_pack_sha256, 64)
            or not _clean(preparation.transition_contract_id, 80)
            or not _hex(preparation.transition_contract_digest, 64)
            or not _clean(preparation.recovery_strategy, 80)
            or not _clean(preparation.recovery_adapter_id, 80)
            or "relock" in preparation.recovery_adapter_id.casefold()
            or not _hex(preparation.stock_package_sha256, 64)
            or preparation.stock_package_sha256 != preparation.source_original_sha256
            or not _hex(preparation.recovery_evidence_digest, 64)
            or preparation.focused_operation is not cls.SUPPORTED_ROUTES[preparation.route_kind]
            or type(preparation.step_count) is not int
            or preparation.step_count != len(steps)
            or not 1 <= preparation.step_count <= 16
            or tuple(item.order for item in steps) != tuple(range(1, len(steps) + 1))
            or steps[0].operation is not preparation.focused_operation
            or any(not cls._valid_step(item, preparation.recovery_adapter_id) for item in steps)
            or preparation.steps_digest != _digest({"steps": [asdict(item) for item in steps]})
            or type(preparation.may_wipe_user_data) is not bool
            or preparation.may_wipe_user_data is not any(item.may_wipe_user_data for item in steps)
            or type(preparation.recorded_prewrite_slot_required) is not bool
            or preparation.recorded_prewrite_slot_required
            is not any(item.target_slot == "recorded_prewrite" for item in steps)
            or preparation.guardian_validation_required is not True
            or preparation.user_confirmation_required is not True
            or preparation.execution_authority != "none"
            or preparation.runtime_invoked is not False
            or preparation.phone_changed is not False
            or preparation.bootloader_relock_allowed is not False
            or preparation.preparation_status != cls.STATUS
            or not _hex(digest, 64)
            or digest != _digest(payload)
        ):
            raise GuardianRecoveryPreparationError(
                "Guardian Recovery preparation failed strict validation"
            )

    def _current_context(
        self,
        incident_id: str,
        route_id: str,
        devices: tuple[AndroidDevice, ...] | list[AndroidDevice],
    ) -> tuple[RecoveryIncident, RecoveryRoute, AndroidDevice]:
        candidates: list[AndroidDevice] = []
        incident = self.autopilot.load(incident_id)
        route = next((item for item in incident.routes if item.route_id == route_id), None)
        if route is None or route.kind not in self.SUPPORTED_ROUTES:
            raise GuardianRecoveryPreparationError(
                "This Recovery route has no exact Guardian preparation contract"
            )
        seen: set[str] = set()
        for device in devices:
            key = self.privacy.pseudonym(device.serial) if device.serial else ""
            if key and key not in seen and hmac.compare_digest(key, incident.device_key):
                candidates.append(device)
                seen.add(key)
        if len(candidates) != 1:
            raise GuardianRecoveryPreparationError(
                "Reconnect the one exact phone involved in this Recovery incident"
            )
        current, current_route = self.autopilot.validate_route_handoff(
            incident.incident_id,
            route.route_id,
            owner_route="guardian_core",
            device=candidates[0],
            require_exact_device=True,
        )
        if (
            current.project_id == ""
            or current.pack_id == ""
            or current.pack_sha256 == ""
            or not current_route.changes_device
            or not current_route.confirmation_required
            or current_route.execution_authority != "none"
        ):
            raise GuardianRecoveryPreparationError(
                "The current Recovery route is not a complete consequential handoff"
            )
        return current, current_route, candidates[0]

    def _matches_current(
        self,
        preparation: GuardianRecoveryPreparation,
        incident: RecoveryIncident,
        route: RecoveryRoute,
        device: AndroidDevice,
    ) -> bool:
        """Rebuild every mutable prerequisite without replacing the sealed record."""

        try:
            project = self.store.get(incident.project_id)
            pack = next(
                (
                    item
                    for item in self.registry.packs
                    if item.pack_id == incident.pack_id
                    and hmac.compare_digest(item.sha256, incident.pack_sha256)
                ),
                None,
            )
            resolution = self.registry.resolve(device)
            if (
                pack is None
                or project.original is None
                or project.device_pack_id != pack.pack_id
                or resolution.pack is None
                or resolution.pack.pack_id != pack.pack_id
                or not hmac.compare_digest(resolution.pack.sha256, pack.sha256)
            ):
                return False
            build = pack.build_contract
            write = build.partition_write_contract if build is not None else None
            transition = write.transition_recovery_contract if write is not None else None
            evidence_record = self.evidence.load(project.project_id)
            if (
                build is None
                or write is None
                or transition is None
                or not self.registry.transition_recovery_contract_is_valid(write, build.source)
                or project.original.sha256 != build.source.archive_sha256
                or transition.recovery.stock_package_sha256 != project.original.sha256
                or evidence_record is None
                or not self.evidence.assess(project.project_id, device).ready
                or evidence_record.record_digest != preparation.recovery_evidence_digest
            ):
                return False
            external_backup = evidence_record.external_backup
            if (
                external_backup is not None
                and external_backup.device_key
                and not hmac.compare_digest(external_backup.device_key, incident.device_key)
            ):
                return False
            focused = self.SUPPORTED_ROUTES.get(route.kind)
            if focused is None:
                return False
            start = next(
                index
                for index, step in enumerate(transition.recovery.actions)
                if step.operation is focused
            )
            current_steps = tuple(
                GuardianPreparedRecoveryStep(
                    order=index,
                    operation=step.operation,
                    adapter_action_id=step.adapter_action_id,
                    from_mode=step.from_mode.value,
                    to_mode=step.to_mode.value,
                    target_slot=step.target_slot,
                    timeout_seconds=step.timeout_seconds,
                    may_wipe_user_data=step.may_wipe_user_data,
                )
                for index, step in enumerate(transition.recovery.actions[start:], 1)
            )
            return bool(
                preparation.incident_id == incident.incident_id
                and preparation.incident_record_digest == incident.record_digest
                and preparation.route_id == route.route_id
                and preparation.route_kind is route.kind
                and preparation.project_id == project.project_id
                and preparation.device_key == incident.device_key
                and preparation.device_name == incident.device_name
                and preparation.expected_product == device.product
                and preparation.expected_entry_mode == current_steps[0].from_mode
                and preparation.source_original_sha256 == project.original.sha256
                and preparation.device_pack_id == pack.pack_id
                and preparation.device_pack_version == pack.version
                and preparation.device_pack_sha256 == pack.sha256
                and preparation.transition_contract_id == transition.contract_id
                and preparation.transition_contract_digest == _digest(asdict(transition))
                and preparation.recovery_strategy == transition.recovery.strategy.value
                and preparation.recovery_adapter_id == transition.recovery.adapter_id
                and preparation.stock_package_sha256 == transition.recovery.stock_package_sha256
                and preparation.focused_operation is focused
                and preparation.steps == current_steps
            )
        except (OSError, ProjectError, StopIteration, TypeError, ValueError):
            return False

    @staticmethod
    def _valid_step(step: GuardianPreparedRecoveryStep, adapter_id: str) -> bool:
        return bool(
            type(step.order) is int
            and 1 <= step.order <= 16
            and isinstance(step.operation, DeviceRecoveryOperation)
            and _clean(step.adapter_action_id, 96)
            and step.adapter_action_id.startswith(f"{adapter_id}.")
            and "relock" not in step.adapter_action_id.casefold()
            and step.from_mode in {"bootloader", "fastbootd", "android"}
            and step.to_mode in {"bootloader", "fastbootd", "android"}
            and step.target_slot in {"none", "recorded_prewrite"}
            and type(step.timeout_seconds) is int
            and 5 <= step.timeout_seconds <= 3600
            and type(step.may_wipe_user_data) is bool
        )

    def _write(self, preparation: GuardianRecoveryPreparation) -> None:
        path = self._path(preparation.incident_id)
        ensure_private_directory(path.parent, boundary=self.store.workspace)
        atomic_write_json(
            path,
            {"format": self.FORMAT, **asdict(preparation)},
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_BYTES,
        )

    def _path(self, incident_id: str) -> Path:
        if not _hex(incident_id, 32):
            raise GuardianRecoveryPreparationError("Recovery incident identifier is invalid")
        return (
            self.store.workspace
            / "diagnostics"
            / "recovery-preparations"
            / incident_id
            / self.LATEST_NAME
        )


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _hex(value: object, length: int) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(rf"[0-9a-f]{{{length}}}", value))


def _clean(value: object, maximum: int) -> bool:
    return bool(
        type(value) is str
        and 1 <= len(value) <= maximum
        and value == value.strip()
        and not any(ord(character) < 32 or ord(character) == 127 for character in value)
    )


def _aware_timestamp(value: object) -> bool:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None
