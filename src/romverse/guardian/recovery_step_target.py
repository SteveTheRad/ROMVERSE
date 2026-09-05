from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from romverse.device.parsers import (
    parse_adb_devices,
    parse_fastboot_devices,
    parse_fastboot_getvar,
)
from romverse.guardian.recovery_execution import (
    GuardianRecoveryExecutionClaim,
    GuardianRecoveryExecutionGrant,
    GuardianRecoveryExecutionService,
    RecoveryExecutionValidationError,
)
from romverse.guardian.recovery_preparation import (
    GuardianPreparedRecoveryStep,
    GuardianRecoveryPreparation,
)
from romverse.infrastructure.local_store import LocalStoreError
from romverse.infrastructure.process import CommandResult
from romverse.rom.models import ProjectError


class RecoveryStepTargetValidationError(ProjectError):
    """Fresh step-bound target evidence was missing, ambiguous, or inconsistent."""


class RecoveryStepTargetPhase(StrEnum):
    PRE_DISPATCH = "pre_dispatch"
    POST_DISPATCH = "post_dispatch"


@dataclass(frozen=True, slots=True)
class GuardianRecoveryStepTargetWitness:
    """Memory-only, read-only target evidence for one exact Recovery step phase."""

    schema_version: int
    witness_id: str
    started_at: str
    completed_at: str
    claim_id: str
    claim_digest: str
    incident_id: str
    preparation_digest: str
    device_key: str
    step_order: int
    adapter_action_id: str
    phase: RecoveryStepTargetPhase
    expected_mode: str
    observed_mode: str
    expected_product: str
    observed_product: str
    observed_unlocked: bool | None
    recorded_prewrite_slot: str
    observed_slot: str
    boot_completed: bool | None
    discovery_pass_count: int
    discovery_pass_digests: tuple[str, ...]
    probe_round_count: int
    probe_evidence_digest: str
    identity_verified: bool
    execution_authority: str
    runtime_invoked: bool
    phone_changed: bool
    witness_digest: str


