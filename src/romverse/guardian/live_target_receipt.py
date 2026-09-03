from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from romverse.core.privacy import WorkspacePrivacy
from romverse.device.adb import AdbClient
from romverse.device.fastboot import FastbootClient
from romverse.device.models import AndroidDevice
from romverse.device.parsers import (
    parse_adb_devices,
    parse_fastboot_devices,
    parse_fastboot_getvar,
)
from romverse.guardian.execution_gateway_contract import (
    GatewayEvidenceKind,
    GatewayStepPhase,
    GatewayTransport,
    GuardianExecutionGatewayContract,
    GuardianExecutionGatewayContractService,
)
from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    ensure_private_directory,
    read_regular_bytes,
    remove_regular_file,
)
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore


@dataclass(frozen=True, slots=True)
class GuardianLiveTargetProbeResult:
    """One normalized read-only value; raw tool output is never retained."""

    order: int
    round: int
    variable: str
    expected_value: str
    observed_value: str
    matched: bool
    evidence_sha256: str
    result_digest: str


@dataclass(frozen=True, slots=True)
class GuardianLiveTargetReceipt:
    """Short-lived local evidence that one live target matches one exact gateway."""

    schema_version: int
    receipt_id: str
    started_at: str
    completed_at: str
    expires_at: str
    gateway_contract_digest: str
    project_id: str
    plan_digest: str
    manifest_digest: str
    artifact_binding_digest: str
    device_key: str
    device_pack_id: str
    device_pack_version: str
    device_pack_sha256: str
    reviewed_build_id_sha256: str
    reviewed_build_fingerprint_sha256: str
    expected_entry_mode: str
    observed_entry_mode: str
    observed_product: str
    observed_unlocked: bool
    recorded_prewrite_slot: str
    discovery_pass_count: int
    discovery_pass_digests: tuple[str, ...]
    probe_round_count: int
    probe_result_count: int
    probe_results_digest: str
    probe_results: tuple[GuardianLiveTargetProbeResult, ...]
    identity_verified: bool
    cryptographic_device_attestation: bool
    final_consent_available: bool
    execution_authority: str
    runtime_invoked: bool
    phone_changed: bool
    receipt_digest: str


class LiveTargetValidationError(ProjectError):
    """The selected live target failed an exact, read-only safety boundary."""


@dataclass(frozen=True, slots=True)
class _ProbeSpec:
    variable: str
    expected_value: str


