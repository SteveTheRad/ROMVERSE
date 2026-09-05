from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from romverse.device.adb import AdbClient
from romverse.device.fastboot import FastbootClient
from romverse.device.models import AndroidDevice, DeviceState
from romverse.guardian.live_target_receipt import (
    GuardianLiveTargetProbeResult,
    GuardianLiveTargetReceiptService,
    LiveTargetValidationError,
    _ProbeSpec,
)
from romverse.guardian.recovery_preparation import (
    GuardianRecoveryPreparation,
    GuardianRecoveryPreparationService,
)
from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    ensure_private_directory,
    read_regular_bytes,
    remove_regular_file,
)
from romverse.rom.models import ProjectError


class RecoveryLiveTargetValidationError(ProjectError):
    """Fresh read-only Fastboot evidence did not match one Recovery preparation."""


@dataclass(frozen=True, slots=True)
class GuardianRecoveryLiveTargetReceipt:
    """Short-lived exact-phone evidence for one zero-authority Recovery preparation."""

    schema_version: int
    receipt_id: str
    started_at: str
    completed_at: str
    expires_at: str
    preparation_id: str
    preparation_digest: str
    incident_id: str
    incident_record_digest: str
    route_id: str
    project_id: str
    device_key: str
    source_original_sha256: str
    device_pack_id: str
    device_pack_version: str
    device_pack_sha256: str
    transition_contract_digest: str
    recovery_evidence_digest: str
    steps_digest: str
    expected_entry_mode: str
    observed_entry_mode: str
    expected_product: str
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
    recovery_consent_available: bool
    execution_authority: str
    runtime_invoked: bool
    phone_changed: bool
    receipt_digest: str