class GuardianRecoveryStepTargetService:
    """Re-identify the exact target and current mode around every adapter step."""

    SCHEMA_VERSION = 1
    DISCOVERY_PASS_COUNT = 3
    PROBE_ROUND_COUNT = 2
    PROBE_TIMEOUT_SECONDS = 4
    MAX_OBSERVATION_SECONDS = 30

    def __init__(self, executions: GuardianRecoveryExecutionService, *, clock=None) -> None:
        self.executions = executions
        self.adb = executions.live_targets.adb
        self.fastboot = executions.live_targets.fastboot
        self.privacy = executions.preparations.privacy
        self.clock = clock or (lambda: datetime.now(UTC))

    def observe(
        self,
        grant: GuardianRecoveryExecutionGrant,
        preparation: GuardianRecoveryPreparation,
        step_order: int,
        phase: RecoveryStepTargetPhase,
    ) -> GuardianRecoveryStepTargetWitness:
        """Collect fresh exact-target evidence without dispatching a Recovery action."""

        try:
            started = self._now()
            claim = self.executions.validate_grant(
                grant,
                preparation,
                now=started,
            )
            step = self.executions.step(preparation, step_order)
            if not isinstance(phase, RecoveryStepTargetPhase):
                raise RecoveryStepTargetValidationError("Recovery target phase is invalid")
            expected_mode = (
                step.from_mode if phase is RecoveryStepTargetPhase.PRE_DISPATCH else step.to_mode
            )
            discoveries: list[str] = [
                self._discover(expected_mode, grant.target_serial, claim.device_key)
            ]
            rounds: list[dict[str, object]] = []
            for _round_number in range(1, self.PROBE_ROUND_COUNT + 1):
                rounds.append(
                    self._probe(
                        expected_mode,
                        grant.target_serial,
                        preparation,
                        step,
                    )
                )
                discoveries.append(
                    self._discover(expected_mode, grant.target_serial, claim.device_key)
                )
            completed = self._now()
            if (
                completed < started
                or (completed - started).total_seconds() > self.MAX_OBSERVATION_SECONDS
                or len(set(discoveries)) != 1
                or rounds[0] != rounds[1]
            ):
                raise RecoveryStepTargetValidationError(
                    "Recovery target changed during the step-bound observation"
                )
            observed = rounds[0]
            observed_slot = str(observed.get("slot", ""))
            recorded_slot = claim.recorded_prewrite_slot
            if (
                observed.get("mode") != expected_mode
                or observed.get("product") != preparation.expected_product
                or (
                    expected_mode in {"bootloader", "fastbootd"}
                    and observed.get("unlocked") is not True
                )
                or (
                    preparation.recorded_prewrite_slot_required
                    and phase is RecoveryStepTargetPhase.PRE_DISPATCH
                    and observed_slot != recorded_slot
                )
                or (expected_mode == "android" and observed.get("boot_completed") is not True)
            ):
                raise RecoveryStepTargetValidationError(
                    "Recovery target identity, mode, slot, or boot state is not exact"
                )
            payload: dict[str, object] = {
                "schema_version": self.SCHEMA_VERSION,
                "witness_id": uuid4().hex,
                "started_at": started.isoformat(),
                "completed_at": completed.isoformat(),
                "claim_id": claim.claim_id,
                "claim_digest": claim.claim_digest,
                "incident_id": claim.incident_id,
                "preparation_digest": preparation.preparation_digest,
                "device_key": claim.device_key,
                "step_order": step.order,
                "adapter_action_id": step.adapter_action_id,
                "phase": phase,
                "expected_mode": expected_mode,
                "observed_mode": str(observed["mode"]),
                "expected_product": preparation.expected_product,
                "observed_product": str(observed["product"]),
                "observed_unlocked": observed.get("unlocked"),
                "recorded_prewrite_slot": recorded_slot,
                "observed_slot": observed_slot,
                "boot_completed": observed.get("boot_completed"),
                "discovery_pass_count": len(discoveries),
                "discovery_pass_digests": tuple(discoveries),
                "probe_round_count": len(rounds),
                "probe_evidence_digest": _digest({"rounds": rounds}),
                "identity_verified": True,
                "execution_authority": "none",
                "runtime_invoked": False,
                "phone_changed": False,
            }
            witness = GuardianRecoveryStepTargetWitness(
                **payload,
                witness_digest=_digest(payload),
            )
            self.validate(witness, claim, preparation, step, phase)
            return witness
        except RecoveryStepTargetValidationError:
            raise
        except RecoveryExecutionValidationError as exc:
            raise RecoveryStepTargetValidationError(str(exc)) from exc
        except (LocalStoreError, OSError, TypeError, ValueError, KeyError, ProjectError) as exc:
            raise RecoveryStepTargetValidationError(
                "Recovery step target validation failed closed before adapter dispatch"
            ) from exc

    @classmethod
    def validate(
        cls,
        witness: GuardianRecoveryStepTargetWitness,
        claim: GuardianRecoveryExecutionClaim,
        preparation: GuardianRecoveryPreparation,
        step: GuardianPreparedRecoveryStep,
        phase: RecoveryStepTargetPhase,
    ) -> None:
        payload = asdict(witness)
        witness_digest = str(payload.pop("witness_digest", ""))
        started = _timestamp(witness.started_at)
        completed = _timestamp(witness.completed_at)
        expected_mode = (
            step.from_mode if phase is RecoveryStepTargetPhase.PRE_DISPATCH else step.to_mode
        )
        expected_slot = claim.recorded_prewrite_slot
        if (
            type(witness.schema_version) is not int
            or witness.schema_version != cls.SCHEMA_VERSION
            or not _hex(witness.witness_id, 32)
            or completed < started
            or (completed - started).total_seconds() > cls.MAX_OBSERVATION_SECONDS
            or witness.claim_id != claim.claim_id
            or witness.claim_digest != claim.claim_digest
            or witness.incident_id != claim.incident_id
            or witness.preparation_digest != preparation.preparation_digest
            or witness.device_key != claim.device_key
            or witness.step_order != step.order
            or witness.adapter_action_id != step.adapter_action_id
            or witness.phase is not phase
            or witness.expected_mode != expected_mode
            or witness.observed_mode != expected_mode
            or witness.expected_product != preparation.expected_product
            or witness.observed_product != preparation.expected_product
            or (
                expected_mode in {"bootloader", "fastbootd"}
                and witness.observed_unlocked is not True
            )
            or (
                expected_mode == "android"
                and (witness.observed_unlocked is not None or witness.boot_completed is not True)
            )
            or witness.recorded_prewrite_slot != expected_slot
            or (
                preparation.recorded_prewrite_slot_required
                and phase is RecoveryStepTargetPhase.PRE_DISPATCH
                and witness.observed_slot != expected_slot
            )
            or witness.observed_slot not in {"", "a", "b"}
            or type(witness.discovery_pass_count) is not int
            or witness.discovery_pass_count != cls.DISCOVERY_PASS_COUNT
            or len(witness.discovery_pass_digests) != cls.DISCOVERY_PASS_COUNT
            or len(set(witness.discovery_pass_digests)) != 1
            or any(not _hex(item, 64) for item in witness.discovery_pass_digests)
            or type(witness.probe_round_count) is not int
            or witness.probe_round_count != cls.PROBE_ROUND_COUNT
            or not _hex(witness.probe_evidence_digest, 64)
            or witness.identity_verified is not True
            or witness.execution_authority != "none"
            or witness.runtime_invoked is not False
            or witness.phone_changed is not False
            or not _hex(witness_digest, 64)
            or witness_digest != _digest(payload)
        ):
            raise RecoveryStepTargetValidationError(
                "Recovery step target witness failed strict validation"
            )

    def _discover(self, expected_mode: str, serial: str, device_key: str) -> str:
        if not serial or not hmac.compare_digest(self.privacy.pseudonym(serial), device_key):
            raise RecoveryStepTargetValidationError(
                "Recovery execution grant does not identify the exact phone"
            )
        adb_result = self.adb.devices()
        fastboot_result = self.fastboot.devices()
        adb_devices = parse_adb_devices(adb_result.stdout) if adb_result.ok else []
        fastboot_devices = (
            parse_fastboot_devices(fastboot_result.stdout + "\n" + fastboot_result.stderr)
            if fastboot_result.ok
            else []
        )
        if expected_mode == "android":
            exact = [
                item
                for item in adb_devices
                if item.get("serial") == serial and item.get("state") == "device"
            ]
            valid = len(adb_devices) == 1 and len(exact) == 1 and not fastboot_devices
            transport = "adb"
        else:
            exact = [item for item in fastboot_devices if item.get("serial") == serial]
            valid = len(fastboot_devices) == 1 and len(exact) == 1 and not adb_devices
            transport = "fastboot"
        if not valid:
            raise RecoveryStepTargetValidationError(
                "Recovery requires exactly one matching phone in the expected mode"
            )
        return _digest(
            {
                "transport": transport,
                "device_key": device_key,
                "expected_mode": expected_mode,
                "adb_count": len(adb_devices),
                "fastboot_count": len(fastboot_devices),
            }
        )

    def _probe(
        self,
        expected_mode: str,
        serial: str,
        preparation: GuardianRecoveryPreparation,
        step: GuardianPreparedRecoveryStep,
    ) -> dict[str, object]:
        if expected_mode == "android":
            product = self._adb_value(serial, "product", "ro.product.device")
            boot_completed = self._adb_value(
                serial,
                "boot-completed",
                "sys.boot_completed",
            )
            slot = ""
            if preparation.recorded_prewrite_slot_required:
                slot = self._adb_value(serial, "slot", "ro.boot.slot_suffix").removeprefix("_")
            return {
                "mode": "android",
                "product": product,
                "unlocked": None,
                "slot": slot,
                "boot_completed": boot_completed == "1",
                "step": step.order,
            }
        product = self._fastboot_value(serial, "product")
        unlocked = self._fastboot_value(serial, "unlocked")
        userspace = self._fastboot_value(serial, "is-userspace")
        slot = ""
        if preparation.recorded_prewrite_slot_required:
            slot = self._fastboot_value(serial, "current-slot").removeprefix("_")
        mode = "fastbootd" if userspace == "yes" else "bootloader" if userspace == "no" else ""
        return {
            "mode": mode,
            "product": product,
            "unlocked": unlocked == "yes",
            "slot": slot,
            "boot_completed": None,
            "step": step.order,
        }

    def _fastboot_value(self, serial: str, variable: str) -> str:
        result = self.fastboot.getvar(serial, variable, timeout=self.PROBE_TIMEOUT_SECONDS)
        value = parse_fastboot_getvar(result.stdout + "\n" + result.stderr, variable)
        if not result.ok or not _clean(value, 160):
            raise RecoveryStepTargetValidationError(f"Recovery Fastboot probe failed: {variable}")
        return value.casefold()

    def _adb_value(self, serial: str, probe_id: str, property_name: str) -> str:
        result: CommandResult = self.adb.probe(
            serial,
            f"recovery.step.{probe_id}",
            ("shell", "getprop", property_name),
            timeout=self.PROBE_TIMEOUT_SECONDS,
        )
        value = " ".join(result.stdout.replace("\x00", " ").split())[:160]
        if not result.ok or not _clean(value, 160):
            raise RecoveryStepTargetValidationError(f"Recovery Android probe failed: {probe_id}")
        return value.casefold()

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise RecoveryStepTargetValidationError(
                "Recovery step target clock must be timezone-aware"
            )
        return value.astimezone(UTC)


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


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(UTC)


def _hex(value: object, length: int) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(rf"[0-9a-f]{{{length}}}", value))


def _clean(value: object, maximum: int) -> bool:
    return bool(
        isinstance(value, str)
        and 1 <= len(value) <= maximum
        and value == value.strip()
        and not any(ord(character) < 32 or ord(character) == 127 for character in value)
    )