class GuardianLiveTargetReceiptService:
    """Re-identify a selected Fastboot target without changing or attesting the phone.

    This service deliberately has no write, reboot, unlock, relock, consent, signing, or
    execution method. It samples both discovery transports three times around two identical
    rounds of allowlisted ``fastboot getvar`` probes. The resulting local receipt is useful
    only while fresh and only as one independently revalidated prerequisite for a later,
    separately trusted runtime.
    """

    FORMAT = "romverse.guardian-live-target-receipt"
    SCHEMA_VERSION = 1
    LATEST_NAME = "live-target-receipt.romverse"
    MAX_BYTES = 256 * 1024
    DISCOVERY_PASS_COUNT = 3
    PROBE_ROUND_COUNT = 2
    VALIDITY_SECONDS = 120
    MAX_OBSERVATION_SECONDS = 60
    STATUS_AUTHORITY = "none"

    def __init__(
        self,
        store: RomProjectStore,
        adb: AdbClient,
        fastboot: FastbootClient,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self.adb = adb
        self.fastboot = fastboot
        self.privacy = WorkspacePrivacy(store.workspace)
        self.clock = clock or (lambda: datetime.now(UTC))

    def observe(
        self,
        gateway: GuardianExecutionGatewayContract,
        reviewed_device: AndroidDevice,
    ) -> GuardianLiveTargetReceipt:
        """Run only read-only identity probes and seal a short-lived local receipt."""

        try:
            GuardianExecutionGatewayContractService.validate(gateway)
            self.store.get(gateway.project_id)
            self._invalidate_existing(gateway.project_id)
            self._validate_reviewed_device(gateway, reviewed_device)
            expected_mode = self._expected_entry_mode(gateway)
            specs = self._probe_specs(gateway, expected_mode)
            started = self._now()

            discoveries: list[str] = []
            results: list[GuardianLiveTargetProbeResult] = []
            discoveries.append(self._discover(gateway, reviewed_device.serial))
            for round_number in range(1, self.PROBE_ROUND_COUNT + 1):
                results.extend(
                    self._probe_round(reviewed_device.serial, specs, round_number, len(results))
                )
                discoveries.append(self._discover(gateway, reviewed_device.serial))

            completed = self._now()
            if (
                completed < started
                or (completed - started).total_seconds() > self.MAX_OBSERVATION_SECONDS
            ):
                raise LiveTargetValidationError(
                    "Live-target verification exceeded its bounded observation window"
                )
            if len(set(discoveries)) != 1:
                raise LiveTargetValidationError(
                    "The USB transport changed during live-target verification"
                )

            observed = self._validate_probe_rounds(specs, tuple(results), expected_mode)
            current_slot = observed.get("current-slot", "")
            payload: dict[str, object] = {
                "schema_version": self.SCHEMA_VERSION,
                "receipt_id": uuid4().hex,
                "started_at": started.isoformat(),
                "completed_at": completed.isoformat(),
                "expires_at": (completed + timedelta(seconds=self.VALIDITY_SECONDS)).isoformat(),
                "gateway_contract_digest": gateway.contract_digest,
                "project_id": gateway.project_id,
                "plan_digest": gateway.plan_digest,
                "manifest_digest": gateway.manifest_digest,
                "artifact_binding_digest": gateway.artifact_binding_digest,
                "device_key": gateway.device_key,
                "device_pack_id": gateway.device_pack_id,
                "device_pack_version": gateway.device_pack_version,
                "device_pack_sha256": gateway.device_pack_sha256,
                "reviewed_build_id_sha256": _text_digest(reviewed_device.build_id),
                "reviewed_build_fingerprint_sha256": _text_digest(
                    reviewed_device.build_fingerprint
                ),
                "expected_entry_mode": expected_mode,
                "observed_entry_mode": expected_mode,
                "observed_product": observed["product"],
                "observed_unlocked": observed["unlocked"].casefold() == "yes",
                "recorded_prewrite_slot": current_slot,
                "discovery_pass_count": len(discoveries),
                "discovery_pass_digests": discoveries,
                "probe_round_count": self.PROBE_ROUND_COUNT,
                "probe_result_count": len(results),
                "probe_results_digest": _digest(
                    {"probe_results": [asdict(item) for item in results]}
                ),
                "probe_results": [asdict(item) for item in results],
                "identity_verified": True,
                "cryptographic_device_attestation": False,
                "final_consent_available": False,
                "execution_authority": self.STATUS_AUTHORITY,
                "runtime_invoked": False,
                "phone_changed": False,
            }
            receipt = GuardianLiveTargetReceipt(
                **{
                    key: value
                    for key, value in payload.items()
                    if key not in {"discovery_pass_digests", "probe_results"}
                },
                discovery_pass_digests=tuple(discoveries),
                probe_results=tuple(results),
                receipt_digest=_digest(payload),
            )
            self.validate(receipt, gateway, reviewed_device, now=completed)
            self._write(receipt)
            return receipt
        except LiveTargetValidationError:
            raise
        except (LocalStoreError, OSError, TypeError, ValueError, KeyError, ProjectError) as exc:
            raise LiveTargetValidationError(
                "Live-target verification failed closed before any phone-changing action"
            ) from exc

    def load(
        self,
        gateway: GuardianExecutionGatewayContract,
        reviewed_device: AndroidDevice,
        *,
        now: datetime | None = None,
    ) -> GuardianLiveTargetReceipt | None:
        try:
            self._validate_reviewed_device(gateway, reviewed_device)
            data = _read_exact_json(
                self._root(gateway.project_id) / self.LATEST_NAME,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            expected_fields = {
                "format",
                *(field.name for field in fields(GuardianLiveTargetReceipt)),
            }
            if set(data) != expected_fields or data.pop("format") != self.FORMAT:
                return None
            raw_results = data.pop("probe_results")
            raw_discoveries = data.get("discovery_pass_digests")
            result_fields = {field.name for field in fields(GuardianLiveTargetProbeResult)}
            if (
                not isinstance(raw_results, list)
                or any(
                    not isinstance(item, dict) or set(item) != result_fields for item in raw_results
                )
                or not isinstance(raw_discoveries, list)
                or any(type(item) is not str for item in raw_discoveries)
            ):
                return None
            data["discovery_pass_digests"] = tuple(raw_discoveries)
            receipt = GuardianLiveTargetReceipt(
                **data,
                probe_results=tuple(GuardianLiveTargetProbeResult(**item) for item in raw_results),
            )
            self.validate(receipt, gateway, reviewed_device, now=now or self._now())
            return receipt
        except (
            LiveTargetValidationError,
            LocalStoreError,
            OSError,
            TypeError,
            ValueError,
            KeyError,
            ProjectError,
            json.JSONDecodeError,
        ):
            return None

    @classmethod
    def validate(
        cls,
        receipt: GuardianLiveTargetReceipt,
        gateway: GuardianExecutionGatewayContract,
        reviewed_device: AndroidDevice,
        *,
        now: datetime | None = None,
    ) -> None:
        try:
            GuardianExecutionGatewayContractService.validate(gateway)
            payload = asdict(receipt)
            receipt_digest = str(payload.pop("receipt_digest", ""))
            if (
                not isinstance(reviewed_device, AndroidDevice)
                or not _clean(reviewed_device.build_id, 160)
                or not _clean(reviewed_device.build_fingerprint, 500)
            ):
                raise LiveTargetValidationError(
                    "Live-target receipt lacks its reviewed Android build identity"
                )
            started = _timestamp(receipt.started_at)
            completed = _timestamp(receipt.completed_at)
            expires = _timestamp(receipt.expires_at)
            checked_at = now or datetime.now(UTC)
            if checked_at.tzinfo is None or checked_at.utcoffset() is None:
                raise LiveTargetValidationError(
                    "Live-target validation time must be timezone-aware"
                )
            checked_at = checked_at.astimezone(UTC)
            expected_mode = cls._expected_entry_mode(gateway)
            specs = cls._probe_specs(gateway, expected_mode)
            observed = cls._validate_probe_rounds(specs, receipt.probe_results, expected_mode)
            expected_slot = observed.get("current-slot", "")
            if (
                type(receipt.schema_version) is not int
                or receipt.schema_version != cls.SCHEMA_VERSION
                or not _hex(receipt.receipt_id, 32)
                or completed < started
                or (completed - started).total_seconds() > cls.MAX_OBSERVATION_SECONDS
                or expires != completed + timedelta(seconds=cls.VALIDITY_SECONDS)
                or checked_at < completed
                or checked_at > expires
                or receipt.gateway_contract_digest != gateway.contract_digest
                or receipt.project_id != gateway.project_id
                or receipt.plan_digest != gateway.plan_digest
                or receipt.manifest_digest != gateway.manifest_digest
                or receipt.artifact_binding_digest != gateway.artifact_binding_digest
                or receipt.device_key != gateway.device_key
                or receipt.device_pack_id != gateway.device_pack_id
                or receipt.device_pack_version != gateway.device_pack_version
                or receipt.device_pack_sha256 != gateway.device_pack_sha256
                or receipt.reviewed_build_id_sha256 != _text_digest(reviewed_device.build_id)
                or receipt.reviewed_build_fingerprint_sha256
                != _text_digest(reviewed_device.build_fingerprint)
                or receipt.expected_entry_mode != expected_mode
                or receipt.observed_entry_mode != expected_mode
                or receipt.observed_product != observed["product"]
                or receipt.observed_unlocked is not True
                or receipt.recorded_prewrite_slot != expected_slot
                or type(receipt.discovery_pass_count) is not int
                or receipt.discovery_pass_count != cls.DISCOVERY_PASS_COUNT
                or len(receipt.discovery_pass_digests) != cls.DISCOVERY_PASS_COUNT
                or len(set(receipt.discovery_pass_digests)) != 1
                or any(not _hex(item, 64) for item in receipt.discovery_pass_digests)
                or type(receipt.probe_round_count) is not int
                or receipt.probe_round_count != cls.PROBE_ROUND_COUNT
                or type(receipt.probe_result_count) is not int
                or receipt.probe_result_count != len(receipt.probe_results)
                or receipt.probe_result_count != len(specs) * cls.PROBE_ROUND_COUNT
                or receipt.probe_results_digest
                != _digest({"probe_results": [asdict(item) for item in receipt.probe_results]})
                or receipt.identity_verified is not True
                or receipt.cryptographic_device_attestation is not False
                or receipt.final_consent_available is not False
                or receipt.execution_authority != cls.STATUS_AUTHORITY
                or receipt.runtime_invoked is not False
                or receipt.phone_changed is not False
                or not _hex(receipt_digest, 64)
                or receipt_digest != _digest(payload)
            ):
                raise LiveTargetValidationError("Live-target receipt failed strict validation")
        except LiveTargetValidationError:
            raise
        except (TypeError, ValueError, KeyError, ProjectError) as exc:
            raise LiveTargetValidationError("Live-target receipt failed strict validation") from exc

    def _discover(self, gateway: GuardianExecutionGatewayContract, serial: str) -> str:
        adb_result = self.adb.devices()
        fastboot_result = self.fastboot.devices()
        if not adb_result.ok or not fastboot_result.ok:
            raise LiveTargetValidationError("A required read-only discovery pass failed")
        adb_devices = parse_adb_devices(adb_result.stdout)
        fastboot_devices = parse_fastboot_devices(
            fastboot_result.stdout + "\n" + fastboot_result.stderr
        )
        if adb_devices or len(fastboot_devices) != 1:
            raise LiveTargetValidationError(
                "Live-target verification requires exactly one Fastboot device and no ADB target"
            )
        found = fastboot_devices[0]
        if (
            found["serial"] != serial
            or self.privacy.pseudonym(found["serial"]) != gateway.device_key
        ):
            raise LiveTargetValidationError(
                "The connected Fastboot target is not the reviewed device"
            )
        stable_metadata = {
            key: value
            for key, value in found.items()
            if key not in {"serial"} and _clean(key, 64) and _clean(value, 256)
        }
        transport_token = self.privacy.pseudonym(
            json.dumps(
                {"serial": serial, "metadata": stable_metadata},
                sort_keys=True,
                separators=(",", ":"),
            ),
            length=64,
        )
        return _digest(
            {
                "device_key": gateway.device_key,
                "transport": "usb-fastboot",
                "transport_token": transport_token,
            }
        )

    def _probe_round(
        self,
        serial: str,
        specs: tuple[_ProbeSpec, ...],
        round_number: int,
        start_order: int,
    ) -> tuple[GuardianLiveTargetProbeResult, ...]:
        results: list[GuardianLiveTargetProbeResult] = []
        for offset, spec in enumerate(specs, 1):
            command = self.fastboot.getvar(serial, spec.variable)
            value = parse_fastboot_getvar(
                command.stdout + "\n" + command.stderr,
                spec.variable,
            )
            if not command.ok or not value:
                raise LiveTargetValidationError(
                    f"Required read-only Fastboot probe failed: {spec.variable}"
                )
            if spec.variable == "current-slot":
                value = value.casefold().removeprefix("_")
                matched = value in {"a", "b"}
            else:
                matched = value == spec.expected_value
            if not matched:
                raise LiveTargetValidationError(
                    f"The connected target does not match the reviewed {spec.variable} requirement"
                )
            payload: dict[str, object] = {
                "order": start_order + offset,
                "round": round_number,
                "variable": spec.variable,
                "expected_value": spec.expected_value,
                "observed_value": value,
                "matched": True,
                "evidence_sha256": _digest(
                    {
                        "variable": spec.variable,
                        "value": value,
                        "returncode": command.returncode,
                        "timed_out": command.timed_out,
                    }
                ),
            }
            results.append(
                GuardianLiveTargetProbeResult(
                    **payload,
                    result_digest=_digest(payload),
                )
            )
        return tuple(results)

    @classmethod
    def _probe_specs(
        cls,
        gateway: GuardianExecutionGatewayContract,
        expected_mode: str,
    ) -> tuple[_ProbeSpec, ...]:
        ordered: list[_ProbeSpec] = []
        by_variable: dict[str, str] = {}
        for step in gateway.steps:
            if step.phone_changes:
                break
            if step.phase is not GatewayStepPhase.PRECONDITION:
                continue
            if (
                step.evidence_kind is not GatewayEvidenceKind.FASTBOOT_VARIABLE_EQUALS
                or step.arguments[-2] != "getvar"
            ):
                raise LiveTargetValidationError(
                    "The gateway entry preconditions are not supported by read-only re-identification"
                )
            variable = step.arguments[-1]
            prior = by_variable.get(variable)
            if prior is not None and prior != step.expected_value:
                raise LiveTargetValidationError("Gateway entry preconditions conflict")
            if prior is None:
                by_variable[variable] = step.expected_value
                ordered.append(_ProbeSpec(variable, step.expected_value))

        mode_value = "yes" if expected_mode == "fastbootd" else "no"
        mandatory = (
            _ProbeSpec("product", by_variable.get("product", "")),
            _ProbeSpec("unlocked", "yes"),
            _ProbeSpec("is-userspace", mode_value),
        )
        for spec in mandatory:
            if not spec.expected_value:
                raise LiveTargetValidationError(
                    f"The gateway is missing the exact {spec.variable} identity requirement"
                )
            existing = by_variable.get(spec.variable)
            if existing is not None and existing != spec.expected_value:
                raise LiveTargetValidationError(
                    f"The gateway {spec.variable} requirement conflicts with its entry mode"
                )
            if existing is None:
                by_variable[spec.variable] = spec.expected_value
                ordered.append(spec)
        if gateway.recovery_require_prewrite_slot_capture:
            ordered.append(_ProbeSpec("current-slot", "a-or-b"))
        return tuple(ordered)

    @classmethod
    def _validate_probe_rounds(
        cls,
        specs: tuple[_ProbeSpec, ...],
        results: tuple[GuardianLiveTargetProbeResult, ...],
        expected_mode: str,
    ) -> dict[str, str]:
        expected_pairs = tuple(
            (round_number, spec)
            for round_number in range(1, cls.PROBE_ROUND_COUNT + 1)
            for spec in specs
        )
        if len(results) != len(expected_pairs):
            raise LiveTargetValidationError("Live-target probe sequence is incomplete")
        rounds: dict[int, dict[str, str]] = {}
        for order, (result, pair) in enumerate(zip(results, expected_pairs, strict=True), 1):
            round_number, spec = pair
            unsigned = asdict(result)
            result_digest = str(unsigned.pop("result_digest", ""))
            matched = (
                result.observed_value in {"a", "b"}
                if spec.variable == "current-slot"
                else result.observed_value == spec.expected_value
            )
            if (
                type(result.order) is not int
                or result.order != order
                or type(result.round) is not int
                or result.round != round_number
                or result.variable != spec.variable
                or result.expected_value != spec.expected_value
                or not _clean(result.observed_value, 160)
                or result.matched is not True
                or not matched
                or not _hex(result.evidence_sha256, 64)
                or not _hex(result_digest, 64)
                or result_digest != _digest(unsigned)
            ):
                raise LiveTargetValidationError("Live-target probe evidence is invalid")
            rounds.setdefault(round_number, {})[spec.variable] = result.observed_value
        if rounds.get(1) != rounds.get(2):
            raise LiveTargetValidationError("Live-target identity changed between probe rounds")
        observed = rounds[1]
        if observed.get("unlocked", "").casefold() != "yes" or observed.get("is-userspace") != (
            "yes" if expected_mode == "fastbootd" else "no"
        ):
            raise LiveTargetValidationError("Live-target mode or unlock state is not safe")
        return observed

    @staticmethod
    def _expected_entry_mode(gateway: GuardianExecutionGatewayContract) -> str:
        if gateway.transition_entry_mode:
            mode = gateway.transition_entry_mode
        else:
            first_change = next((step for step in gateway.steps if step.phone_changes), None)
            if first_change is None:
                raise LiveTargetValidationError("The gateway contains no bounded operation entry")
            mode = (
                "fastbootd"
                if first_change.transport is GatewayTransport.FASTBOOTD
                else "bootloader"
                if first_change.transport is GatewayTransport.FASTBOOT
                else ""
            )
        if mode not in {"bootloader", "fastbootd"}:
            raise LiveTargetValidationError("The gateway entry mode cannot be verified safely")
        return mode

    def _validate_reviewed_device(
        self,
        gateway: GuardianExecutionGatewayContract,
        device: AndroidDevice,
    ) -> None:
        if (
            not _clean(device.serial, 256)
            or self.privacy.pseudonym(device.serial) != gateway.device_key
            or not _clean(device.build_id, 160)
            or not _clean(device.build_fingerprint, 500)
        ):
            raise LiveTargetValidationError(
                "A complete reviewed Android build identity is required before Fastboot re-identification"
            )

    def _write(self, receipt: GuardianLiveTargetReceipt) -> None:
        root = self._root(receipt.project_id)
        ensure_private_directory(root, boundary=self.store.workspace)
        atomic_write_json(
            root / self.LATEST_NAME,
            {"format": self.FORMAT, **asdict(receipt)},
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_BYTES,
        )

    def _invalidate_existing(self, project_id: str) -> None:
        remove_regular_file(
            self._root(project_id) / self.LATEST_NAME,
            boundary=self.store.workspace,
            missing_ok=True,
        )

    def _root(self, project_id: str) -> Path:
        self.store.get(project_id)
        return self.store.projects_root / project_id / "guardian"

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise LiveTargetValidationError("Live-target clock must be timezone-aware")
        return value.astimezone(UTC)


def _text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(UTC)


def _hex(value: object, length: int) -> bool:
    return type(value) is str and re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is not None


def _clean(value: object, maximum: int) -> bool:
    return bool(
        type(value) is str
        and 0 < len(value) <= maximum
        and value == value.strip()
        and not any(ord(character) < 32 or ord(character) == 127 for character in value)
    )


def _read_exact_json(path: Path, *, boundary: Path, maximum_bytes: int) -> dict[str, Any]:
    encoded = read_regular_bytes(path, boundary=boundary, maximum_bytes=maximum_bytes)

    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    payload = json.loads(encoded.decode("utf-8"), object_pairs_hook=pairs)
    if not isinstance(payload, dict):
        raise ValueError("receipt must be a JSON object")
    return payload
