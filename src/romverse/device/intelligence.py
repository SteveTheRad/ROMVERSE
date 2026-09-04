from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from romverse.core.privacy import WorkspacePrivacy
from romverse.device.models import AndroidDevice, DeviceState
from romverse.infrastructure.local_store import LocalStoreError, atomic_write_json, read_json_object
from romverse.rom.source_identity import xiaomi_build_region

if TYPE_CHECKING:
    from romverse.device_packs.models import DevicePack
    from romverse.guardian.execution_result_receipt import (
        GuardianExecutionResultReceipt,
        VerifiedGuardianExecutionResult,
    )


class DeviceIntelligenceError(RuntimeError):
    """A local Device Intelligence timeline could not be trusted or preserved."""


@dataclass(frozen=True, slots=True)
class DevicePassportSnapshot:
    """One privacy-safe, read-only live-device passport observation."""

    schema_version: int
    scan_id: str
    observed_at: str
    device_key: str
    connection_state: str
    transport: str
    display_name: str
    manufacturer: str
    brand: str
    model: str
    product: str
    codename: str
    chipset: str
    region: str
    android_version: str
    firmware_version: str
    security_patch: str
    bootloader_state: str
    verified_boot_state: str
    active_slot: str
    slot_scheme: str
    partition_summary: str
    battery_percent: int | None
    battery_temperature_c: float | None
    storage_total_bytes: int | None
    storage_available_bytes: int | None
    storage_percent_used: int | None
    health_summary: str
    pack_id: str
    pack_version: str
    pack_match_reason: str
    record_digest: str


@dataclass(frozen=True, slots=True)
class DeviceOperationEvent:
    """One verified device-changing event suitable for the private timeline."""

    schema_version: int
    event_id: str
    occurred_at: str
    device_key: str
    event_type: str
    outcome: str
    title: str
    detail: str
    project_id: str
    pack_id: str
    evidence_digest: str
    record_digest: str