class GuardianRecoveryLiveTargetReceiptService(GuardianLiveTargetReceiptService):
    """Observe one exact Fastboot phone for one current Recovery preparation.

    The service inherits only the established read-only discovery/probe mechanics.
    It uses a distinct receipt and storage boundary and cannot consume forward-flash
    consent, authorize a Recovery action, or execute an adapter.
    """

    FORMAT = "romverse.guardian-recovery-live-target-receipt"
    SCHEMA_VERSION = 1
    LATEST_NAME = "live-target.romverse"
    MAX_BYTES = 256 * 1024
    VALIDITY_SECONDS = 120

    def __init__(
        self,
        preparations: GuardianRecoveryPreparationService,
        adb: AdbClient,
        fastboot: FastbootClient,
        *,
        clock=None,
    ) -> None:
        super().__init__(preparations.store, adb, fastboot, clock=clock)
        self.preparations = preparations

    def observe(
        self,
        preparation: GuardianRecoveryPreparation,
        reviewed_device: AndroidDevice,
    ) -> GuardianRecoveryLiveTargetReceipt:
        """Create short-lived evidence using discovery and allowlisted getvar reads only."""

        try:
            self.validate_context(preparation, reviewed_device)
            self._invalidate_existing(preparation.incident_id)
            specs = self._recovery_probe_specs(preparation)
            started = self._now()
            discoveries: list[str] = [
                self._discover(preparation.device_key, reviewed_device.serial)
            ]
            results: list[GuardianLiveTargetProbeResult] = []
            for round_number in range(1, self.PROBE_ROUND_COUNT + 1):
                results.extend(
                    self._probe_round(
                        reviewed_device.serial,
                        specs,
                        round_number,
                        len(results),
                    )
                )
                discoveries.append(self._discover(preparation.device_key, reviewed_device.serial))
            completed = self._now()
            if (
                completed < started
                or (completed - started).total_seconds() > self.MAX_OBSERVATION_SECONDS
            ):
                raise RecoveryLiveTargetValidationError(
                    "Recovery target verification exceeded its bounded observation window"
                )
            if len(set(discoveries)) != 1:
                raise RecoveryLiveTargetValidationError(
                    "The USB transport changed during Recovery target verification"
                )
            observed = self._validate_probe_rounds(
                specs,
                tuple(results),
                preparation.expected_entry_mode,
            )
            current_slot = observed.get("current-slot", "")
            payload: dict[str, object] = {
                "schema_version": self.SCHEMA_VERSION,
                "receipt_id": uuid4().hex,
                "started_at": started.isoformat(),
                "completed_at": completed.isoformat(),
                "expires_at": (completed + timedelta(seconds=self.VALIDITY_SECONDS)).isoformat(),
                "preparation_id": preparation.preparation_id,
                "preparation_digest": preparation.preparation_digest,
                "incident_id": preparation.incident_id,
                "incident_record_digest": preparation.incident_record_digest,
                "route_id": preparation.route_id,
                "project_id": preparation.project_id,
                "device_key": preparation.device_key,
                "source_original_sha256": preparation.source_original_sha256,
                "device_pack_id": preparation.device_pack_id,
                "device_pack_version": preparation.device_pack_version,
                "device_pack_sha256": preparation.device_pack_sha256,
                "transition_contract_digest": preparation.transition_contract_digest,
                "recovery_evidence_digest": preparation.recovery_evidence_digest,
                "steps_digest": preparation.steps_digest,
                "expected_entry_mode": preparation.expected_entry_mode,
                "observed_entry_mode": preparation.expected_entry_mode,
                "expected_product": preparation.expected_product,
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
                "recovery_consent_available": False,
                "execution_authority": "none",
                "runtime_invoked": False,
                "phone_changed": False,
            }
            receipt = GuardianRecoveryLiveTargetReceipt(
                **{
                    key: value
                    for key, value in payload.items()
                    if key not in {"discovery_pass_digests", "probe_results"}
                },
                discovery_pass_digests=tuple(discoveries),
                probe_results=tuple(results),
                receipt_digest=_digest(payload),
            )
            self.validate(receipt, preparation, now=completed)
            self._write_recovery(receipt)
            return receipt
        except RecoveryLiveTargetValidationError:
            raise
        except LiveTargetValidationError as exc:
            raise RecoveryLiveTargetValidationError(str(exc)) from exc
        except (LocalStoreError, OSError, TypeError, ValueError, KeyError, ProjectError) as exc:
            raise RecoveryLiveTargetValidationError(
                "Recovery target verification failed closed before any phone-changing action"
            ) from exc

    def load(
        self,
        preparation: GuardianRecoveryPreparation,
        reviewed_device: AndroidDevice,
        *,
        now: datetime | None = None,
    ) -> GuardianRecoveryLiveTargetReceipt | None:
        try:
            self.validate_context(preparation, reviewed_device)
            data = _read_exact_json(
                self._path(preparation.incident_id),
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            expected = {
                "format",
                *(field.name for field in fields(GuardianRecoveryLiveTargetReceipt)),
            }
            if set(data) != expected or data.pop("format") != self.FORMAT:
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
            receipt = GuardianRecoveryLiveTargetReceipt(
                **data,
                probe_results=tuple(GuardianLiveTargetProbeResult(**item) for item in raw_results),
            )
            self.validate(receipt, preparation, now=now or self._now())
            return receipt
        except (
            RecoveryLiveTargetValidationError,
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
        receipt: GuardianRecoveryLiveTargetReceipt,
        preparation: GuardianRecoveryPreparation,
        *,
        now: datetime | None = None,
    ) -> None:
        try:
            GuardianRecoveryPreparationService.validate(preparation)
            payload = asdict(receipt)
            receipt_digest = str(payload.pop("receipt_digest", ""))
            started = _timestamp(receipt.started_at)
            completed = _timestamp(receipt.completed_at)
            expires = _timestamp(receipt.expires_at)
            checked_at = now or datetime.now(UTC)
            if checked_at.tzinfo is None or checked_at.utcoffset() is None:
                raise RecoveryLiveTargetValidationError(
                    "Recovery live-target validation time must be timezone-aware"
                )
            checked_at = checked_at.astimezone(UTC)
            specs = cls._recovery_probe_specs(preparation)
            observed = cls._validate_probe_rounds(
                specs,
                receipt.probe_results,
                preparation.expected_entry_mode,
            )
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
                or receipt.preparation_id != preparation.preparation_id
                or receipt.preparation_digest != preparation.preparation_digest
                or receipt.incident_id != preparation.incident_id
                or receipt.incident_record_digest != preparation.incident_record_digest
                or receipt.route_id != preparation.route_id
                or receipt.project_id != preparation.project_id
                or receipt.device_key != preparation.device_key
                or receipt.source_original_sha256 != preparation.source_original_sha256
                or receipt.device_pack_id != preparation.device_pack_id
                or receipt.device_pack_version != preparation.device_pack_version
                or receipt.device_pack_sha256 != preparation.device_pack_sha256
                or receipt.transition_contract_digest != preparation.transition_contract_digest
                or receipt.recovery_evidence_digest != preparation.recovery_evidence_digest
                or receipt.steps_digest != preparation.steps_digest
                or receipt.expected_entry_mode != preparation.expected_entry_mode
                or receipt.observed_entry_mode != preparation.expected_entry_mode
                or receipt.expected_product != preparation.expected_product
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
                or receipt.recovery_consent_available is not False
                or receipt.execution_authority != "none"
                or receipt.runtime_invoked is not False
                or receipt.phone_changed is not False
                or not _hex(receipt_digest, 64)
                or receipt_digest != _digest(payload)
            ):
                raise RecoveryLiveTargetValidationError(
                    "Recovery live-target receipt failed strict validation"
                )
        except RecoveryLiveTargetValidationError:
            raise
        except (TypeError, ValueError, KeyError, ProjectError, LiveTargetValidationError) as exc:
            raise RecoveryLiveTargetValidationError(
                "Recovery live-target receipt failed strict validation"
            ) from exc

    def validate_context(
        self,
        preparation: GuardianRecoveryPreparation,
        reviewed_device: AndroidDevice,
    ) -> None:
        """Revalidate the current preparation and scanned mode without contacting a phone."""

        try:
            self._validate_preparation(preparation, reviewed_device)
        except RecoveryLiveTargetValidationError:
            raise
        except (LocalStoreError, OSError, TypeError, ValueError, KeyError, ProjectError) as exc:
            raise RecoveryLiveTargetValidationError(
                str(exc) or "Recovery preparation no longer matches current evidence"
            ) from exc

    def _validate_preparation(
        self,
        preparation: GuardianRecoveryPreparation,
        reviewed_device: AndroidDevice,
    ) -> None:
        GuardianRecoveryPreparationService.validate(preparation)
        current = self.preparations.load(
            preparation.incident_id,
            preparation.route_id,
            [reviewed_device],
        )
        if current != preparation:
            raise RecoveryLiveTargetValidationError(
                "Recovery preparation no longer matches current incident evidence"
            )
        if (
            not _clean(reviewed_device.serial, 256)
            or self.privacy.pseudonym(reviewed_device.serial) != preparation.device_key
            or reviewed_device.product != preparation.expected_product
            or not reviewed_device.is_fastboot
            or (
                preparation.expected_entry_mode == "fastbootd"
                and reviewed_device.state is not DeviceState.FASTBOOTD
            )
            or (
                preparation.expected_entry_mode == "bootloader"
                and reviewed_device.state not in {DeviceState.FASTBOOT, DeviceState.BOOTLOADER}
            )
        ):
            raise RecoveryLiveTargetValidationError(
                "The selected phone is not the exact prepared Recovery target"
            )

    @staticmethod
    def _recovery_probe_specs(
        preparation: GuardianRecoveryPreparation,
    ) -> tuple[_ProbeSpec, ...]:
        mode_value = "yes" if preparation.expected_entry_mode == "fastbootd" else "no"
        specs = [
            _ProbeSpec("product", preparation.expected_product),
            _ProbeSpec("unlocked", "yes"),
            _ProbeSpec("is-userspace", mode_value),
        ]
        if preparation.recorded_prewrite_slot_required:
            specs.append(_ProbeSpec("current-slot", "a-or-b"))
        return tuple(specs)

    def _write_recovery(self, receipt: GuardianRecoveryLiveTargetReceipt) -> None:
        path = self._path(receipt.incident_id)
        ensure_private_directory(path.parent, boundary=self.store.workspace)
        atomic_write_json(
            path,
            {"format": self.FORMAT, **asdict(receipt)},
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_BYTES,
        )

    def _invalidate_existing(self, incident_id: str) -> None:
        remove_regular_file(
            self._path(incident_id),
            boundary=self.store.workspace,
            missing_ok=True,
        )

    def _path(self, incident_id: str) -> Path:
        if not _hex(incident_id, 32):
            raise RecoveryLiveTargetValidationError("Recovery incident identifier is invalid")
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


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(UTC)


def _hex(value: object, length: int) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(rf"[0-9a-f]{{{length}}}", value))


def _clean(value: object, maximum: int) -> bool:
    return bool(
        type(value) is str
        and 1 <= len(value) <= maximum
        and value == value.strip()
        and not any(ord(character) < 32 or ord(character) == 127 for character in value)
    )


def _read_exact_json(path: Path, *, boundary: Path, maximum_bytes: int) -> dict[str, object]:
    encoded = read_regular_bytes(path, boundary=boundary, maximum_bytes=maximum_bytes)

    def pairs(values: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in values:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    payload = json.loads(encoded.decode("utf-8"), object_pairs_hook=pairs)
    if not isinstance(payload, dict):
        raise ValueError("receipt must be a JSON object")
    return payload