class DeviceIntelligenceHistoryStore:
    """Bounded pseudonymous history for Device Atlas passport scans."""

    FORMAT = "romverse.device-intelligence-history"
    OPERATION_FORMAT = "romverse.device-intelligence-operations"
    SCHEMA_VERSION = 1
    PRIVACY = "pseudonymous-local"
    MAX_SNAPSHOTS = 120
    MAX_OPERATIONS = 160
    MAX_BYTES = 2 * 1024 * 1024
    DEDUPE_SECONDS = 15 * 60
    ROOT_FIELDS = {
        "format",
        "schema_version",
        "privacy",
        "snapshots",
        "ledger_digest",
    }
    SNAPSHOT_FIELDS = {field.name for field in fields(DevicePassportSnapshot)}
    OPERATION_ROOT_FIELDS = {
        "format",
        "schema_version",
        "privacy",
        "events",
        "ledger_digest",
    }
    OPERATION_FIELDS = {field.name for field in fields(DeviceOperationEvent)}

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.expanduser().resolve()
        self.root = self.workspace / "device_intelligence"
        self.path = self.root / "passport-history.romverse"
        self.operation_path = self.root / "operation-history.romverse"
        self.privacy = WorkspacePrivacy(self.workspace)

    def record_verified_flash(
        self,
        device_serial: str,
        project_name: str,
        result: VerifiedGuardianExecutionResult,
    ) -> DeviceOperationEvent:
        """Record only a successful result already accepted by Guardian boot evidence."""

        from romverse.guardian.execution_result_receipt import (
            GatewayResultOutcome,
            VerifiedGuardianExecutionResult,
        )

        receipt = result.receipt if isinstance(result, VerifiedGuardianExecutionResult) else None
        if not self._valid_verified_flash(device_serial, result, receipt):
            raise DeviceIntelligenceError(
                "Device Intelligence requires an exact successful Guardian flash result"
            )
        occurred_at = self._utc_timestamp(receipt.completed_at)
        events = self.load_operations()
        existing = next(
            (item for item in events if item.evidence_digest == result.signed_receipt_sha256),
            None,
        )
        if existing is not None:
            return existing
        passed = sum(
            item.outcome is GatewayResultOutcome.PASSED for item in receipt.forward_results
        )
        payload: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "event_id": uuid4().hex[:24],
            "occurred_at": occurred_at,
            "device_key": self.privacy.pseudonym(device_serial),
            "event_type": "flash",
            "outcome": "verified",
            "title": "Verified Guardian flash",
            "detail": self._text(
                f"{project_name or 'ROM project'} • {passed} partition operation(s) passed • "
                "runtime postconditions verified",
                400,
            ),
            "project_id": self._text(receipt.project_id, 80),
            "pack_id": self._text(receipt.device_pack_id, 180),
            "evidence_digest": result.signed_receipt_sha256,
        }
        event = DeviceOperationEvent(**payload, record_digest=self._digest(payload))  # type: ignore[arg-type]
        if device_serial in json.dumps(asdict(event), sort_keys=True):
            raise DeviceIntelligenceError(
                "Device Intelligence operation history contains private identity"
            )
        updated = tuple(
            sorted(
                (event, *events),
                key=lambda item: datetime.fromisoformat(item.occurred_at),
                reverse=True,
            )
        )[: self.MAX_OPERATIONS]
        self._save_operations(updated)
        return event

    def load_operations(
        self,
        *,
        device_serial: str = "",
        limit: int = MAX_OPERATIONS,
    ) -> tuple[DeviceOperationEvent, ...]:
        if not self.operation_path.exists() and not self.operation_path.is_symlink():
            return ()
        try:
            payload = read_json_object(
                self.operation_path,
                boundary=self.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            if (
                set(payload) != self.OPERATION_ROOT_FIELDS
                or payload["format"] != self.OPERATION_FORMAT
                or type(payload["schema_version"]) is not int
                or payload["schema_version"] != self.SCHEMA_VERSION
                or payload["privacy"] != self.PRIVACY
                or not isinstance(payload["events"], list)
                or len(payload["events"]) > self.MAX_OPERATIONS
            ):
                raise ValueError("Device Intelligence operation envelope is invalid")
            unsigned = dict(payload)
            ledger_digest = unsigned.pop("ledger_digest")
            if not self._hex(ledger_digest, 64) or ledger_digest != self._digest(unsigned):
                raise ValueError("Device Intelligence operation digest does not match")
            events = tuple(self._parse_operation(item) for item in payload["events"])
            if len({item.event_id for item in events}) != len(events):
                raise ValueError("Device Intelligence operation identifiers are not unique")
            if (
                tuple(
                    sorted(
                        events,
                        key=lambda item: datetime.fromisoformat(item.occurred_at),
                        reverse=True,
                    )
                )
                != events
            ):
                raise ValueError("Device Intelligence operation timeline is not ordered")
        except (
            LocalStoreError,
            OSError,
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            raise DeviceIntelligenceError(
                f"Device Intelligence operation history is unreadable: {exc}"
            ) from exc
        if device_serial:
            device_key = self.privacy.pseudonym(device_serial)
            events = tuple(item for item in events if item.device_key == device_key)
        bounded = max(0, min(int(limit), self.MAX_OPERATIONS))
        return events[:bounded]

    def record_scan(
        self,
        device: AndroidDevice,
        pack: DevicePack | None = None,
        match_reason: str = "",
        *,
        observed_at: datetime | None = None,
    ) -> DevicePassportSnapshot:
        now = (observed_at or datetime.now(UTC)).astimezone(UTC)
        snapshots = self.load()
        snapshot = self._snapshot(device, pack, match_reason, now)
        encoded_snapshot = json.dumps(asdict(snapshot), sort_keys=True)
        private_values = tuple(
            value for value in (device.serial, device.build_fingerprint) if value
        )
        if any(value in encoded_snapshot for value in private_values):
            raise DeviceIntelligenceError("Device Intelligence history contains private identity")
        previous = next(
            (
                item
                for item in snapshots
                if item.device_key == snapshot.device_key and self._same_observation(snapshot, item)
            ),
            None,
        )
        if previous is not None:
            previous_time = datetime.fromisoformat(previous.observed_at)
            if (now - previous_time).total_seconds() < self.DEDUPE_SECONDS:
                return previous
        updated = (snapshot, *snapshots)[: self.MAX_SNAPSHOTS]
        self._save(updated)
        return snapshot

    def load(
        self,
        *,
        device_serial: str = "",
        limit: int = MAX_SNAPSHOTS,
    ) -> tuple[DevicePassportSnapshot, ...]:
        if not self.path.exists() and not self.path.is_symlink():
            return ()
        try:
            payload = read_json_object(
                self.path,
                boundary=self.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            if (
                set(payload) != self.ROOT_FIELDS
                or payload["format"] != self.FORMAT
                or type(payload["schema_version"]) is not int
                or payload["schema_version"] != self.SCHEMA_VERSION
                or payload["privacy"] != self.PRIVACY
                or not isinstance(payload["snapshots"], list)
                or len(payload["snapshots"]) > self.MAX_SNAPSHOTS
            ):
                raise ValueError("Device Intelligence history envelope is invalid")
            unsigned = dict(payload)
            ledger_digest = unsigned.pop("ledger_digest")
            if not self._hex(ledger_digest, 64) or ledger_digest != self._digest(unsigned):
                raise ValueError("Device Intelligence history digest does not match")
            snapshots = tuple(self._parse(item) for item in payload["snapshots"])
            if len({item.scan_id for item in snapshots}) != len(snapshots):
                raise ValueError("Device Intelligence scan identifiers are not unique")
            if (
                tuple(
                    sorted(
                        snapshots,
                        key=lambda item: datetime.fromisoformat(item.observed_at),
                        reverse=True,
                    )
                )
                != snapshots
            ):
                raise ValueError("Device Intelligence timeline is not ordered")
        except (
            LocalStoreError,
            OSError,
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            raise DeviceIntelligenceError(
                f"Device Intelligence history is unreadable: {exc}"
            ) from exc
        if device_serial:
            device_key = self.privacy.pseudonym(device_serial)
            snapshots = tuple(item for item in snapshots if item.device_key == device_key)
        bounded = max(0, min(int(limit), self.MAX_SNAPSHOTS))
        return snapshots[:bounded]

    def _save(self, snapshots: tuple[DevicePassportSnapshot, ...]) -> None:
        unsigned: dict[str, object] = {
            "format": self.FORMAT,
            "schema_version": self.SCHEMA_VERSION,
            "privacy": self.PRIVACY,
            "snapshots": [asdict(item) for item in snapshots],
        }
        payload = {**unsigned, "ledger_digest": self._digest(unsigned)}
        try:
            atomic_write_json(
                self.path,
                payload,
                boundary=self.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
        except (LocalStoreError, OSError, TypeError, ValueError) as exc:
            raise DeviceIntelligenceError(
                f"Device Intelligence history could not be preserved: {exc}"
            ) from exc

    def _save_operations(self, events: tuple[DeviceOperationEvent, ...]) -> None:
        unsigned: dict[str, object] = {
            "format": self.OPERATION_FORMAT,
            "schema_version": self.SCHEMA_VERSION,
            "privacy": self.PRIVACY,
            "events": [asdict(item) for item in events],
        }
        payload = {**unsigned, "ledger_digest": self._digest(unsigned)}
        try:
            atomic_write_json(
                self.operation_path,
                payload,
                boundary=self.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
        except (LocalStoreError, OSError, TypeError, ValueError) as exc:
            raise DeviceIntelligenceError(
                f"Device Intelligence operation history could not be preserved: {exc}"
            ) from exc

    def _snapshot(
        self,
        device: AndroidDevice,
        pack: DevicePack | None,
        match_reason: str,
        observed_at: datetime,
    ) -> DevicePassportSnapshot:
        payload: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "scan_id": uuid4().hex[:24],
            "observed_at": observed_at.isoformat(),
            "device_key": self.privacy.pseudonym(device.serial),
            "connection_state": self._connection_state(device),
            "transport": self._text(device.transport, 40),
            "display_name": self._text(device.display_name, 120),
            "manufacturer": self._text(device.manufacturer, 80),
            "brand": self._text(device.brand, 80),
            "model": self._text(device.model, 120),
            "product": self._text(device.product, 120),
            "codename": self._text(device.codename, 120),
            "chipset": self._text(device.soc_platform or device.hardware, 160),
            "region": self._text(self._region(device), 80),
            "android_version": self._text(device.android_version, 80),
            "firmware_version": self._text(
                device.rom_display or device.build_id or device.build_incremental,
                180,
            ),
            "security_patch": self._text(device.security_patch, 40),
            "bootloader_state": self._bootloader_state(device),
            "verified_boot_state": self._text(device.verified_boot, 80),
            "active_slot": self._text(device.slot_suffix.removeprefix("_"), 16),
            "slot_scheme": self._slot_scheme(device),
            "partition_summary": self._partition_summary(device, pack),
            "battery_percent": device.battery_percent,
            "battery_temperature_c": device.battery_temperature_c,
            "storage_total_bytes": device.storage.total_bytes,
            "storage_available_bytes": device.storage.available_bytes,
            "storage_percent_used": device.storage.percent_used,
            "health_summary": self._health_summary(device),
            "pack_id": self._text(pack.pack_id if pack is not None else "", 180),
            "pack_version": self._text(pack.version if pack is not None else "", 80),
            "pack_match_reason": self._text(match_reason, 300),
        }
        return DevicePassportSnapshot(**payload, record_digest=self._digest(payload))  # type: ignore[arg-type]

    def _parse(self, value: object) -> DevicePassportSnapshot:
        if not isinstance(value, dict) or set(value) != self.SNAPSHOT_FIELDS:
            raise ValueError("Device Intelligence snapshot fields are invalid")
        payload = dict(value)
        digest = payload.pop("record_digest")
        if not self._hex(digest, 64) or digest != self._digest(payload):
            raise ValueError("Device Intelligence snapshot digest does not match")
        timestamp = datetime.fromisoformat(self._required_text(payload["observed_at"], 80))
        if timestamp.tzinfo is None or timestamp.utcoffset() != timedelta(0):
            raise ValueError("Device Intelligence timestamp requires UTC")
        if (
            type(payload["schema_version"]) is not int
            or payload["schema_version"] != self.SCHEMA_VERSION
            or not self._hex(payload["scan_id"], 24)
            or not self._hex(payload["device_key"], 20)
            or payload["connection_state"]
            not in {
                "connected",
                "authorization-required",
                "offline",
                "recovery",
                "sideload",
                "fastboot",
                "unknown",
            }
            or any(
                not self._valid_optional_text(payload[name], limit)
                for name, limit in (
                    ("transport", 40),
                    ("display_name", 120),
                    ("manufacturer", 80),
                    ("brand", 80),
                    ("model", 120),
                    ("product", 120),
                    ("codename", 120),
                    ("chipset", 160),
                    ("region", 80),
                    ("android_version", 80),
                    ("firmware_version", 180),
                    ("security_patch", 40),
                    ("bootloader_state", 32),
                    ("verified_boot_state", 80),
                    ("active_slot", 16),
                    ("slot_scheme", 80),
                    ("partition_summary", 240),
                    ("health_summary", 240),
                    ("pack_id", 180),
                    ("pack_version", 80),
                    ("pack_match_reason", 300),
                )
            )
            or not self._valid_percent(payload["battery_percent"])
            or not self._valid_temperature(payload["battery_temperature_c"])
            or not self._valid_bytes(payload["storage_total_bytes"])
            or not self._valid_bytes(payload["storage_available_bytes"])
            or not self._valid_percent(payload["storage_percent_used"])
            or (
                type(payload["storage_total_bytes"]) is int
                and type(payload["storage_available_bytes"]) is int
                and payload["storage_available_bytes"] > payload["storage_total_bytes"]
            )
        ):
            raise ValueError("Device Intelligence snapshot contains invalid evidence")
        return DevicePassportSnapshot(**value)

    def _parse_operation(self, value: object) -> DeviceOperationEvent:
        if not isinstance(value, dict) or set(value) != self.OPERATION_FIELDS:
            raise ValueError("Device Intelligence operation fields are invalid")
        payload = dict(value)
        digest = payload.pop("record_digest")
        if not self._hex(digest, 64) or digest != self._digest(payload):
            raise ValueError("Device Intelligence operation record digest does not match")
        occurred_at = self._utc_timestamp(payload["occurred_at"])
        if (
            type(payload["schema_version"]) is not int
            or payload["schema_version"] != self.SCHEMA_VERSION
            or not self._hex(payload["event_id"], 24)
            or not self._hex(payload["device_key"], 20)
            or payload["event_type"] != "flash"
            or payload["outcome"] != "verified"
            or not self._valid_optional_text(payload["title"], 140)
            or not payload["title"]
            or not self._valid_optional_text(payload["detail"], 400)
            or not payload["detail"]
            or not self._valid_optional_text(payload["project_id"], 80)
            or not payload["project_id"]
            or not self._valid_optional_text(payload["pack_id"], 180)
            or not payload["pack_id"]
            or not self._hex(payload["evidence_digest"], 64)
            or occurred_at != payload["occurred_at"]
        ):
            raise ValueError("Device Intelligence operation contains invalid evidence")
        return DeviceOperationEvent(**value)

    def _valid_verified_flash(
        self,
        device_serial: str,
        result: VerifiedGuardianExecutionResult,
        receipt: GuardianExecutionResultReceipt | None,
    ) -> bool:
        from romverse.guardian.execution_result_receipt import (
            ExecutionTerminalState,
            GatewayResultOutcome,
            GuardianExecutionResultReceipt,
            canonical_execution_result_bytes,
            execution_result_digest,
        )

        if not isinstance(receipt, GuardianExecutionResultReceipt):
            return False
        try:
            completed_at = self._utc_timestamp(receipt.completed_at)
        except (TypeError, ValueError):
            return False
        unsigned = asdict(receipt)
        receipt_digest = unsigned.pop("receipt_digest", "")
        signed_receipt = hashlib.sha256(
            canonical_execution_result_bytes(asdict(receipt))
        ).hexdigest()
        return bool(
            device_serial
            and receipt.device_key == self.privacy.pseudonym(device_serial)
            and receipt.terminal_state is ExecutionTerminalState.SUCCEEDED
            and receipt.forward_results
            and receipt.forward_result_count == len(receipt.forward_results)
            and all(item.outcome is GatewayResultOutcome.PASSED for item in receipt.forward_results)
            and receipt.forward_results_digest
            == execution_result_digest(
                {"forward_results": [asdict(item) for item in receipt.forward_results]}
            )
            and receipt.phone_change_attempted
            and receipt.phone_change_verified
            and not receipt.phone_state_uncertain
            and receipt.postconditions_verified
            and result.signer_key_id == receipt.runtime_signer_key_id
            and self._hex(result.signed_receipt_sha256, 64)
            and result.signed_receipt_sha256 == signed_receipt
            and receipt_digest == execution_result_digest(unsigned)
            and bool(completed_at)
        )

    @classmethod
    def _utc_timestamp(cls, value: object) -> str:
        timestamp = datetime.fromisoformat(cls._required_text(value, 80).replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("Device Intelligence timestamp requires a timezone")
        return timestamp.astimezone(UTC).isoformat()

    @staticmethod
    def _same_observation(
        current: DevicePassportSnapshot,
        previous: DevicePassportSnapshot,
    ) -> bool:
        current_payload = asdict(current)
        previous_payload = asdict(previous)
        for field in ("scan_id", "observed_at", "record_digest"):
            current_payload.pop(field)
            previous_payload.pop(field)
        return current_payload == previous_payload

    @staticmethod
    def _connection_state(device: AndroidDevice) -> str:
        if device.state is DeviceState.DEVICE:
            return "connected"
        if device.state is DeviceState.UNAUTHORIZED:
            return "authorization-required"
        if device.state is DeviceState.OFFLINE:
            return "offline"
        if device.state is DeviceState.RECOVERY:
            return "recovery"
        if device.state is DeviceState.SIDELOAD:
            return "sideload"
        if device.is_fastboot:
            return "fastboot"
        return "unknown"

    @staticmethod
    def _region(device: AndroidDevice) -> str:
        for value in (device.build_id, device.build_incremental, device.rom_display):
            region = xiaomi_build_region(value)
            if region:
                return region
        return ""

    @staticmethod
    def _bootloader_state(device: AndroidDevice) -> str:
        if device.bootloader_locked is True:
            return "locked"
        if device.bootloader_locked is False:
            return "unlocked"
        return "unconfirmed"

    @staticmethod
    def _slot_scheme(device: AndroidDevice) -> str:
        if device.virtual_ab is True:
            return "Virtual A/B"
        if device.ab_update is True:
            return "A/B"
        if device.ab_update is False:
            return "Single-slot reported"
        return "Unconfirmed"

    @classmethod
    def _partition_summary(cls, device: AndroidDevice, pack: DevicePack | None) -> str:
        contract = pack.build_contract if pack is not None else None
        if contract is not None:
            return cls._text(
                f"Pack declares {len(contract.partitions)} source-bound partition(s) across "
                f"{len(contract.groups)} dynamic group(s)",
                240,
            )
        if device.dynamic_partitions is True:
            return "Dynamic partitions reported by Android; exact inventory unconfirmed"
        if device.dynamic_partitions is False:
            return "Non-dynamic layout reported by Android; exact inventory unconfirmed"
        return "Exact partition inventory unconfirmed"

    @staticmethod
    def _health_summary(device: AndroidDevice) -> str:
        if device.state is DeviceState.UNAUTHORIZED:
            return "USB authorization is required before Android health can be measured"
        if device.is_fastboot:
            return "Bootloader connection detected; Android health is unavailable"
        if device.state is not DeviceState.DEVICE:
            return "Android health is unavailable in the current connection state"
        concerns: list[str] = []
        if device.errors:
            concerns.append(f"{len(device.errors)} scan limitation(s)")
        if device.battery_percent is not None and device.battery_percent < 20:
            concerns.append("low battery")
        if device.battery_temperature_c is not None and device.battery_temperature_c >= 45:
            concerns.append("high battery temperature")
        if device.storage.percent_used is not None and device.storage.percent_used >= 90:
            concerns.append("storage pressure")
        return (
            "Attention: " + ", ".join(concerns)
            if concerns
            else "No warning found in the current bounded live telemetry"
        )

    @staticmethod
    def _text(value: object, limit: int) -> str:
        return " ".join(str(value or "").replace("\x00", " ").split())[:limit]

    @classmethod
    def _required_text(cls, value: object, limit: int) -> str:
        text = cls._text(value, limit)
        if not text:
            raise ValueError("Required Device Intelligence text is missing")
        return text

    @staticmethod
    def _valid_optional_text(value: object, limit: int) -> bool:
        return isinstance(value, str) and len(value) <= limit and "\x00" not in value

    @staticmethod
    def _valid_percent(value: object) -> bool:
        return value is None or (type(value) is int and 0 <= value <= 100)

    @staticmethod
    def _valid_temperature(value: object) -> bool:
        return value is None or (type(value) in {int, float} and -100 <= float(value) <= 200)

    @staticmethod
    def _valid_bytes(value: object) -> bool:
        return value is None or (type(value) is int and 0 <= value <= 2**63 - 1)

    @staticmethod
    def _hex(value: object, length: int) -> bool:
        return bool(
            isinstance(value, str)
            and len(value) == length
            and all(char in "0123456789abcdef" for char in value)
        )

    @staticmethod
    def _digest(payload: object) -> str:
        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
