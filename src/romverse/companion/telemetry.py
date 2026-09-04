"""Read-only telemetry exchanged with ROMVERSE Companion.

This module intentionally contains no command or device-control fields.  It is a
small, versionable contract that can be transported over ADB or a future local
pairing channel without giving telemetry messages execution authority.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

_FORBIDDEN_REMOTE_FIELDS = frozenset(
    {
        "account",
        "accounts",
        "action",
        "app_list",
        "approval",
        "command",
        "files",
        "imei",
        "packages",
        "serial",
        "shell",
    }
)


def _bounded_text(payload: Mapping[str, Any], key: str, *, maximum: int = 80) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be text")
    value = value.strip()
    if not value or len(value) > maximum or any(ord(character) < 32 for character in value):
        raise ValueError(f"{key} is invalid")
    return value


def _integer(payload: Mapping[str, Any], key: str, *, minimum: int, maximum: int) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{key} is outside the supported range")
    return value


def _optional_integer(
    payload: Mapping[str, Any], key: str, *, minimum: int, maximum: int
) -> int | None:
    if payload.get(key) is None:
        return None
    return _integer(payload, key, minimum=minimum, maximum=maximum)


def _optional_number(
    payload: Mapping[str, Any], key: str, *, minimum: float, maximum: float
) -> float | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a number")
    number = float(value)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{key} is outside the supported range")
    return number


def _optional_boolean(payload: Mapping[str, Any], key: str) -> bool | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be true, false, or null")
    return value


@dataclass(frozen=True, slots=True)
class ActivityEvent:
    title: str
    detail: str = ""
    timestamp: str = ""

    def to_mapping(self) -> dict[str, str]:
        return {"title": self.title, "detail": self.detail, "timestamp": self.timestamp}


@dataclass(frozen=True, slots=True)
class LiveConsoleTelemetryEvent:
    """One privacy-redacted producer event; it carries no executable operation."""

    event_id: str
    updated_at: str
    source: str
    stage: str
    title: str
    summary: str
    explanation: str
    next_action: str
    state: str
    progress_percent: int
    confidence: str
    guardian_protected: bool

    def __post_init__(self) -> None:
        if (
            not self.event_id
            or len(self.event_id) > 100
            or not self.event_id.replace("-", "").isalnum()
        ):
            raise ValueError("Live Console event id is invalid")
        parsed = datetime.fromisoformat(self.updated_at)
        if parsed.tzinfo is None:
            raise ValueError("Live Console event timestamp needs a timezone")
        for name, value, maximum in (
            ("source", self.source, 80),
            ("stage", self.stage, 100),
            ("title", self.title, 180),
            ("summary", self.summary, 500),
            ("explanation", self.explanation, 1_000),
            ("next_action", self.next_action, 500),
        ):
            if not value or len(value) > maximum or any(ord(character) < 32 for character in value):
                raise ValueError(f"Live Console {name} is invalid")
        if self.state not in {
            "running",
            "succeeded",
            "failed",
            "blocked",
            "attention",
            "information",
        }:
            raise ValueError("Live Console event state is invalid")
        if not 0 <= self.progress_percent <= 100:
            raise ValueError("Live Console event progress is invalid")
        if self.confidence not in {
            "verified",
            "high",
            "medium",
            "low",
            "unconfirmed",
            "not-applicable",
        }:
            raise ValueError("Live Console event confidence is invalid")
        if not self.guardian_protected:
            raise ValueError("Companion Live Console accepts only Guardian-protected events")

    def to_mapping(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RawTerminalTelemetryRecord:
    """One non-executable, privacy-filtered Command Console result."""

    record_id: str
    captured_at: str
    probe_id: str
    title: str
    lines: tuple[str, ...]
    success: bool
    record_digest: str

    def __post_init__(self) -> None:
        if (
            not self.record_id
            or len(self.record_id) > 100
            or not self.record_id.replace("-", "").isalnum()
        ):
            raise ValueError("Raw Terminal record id is invalid")
        parsed = datetime.fromisoformat(self.captured_at)
        if parsed.tzinfo is None:
            raise ValueError("Raw Terminal timestamp needs a timezone")
        if self.probe_id not in {
            "adb-version",
            "device-model",
            "android-version",
            "battery-details",
            "storage-details",
            "verified-boot-state",
        }:
            raise ValueError("Raw Terminal probe is not Link-approved")
        if not self.title or len(self.title) > 80 or any(ord(char) < 32 for char in self.title):
            raise ValueError("Raw Terminal title is invalid")
        if not 1 <= len(self.lines) <= 32:
            raise ValueError("Raw Terminal record has an invalid line count")
        if any(
            not line or len(line) > 240 or any(ord(char) < 32 for char in line)
            for line in self.lines
        ):
            raise ValueError("Raw Terminal line is invalid")
        if not isinstance(self.success, bool):
            raise ValueError("Raw Terminal result state is invalid")
        if len(self.record_digest) != 64 or any(
            char not in "0123456789abcdef" for char in self.record_digest
        ):
            raise ValueError("Raw Terminal record digest is invalid")
        unsigned = {
            "record_id": self.record_id,
            "captured_at": self.captured_at,
            "probe_id": self.probe_id,
            "title": self.title,
            "lines": self.lines,
            "success": self.success,
        }
        expected = hashlib.sha256(
            json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if self.record_digest != expected:
            raise ValueError("Raw Terminal record digest does not match its content")

    def to_mapping(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DeviceDnaCapabilityTelemetry:
    """One bounded, explanation-only Capability Map row for Companion."""

    capability_id: str
    label: str
    state: str
    detail: str

    def __post_init__(self) -> None:
        if (
            not self.capability_id
            or len(self.capability_id) > 80
            or any(
                char not in "abcdefghijklmnopqrstuvwxyz0123456789._-" for char in self.capability_id
            )
        ):
            raise ValueError("Device DNA capability id is invalid")
        for name, value, maximum in (
            ("label", self.label, 100),
            ("detail", self.detail, 500),
        ):
            if not value or len(value) > maximum or any(ord(char) < 32 for char in value):
                raise ValueError(f"Device DNA capability {name} is invalid")
        if self.state not in {"SUPPORTED", "CAUTION", "UNSUPPORTED", "UNCONFIRMED"}:
            raise ValueError("Device DNA capability state is invalid")

    def to_mapping(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CompanionTelemetry:
    """A validated, read-only snapshot suitable for desktop or Android display."""

    schema_version: int = 6
    captured_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    battery_percent: int | None = None
    storage_used_bytes: int | None = None
    storage_total_bytes: int | None = None
    guardian_active: bool = True
    activity: tuple[ActivityEvent, ...] = ()
    ascension_state: str = "no_project"
    ascension_project: str = ""
    ascension_method: str = "none"
    ascension_target_partition: str = ""
    ascension_blocker_count: int = 0
    ascension_phone_changed: bool = False
    ascension_execution_authority: str = "none"
    ascension_stage_number: int = 0
    ascension_stage_title: str = ""
    ascension_next_action: str = ""
    ascension_why: str = ""
    ascension_romverse_action: str = ""
    ascension_manager_state: str = "unavailable"
    ascension_manager_repository: str = ""
    ascension_manager_tag: str = ""
    ascension_manager_asset: str = ""
    ascension_manager_sha256_ref: str = ""
    live_console_events: tuple[LiveConsoleTelemetryEvent, ...] = ()
    live_console_integrity: str = "trusted"
    nexus_status: str = "no-plan"
    nexus_objective: str = "none"
    nexus_current_stage: str = ""
    nexus_research_count: int = 0
    guardian_review_state: str = "unavailable"
    live_console_execution_authority: str = "none"
    raw_terminal_included: bool = False
    raw_terminal_integrity: str = "unavailable"
    raw_terminal_records: tuple[RawTerminalTelemetryRecord, ...] = ()
    device_dna_state: str = "unavailable"
    device_dna_project: str = ""
    device_dna_profile_ref: str = ""
    device_dna_warning_count: int = 0
    device_dna_capabilities: tuple[DeviceDnaCapabilityTelemetry, ...] = ()
    device_dna_execution_authority: str = "none"
    device_dna_bootloader_relock: str = "never"

    def __post_init__(self) -> None:
        if self.schema_version not in {1, 2, 3, 4, 5, 6}:
            raise ValueError("unsupported Companion telemetry schema")
        datetime.fromisoformat(self.captured_at)
        if self.battery_percent is not None and not 0 <= self.battery_percent <= 100:
            raise ValueError("battery_percent must be between 0 and 100")
        for value in (self.storage_used_bytes, self.storage_total_bytes):
            if value is not None and value < 0:
                raise ValueError("storage values cannot be negative")
        if (
            self.storage_used_bytes is not None
            and self.storage_total_bytes is not None
            and self.storage_used_bytes > self.storage_total_bytes
        ):
            raise ValueError("storage used cannot exceed storage total")
        if self.schema_version >= 2:
            if self.ascension_state not in {
                "no_project",
                "not_started",
                "skipped",
                "preparing",
                "blocked",
                "review_ready",
            }:
                raise ValueError("ascension_state is invalid")
            if len(self.ascension_project) > 120 or any(
                ord(character) < 32 for character in self.ascension_project
            ):
                raise ValueError("ascension_project is invalid")
            if self.ascension_method not in {"none", "magisk", "kernelsu_lkm"}:
                raise ValueError("ascension_method is invalid")
            if self.ascension_target_partition not in {
                "",
                "boot",
                "init_boot",
                "recovery",
                "vendor_boot",
            }:
                raise ValueError("ascension_target_partition is invalid")
            if not 0 <= self.ascension_blocker_count <= 100:
                raise ValueError("ascension_blocker_count is invalid")
            if self.ascension_phone_changed:
                raise ValueError("Companion telemetry cannot claim an Ascension phone change")
            if self.ascension_execution_authority != "none":
                raise ValueError("Companion telemetry cannot carry execution authority")
        if self.schema_version >= 3:
            maximum_stage = 7 if self.schema_version == 3 else 9
            if not 0 <= self.ascension_stage_number <= maximum_stage:
                raise ValueError("ascension_stage_number is invalid")
            for name, value, maximum in (
                ("ascension_stage_title", self.ascension_stage_title, 120),
                ("ascension_next_action", self.ascension_next_action, 500),
                ("ascension_why", self.ascension_why, 500),
                ("ascension_romverse_action", self.ascension_romverse_action, 500),
            ):
                if len(value) > maximum or any(ord(character) < 32 for character in value):
                    raise ValueError(f"{name} is invalid")
        if self.schema_version >= 5:
            if len(self.live_console_events) > 8:
                raise ValueError("Companion Live Console is limited to eight events")
            if self.live_console_integrity not in {
                "trusted",
                "needs-attention",
                "unavailable",
            }:
                raise ValueError("Live Console integrity state is invalid")
            if self.nexus_status not in {
                "no-plan",
                "needs-evidence",
                "ready-for-guardian",
            }:
                raise ValueError("Nexus status is invalid")
            if self.nexus_objective not in {
                "none",
                "build-rom",
                "root-rom",
                "flash-device",
            }:
                raise ValueError("Nexus objective is invalid")
            if len(self.nexus_current_stage) > 120 or any(
                ord(character) < 32 for character in self.nexus_current_stage
            ):
                raise ValueError("Nexus current stage is invalid")
            if not 0 <= self.nexus_research_count <= 100:
                raise ValueError("Nexus research count is invalid")
            if self.guardian_review_state not in {"unavailable", "blocked", "ready"}:
                raise ValueError("Guardian review state is invalid")
            if self.live_console_execution_authority != "none":
                raise ValueError("Companion Live Console cannot carry execution authority")
            if self.schema_version == 5 and self.raw_terminal_included:
                raise ValueError("Raw terminal output is not authorized in this Link schema")
        if self.schema_version >= 6:
            if self.ascension_manager_state not in {"unavailable", "verified"}:
                raise ValueError("Ascension manager state is invalid")
            manager_values = (
                self.ascension_manager_repository,
                self.ascension_manager_tag,
                self.ascension_manager_asset,
                self.ascension_manager_sha256_ref,
            )
            if self.ascension_manager_state == "unavailable":
                if any(manager_values):
                    raise ValueError("Unavailable Ascension manager cannot carry provenance")
            else:
                expected_repository = {
                    "magisk": "topjohnwu/Magisk",
                    "kernelsu_lkm": "tiann/KernelSU",
                }.get(self.ascension_method)
                if self.ascension_manager_repository != expected_repository:
                    raise ValueError("Ascension manager repository does not match its method")
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", self.ascension_manager_tag):
                    raise ValueError("Ascension manager tag is invalid")
                valid_asset = (
                    bool(
                        re.fullmatch(
                            r"Magisk-v[0-9][A-Za-z0-9._-]*\.apk",
                            self.ascension_manager_asset,
                        )
                    )
                    if self.ascension_method == "magisk"
                    else bool(
                        re.fullmatch(
                            r"KernelSU_v[0-9][A-Za-z0-9._-]*-release\.apk",
                            self.ascension_manager_asset,
                        )
                    )
                )
                if not valid_asset or len(self.ascension_manager_asset) > 120:
                    raise ValueError("Ascension manager asset is invalid")
                if not re.fullmatch(r"[0-9a-f]{16}", self.ascension_manager_sha256_ref):
                    raise ValueError("Ascension manager fingerprint reference is invalid")
            if len(self.raw_terminal_records) > 4:
                raise ValueError("Companion Raw Terminal is limited to four records")
            if self.raw_terminal_integrity not in {
                "verified-local-feed",
                "needs-attention",
                "unavailable",
            }:
                raise ValueError("Raw Terminal integrity state is invalid")
            if self.raw_terminal_included != bool(self.raw_terminal_records):
                raise ValueError("Raw Terminal inclusion marker does not match its records")
            if self.device_dna_state not in {"unavailable", "ready", "needs-attention"}:
                raise ValueError("Device DNA state is invalid")
            if len(self.device_dna_project) > 120 or any(
                ord(character) < 32 for character in self.device_dna_project
            ):
                raise ValueError("Device DNA project is invalid")
            if self.device_dna_profile_ref and (
                len(self.device_dna_profile_ref) != 16
                or any(char not in "0123456789abcdef" for char in self.device_dna_profile_ref)
            ):
                raise ValueError("Device DNA profile reference is invalid")
            if not 0 <= self.device_dna_warning_count <= 100:
                raise ValueError("Device DNA warning count is invalid")
            if len(self.device_dna_capabilities) > 12:
                raise ValueError("Device DNA Capability Map is too large")
            if self.device_dna_execution_authority != "none":
                raise ValueError("Device DNA telemetry cannot carry execution authority")
            if self.device_dna_bootloader_relock != "never":
                raise ValueError("Device DNA telemetry can never authorize bootloader relocking")
            if self.device_dna_state == "unavailable":
                if (
                    self.device_dna_project
                    or self.device_dna_profile_ref
                    or self.device_dna_warning_count
                    or self.device_dna_capabilities
                ):
                    raise ValueError("Unavailable Device DNA cannot carry profile evidence")
            elif (
                not self.device_dna_project
                or not self.device_dna_profile_ref
                or not self.device_dna_capabilities
            ):
                raise ValueError("Available Device DNA requires bounded profile evidence")
        elif (
            self.device_dna_state != "unavailable"
            or self.device_dna_project
            or self.device_dna_profile_ref
            or self.device_dna_warning_count
            or self.device_dna_capabilities
        ):
            raise ValueError("Device DNA telemetry requires Link schema 6")
        elif (
            self.ascension_manager_state != "unavailable"
            or self.ascension_manager_repository
            or self.ascension_manager_tag
            or self.ascension_manager_asset
            or self.ascension_manager_sha256_ref
        ):
            raise ValueError("Ascension manager provenance requires Link schema 6")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "captured_at": self.captured_at,
            "battery_percent": self.battery_percent,
            "storage_used_bytes": self.storage_used_bytes,
            "storage_total_bytes": self.storage_total_bytes,
            "guardian_active": self.guardian_active,
            "activity": [event.to_mapping() for event in self.activity],
            "ascension_state": self.ascension_state,
            "ascension_project": self.ascension_project,
            "ascension_method": self.ascension_method,
            "ascension_target_partition": self.ascension_target_partition,
            "ascension_blocker_count": self.ascension_blocker_count,
            "ascension_phone_changed": self.ascension_phone_changed,
            "ascension_execution_authority": self.ascension_execution_authority,
            "ascension_stage_number": self.ascension_stage_number,
            "ascension_stage_title": self.ascension_stage_title,
            "ascension_next_action": self.ascension_next_action,
            "ascension_why": self.ascension_why,
            "ascension_romverse_action": self.ascension_romverse_action,
            "ascension_manager_state": self.ascension_manager_state,
            "ascension_manager_repository": self.ascension_manager_repository,
            "ascension_manager_tag": self.ascension_manager_tag,
            "ascension_manager_asset": self.ascension_manager_asset,
            "ascension_manager_sha256_ref": self.ascension_manager_sha256_ref,
            "live_console_events": [event.to_mapping() for event in self.live_console_events],
            "live_console_integrity": self.live_console_integrity,
            "nexus_status": self.nexus_status,
            "nexus_objective": self.nexus_objective,
            "nexus_current_stage": self.nexus_current_stage,
            "nexus_research_count": self.nexus_research_count,
            "guardian_review_state": self.guardian_review_state,
            "live_console_execution_authority": self.live_console_execution_authority,
            "raw_terminal_included": self.raw_terminal_included,
            "raw_terminal_integrity": self.raw_terminal_integrity,
            "raw_terminal_records": [record.to_mapping() for record in self.raw_terminal_records],
            "device_dna_state": self.device_dna_state,
            "device_dna_project": self.device_dna_project,
            "device_dna_profile_ref": self.device_dna_profile_ref,
            "device_dna_warning_count": self.device_dna_warning_count,
            "device_dna_capabilities": [
                capability.to_mapping() for capability in self.device_dna_capabilities
            ],
            "device_dna_execution_authority": self.device_dna_execution_authority,
            "device_dna_bootloader_relock": self.device_dna_bootloader_relock,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> CompanionTelemetry:
        """Parse only known read-only fields; ignore unknown future fields."""

        raw_activity = payload.get("activity", ())
        if not isinstance(raw_activity, (list, tuple)):
            raise ValueError("activity must be a list")
        activity = tuple(
            ActivityEvent(
                title=str(item.get("title", "")),
                detail=str(item.get("detail", "")),
                timestamp=str(item.get("timestamp", "")),
            )
            for item in raw_activity
            if isinstance(item, Mapping)
        )
        schema_version = int(payload.get("schema_version", 1))
        raw_console = payload.get("live_console_events", ()) if schema_version >= 5 else ()
        if not isinstance(raw_console, (list, tuple)):
            raise ValueError("live_console_events must be a list")
        console_events = tuple(
            LiveConsoleTelemetryEvent(
                event_id=str(item.get("event_id", "")),
                updated_at=str(item.get("updated_at", "")),
                source=str(item.get("source", "")),
                stage=str(item.get("stage", "")),
                title=str(item.get("title", "")),
                summary=str(item.get("summary", "")),
                explanation=str(item.get("explanation", "")),
                next_action=str(item.get("next_action", "")),
                state=str(item.get("state", "")),
                progress_percent=int(item.get("progress_percent", -1)),
                confidence=str(item.get("confidence", "")),
                guardian_protected=bool(item.get("guardian_protected", False)),
            )
            for item in raw_console
            if isinstance(item, Mapping)
        )
        raw_terminal = payload.get("raw_terminal_records", ()) if schema_version >= 6 else ()
        if not isinstance(raw_terminal, (list, tuple)):
            raise ValueError("raw_terminal_records must be a list")
        terminal_records = tuple(
            RawTerminalTelemetryRecord(
                record_id=str(item.get("record_id", "")),
                captured_at=str(item.get("captured_at", "")),
                probe_id=str(item.get("probe_id", "")),
                title=str(item.get("title", "")),
                lines=tuple(str(line) for line in item.get("lines", ())),
                success=item.get("success"),
                record_digest=str(item.get("record_digest", "")),
            )
            for item in raw_terminal
            if isinstance(item, Mapping) and isinstance(item.get("lines"), (list, tuple))
        )
        raw_device_dna = payload.get("device_dna_capabilities", ()) if schema_version >= 6 else ()
        if not isinstance(raw_device_dna, (list, tuple)):
            raise ValueError("device_dna_capabilities must be a list")
        device_dna_capabilities = tuple(
            DeviceDnaCapabilityTelemetry(
                capability_id=str(item.get("capability_id", "")),
                label=str(item.get("label", "")),
                state=str(item.get("state", "")),
                detail=str(item.get("detail", "")),
            )
            for item in raw_device_dna
            if isinstance(item, Mapping)
        )
        return cls(
            schema_version=schema_version,
            captured_at=str(payload.get("captured_at", datetime.now(UTC).isoformat())),
            battery_percent=payload.get("battery_percent"),
            storage_used_bytes=payload.get("storage_used_bytes"),
            storage_total_bytes=payload.get("storage_total_bytes"),
            guardian_active=bool(payload.get("guardian_active", True)),
            activity=activity,
            ascension_state=(
                str(payload.get("ascension_state", "no_project"))
                if schema_version >= 2
                else "no_project"
            ),
            ascension_project=(
                str(payload.get("ascension_project", "")) if schema_version >= 2 else ""
            ),
            ascension_method=(
                str(payload.get("ascension_method", "none")) if schema_version >= 2 else "none"
            ),
            ascension_target_partition=(
                str(payload.get("ascension_target_partition", "")) if schema_version >= 2 else ""
            ),
            ascension_blocker_count=(
                int(payload.get("ascension_blocker_count", 0)) if schema_version >= 2 else 0
            ),
            ascension_phone_changed=(
                bool(payload.get("ascension_phone_changed", False))
                if schema_version >= 2
                else False
            ),
            ascension_execution_authority=(
                str(payload.get("ascension_execution_authority", "none"))
                if schema_version >= 2
                else "none"
            ),
            ascension_stage_number=(
                int(payload.get("ascension_stage_number", 0)) if schema_version >= 3 else 0
            ),
            ascension_stage_title=(
                str(payload.get("ascension_stage_title", "")) if schema_version >= 3 else ""
            ),
            ascension_next_action=(
                str(payload.get("ascension_next_action", "")) if schema_version >= 3 else ""
            ),
            ascension_why=(str(payload.get("ascension_why", "")) if schema_version >= 3 else ""),
            ascension_romverse_action=(
                str(payload.get("ascension_romverse_action", "")) if schema_version >= 3 else ""
            ),
            ascension_manager_state=(
                str(payload.get("ascension_manager_state", "unavailable"))
                if schema_version >= 6
                else "unavailable"
            ),
            ascension_manager_repository=(
                str(payload.get("ascension_manager_repository", "")) if schema_version >= 6 else ""
            ),
            ascension_manager_tag=(
                str(payload.get("ascension_manager_tag", "")) if schema_version >= 6 else ""
            ),
            ascension_manager_asset=(
                str(payload.get("ascension_manager_asset", "")) if schema_version >= 6 else ""
            ),
            ascension_manager_sha256_ref=(
                str(payload.get("ascension_manager_sha256_ref", "")) if schema_version >= 6 else ""
            ),
            live_console_events=console_events,
            live_console_integrity=(
                str(payload.get("live_console_integrity", "unavailable"))
                if schema_version >= 5
                else "unavailable"
            ),
            nexus_status=(
                str(payload.get("nexus_status", "no-plan")) if schema_version >= 5 else "no-plan"
            ),
            nexus_objective=(
                str(payload.get("nexus_objective", "none")) if schema_version >= 5 else "none"
            ),
            nexus_current_stage=(
                str(payload.get("nexus_current_stage", "")) if schema_version >= 5 else ""
            ),
            nexus_research_count=(
                int(payload.get("nexus_research_count", 0)) if schema_version >= 5 else 0
            ),
            guardian_review_state=(
                str(payload.get("guardian_review_state", "unavailable"))
                if schema_version >= 5
                else "unavailable"
            ),
            live_console_execution_authority=(
                str(payload.get("live_console_execution_authority", "none"))
                if schema_version >= 5
                else "none"
            ),
            raw_terminal_included=(
                bool(payload.get("raw_terminal_included", False)) if schema_version >= 5 else False
            ),
            raw_terminal_integrity=(
                str(payload.get("raw_terminal_integrity", "unavailable"))
                if schema_version >= 6
                else "unavailable"
            ),
            raw_terminal_records=terminal_records,
            device_dna_state=(
                str(payload.get("device_dna_state", "unavailable"))
                if schema_version >= 6
                else "unavailable"
            ),
            device_dna_project=(
                str(payload.get("device_dna_project", "")) if schema_version >= 6 else ""
            ),
            device_dna_profile_ref=(
                str(payload.get("device_dna_profile_ref", "")) if schema_version >= 6 else ""
            ),
            device_dna_warning_count=(
                int(payload.get("device_dna_warning_count", 0)) if schema_version >= 6 else 0
            ),
            device_dna_capabilities=device_dna_capabilities,
            device_dna_execution_authority=(
                str(payload.get("device_dna_execution_authority", "none"))
                if schema_version >= 6
                else "none"
            ),
            device_dna_bootloader_relock=(
                str(payload.get("device_dna_bootloader_relock", "never"))
                if schema_version >= 6
                else "never"
            ),
        )


@dataclass(frozen=True, slots=True)
class RemoteCompanionSnapshot:
    """Privacy-bounded health telemetry submitted by an authenticated Companion.

    This contract deliberately has no serial number, IMEI, account, package,
    file, command, shell, or approval fields. Receiving it cannot authorize an
    operation on either device.
    """

    captured_at_epoch_ms: int
    manufacturer: str
    model: str
    device_codename: str
    android_version: str
    sdk_int: int
    companion_version: str
    battery_percent: int | None = None
    storage_used_bytes: int | None = None
    storage_total_bytes: int | None = None
    memory_available_bytes: int | None = None
    memory_total_bytes: int | None = None
    health_score: int | None = None
    battery_temperature_celsius: float | None = None
    network_validated: bool | None = None
    usb_connected: bool | None = None
    vitalis_state: str = "UNCONFIRMED"
    vitalis_evidence_percent: int = 0
    kernel_release: str = "unknown"
    root_signal: str = "unknown"
    root_manager_candidate: str = "unknown"
    bootloader_state: str = "unknown"
    kernelsu_support: str = "unknown"
    user_data_backup_state: str = "unconfirmed"
    user_data_backup_confirmed_at_epoch_ms: int | None = None
    backup_confirmation_scope: str = "user_attestation_only"
    backup_execution_authority: str = "none"
    schema_version: int = 2
    guardian_active: bool = True
    privacy_scope: str = "health_and_device_safety"

    def __post_init__(self) -> None:
        if self.schema_version not in {1, 2, 3, 4, 5}:
            raise ValueError("unsupported remote Companion telemetry schema")
        if self.captured_at_epoch_ms <= 0:
            raise ValueError("captured_at_epoch_ms must be positive")
        for name in (
            "manufacturer",
            "model",
            "device_codename",
            "android_version",
            "companion_version",
        ):
            value = getattr(self, name)
            if not value or len(value) > 80 or any(ord(character) < 32 for character in value):
                raise ValueError(f"{name} is invalid")
        if not 1 <= self.sdk_int <= 10_000:
            raise ValueError("sdk_int is outside the supported range")
        if self.battery_percent is not None and (
            isinstance(self.battery_percent, bool)
            or not isinstance(self.battery_percent, int)
            or not 0 <= self.battery_percent <= 100
        ):
            raise ValueError("battery_percent must be an integer between 0 and 100")
        if self.health_score is not None and (
            isinstance(self.health_score, bool)
            or not isinstance(self.health_score, int)
            or not 0 <= self.health_score <= 100
        ):
            raise ValueError("health_score must be an integer between 0 and 100")
        for name in (
            "storage_used_bytes",
            "storage_total_bytes",
            "memory_available_bytes",
            "memory_total_bytes",
        ):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 2**63 - 1
            ):
                raise ValueError(f"{name} is outside the supported range")
        if (
            self.storage_used_bytes is not None
            and self.storage_total_bytes is not None
            and self.storage_used_bytes > self.storage_total_bytes
        ):
            raise ValueError("storage used cannot exceed storage total")
        if (
            self.memory_available_bytes is not None
            and self.memory_total_bytes is not None
            and self.memory_available_bytes > self.memory_total_bytes
        ):
            raise ValueError("available memory cannot exceed total memory")
        if self.guardian_active is not True:
            raise ValueError("remote telemetry requires Guardian to be active")
        expected_scope = "health_only" if self.schema_version == 1 else "health_and_device_safety"
        if self.privacy_scope != expected_scope:
            raise ValueError("unsupported remote telemetry privacy scope")
        if self.schema_version >= 2:
            if (
                not self.kernel_release
                or len(self.kernel_release) > 160
                or any(ord(character) < 32 for character in self.kernel_release)
            ):
                raise ValueError("kernel_release is invalid")
            if self.root_signal not in {"observed", "not_observed", "unknown"}:
                raise ValueError("root_signal is invalid")
            if self.bootloader_state not in {"locked", "unlocked", "unknown"}:
                raise ValueError("bootloader_state is invalid")
            if self.kernelsu_support not in {"supported", "unsupported", "unknown"}:
                raise ValueError("kernelsu_support is invalid")
        if self.schema_version >= 3 and self.root_manager_candidate not in {
            "magisk",
            "kernelsu_lkm",
            "conflict",
            "none",
            "unknown",
        }:
            raise ValueError("root_manager_candidate is invalid")
        if self.schema_version >= 4:
            if self.battery_temperature_celsius is not None and (
                isinstance(self.battery_temperature_celsius, bool)
                or not isinstance(self.battery_temperature_celsius, (int, float))
                or not math.isfinite(self.battery_temperature_celsius)
                or not -20.0 <= self.battery_temperature_celsius <= 100.0
            ):
                raise ValueError("battery_temperature_celsius is invalid")
            if self.network_validated is not None and not isinstance(self.network_validated, bool):
                raise ValueError("network_validated is invalid")
            if self.usb_connected is not None and not isinstance(self.usb_connected, bool):
                raise ValueError("usb_connected is invalid")
            if self.vitalis_state not in {
                "OPTIMAL",
                "ATTENTION",
                "ACTION RECOMMENDED",
                "UNCONFIRMED",
            }:
                raise ValueError("vitalis_state is invalid")
            if (
                isinstance(self.vitalis_evidence_percent, bool)
                or not isinstance(self.vitalis_evidence_percent, int)
                or not 0 <= self.vitalis_evidence_percent <= 100
            ):
                raise ValueError("vitalis_evidence_percent is invalid")
            if (self.storage_used_bytes is None) != (self.storage_total_bytes is None):
                raise ValueError("storage evidence must be a complete pair")
            if (self.memory_available_bytes is None) != (self.memory_total_bytes is None):
                raise ValueError("memory evidence must be a complete pair")
            if self.storage_total_bytes is not None and self.storage_total_bytes <= 0:
                raise ValueError("storage total must be positive")
            if self.memory_total_bytes is not None and self.memory_total_bytes <= 0:
                raise ValueError("memory total must be positive")
            expected_score, expected_state, expected_coverage = self._derived_vitalis()
            if self.health_score != expected_score:
                raise ValueError("health_score does not match Vitalis evidence")
            if self.vitalis_state != expected_state:
                raise ValueError("vitalis_state does not match its evidence")
            if self.vitalis_evidence_percent != expected_coverage:
                raise ValueError("vitalis_evidence_percent does not match its fields")
        if self.schema_version >= 5:
            if self.user_data_backup_state not in {"unconfirmed", "confirmed_by_user"}:
                raise ValueError("user_data_backup_state is invalid")
            confirmed_at = self.user_data_backup_confirmed_at_epoch_ms
            if self.user_data_backup_state == "confirmed_by_user":
                if (
                    isinstance(confirmed_at, bool)
                    or not isinstance(confirmed_at, int)
                    or not 1 <= confirmed_at <= self.captured_at_epoch_ms + 300_000
                ):
                    raise ValueError("user-data backup confirmation is invalid")
            elif confirmed_at is not None:
                raise ValueError("unconfirmed user-data backup cannot have a timestamp")
            if self.backup_confirmation_scope != "user_attestation_only":
                raise ValueError("backup_confirmation_scope is invalid")
            if self.backup_execution_authority != "none":
                raise ValueError("backup confirmation cannot carry execution authority")
        elif (
            self.user_data_backup_state != "unconfirmed"
            or self.user_data_backup_confirmed_at_epoch_ms is not None
            or self.backup_confirmation_scope != "user_attestation_only"
            or self.backup_execution_authority != "none"
        ):
            raise ValueError("user-data backup evidence requires schema 5")

    def _derived_vitalis(self) -> tuple[int | None, str, int]:
        storage_percent = (
            (self.storage_used_bytes * 100) // self.storage_total_bytes
            if self.storage_used_bytes is not None and self.storage_total_bytes is not None
            else None
        )
        ram_percent = (
            ((self.memory_total_bytes - self.memory_available_bytes) * 100)
            // self.memory_total_bytes
            if self.memory_available_bytes is not None and self.memory_total_bytes is not None
            else None
        )
        observed = sum(
            item is not None
            for item in (
                self.battery_percent,
                self.battery_temperature_celsius,
                storage_percent,
                ram_percent,
                self.network_validated,
                self.usb_connected,
            )
        )
        penalty = 0
        caution = False
        critical = False
        if self.battery_percent is not None and self.battery_percent < 20:
            penalty += 18
            caution = True
        if (
            self.battery_temperature_celsius is not None
            and self.battery_temperature_celsius >= 45.0
        ):
            penalty += 25
            critical = True
        if storage_percent is not None and storage_percent >= 90:
            penalty += 25
            critical = True
        elif storage_percent is not None and storage_percent >= 80:
            penalty += 10
            caution = True
        if ram_percent is not None and ram_percent >= 90:
            penalty += 12
            caution = True
        if self.network_validated is False:
            penalty += 8
            caution = True
        scoring_complete = all(
            item is not None
            for item in (
                self.battery_percent,
                self.battery_temperature_celsius,
                storage_percent,
                ram_percent,
                self.network_validated,
            )
        )
        score = max(0, 100 - penalty) if scoring_complete else None
        coverage = observed * 100 // 6
        if critical or (score is not None and score < 65):
            state = "ACTION RECOMMENDED"
        elif caution or (score is not None and score < 85):
            state = "ATTENTION"
        elif score is None or coverage < 100:
            state = "UNCONFIRMED"
        else:
            state = "OPTIMAL"
        return score, state, coverage

    def verify_freshness(
        self,
        now_epoch_ms: int,
        *,
        maximum_age_ms: int = 120_000,
        maximum_future_skew_ms: int = 300_000,
    ) -> None:
        """Reject a replayed or implausibly future health observation."""

        if now_epoch_ms <= 0:
            raise ValueError("current telemetry time must be positive")
        if self.captured_at_epoch_ms > now_epoch_ms:
            if self.captured_at_epoch_ms - now_epoch_ms > maximum_future_skew_ms:
                raise ValueError("remote health evidence is too far in the future")
        elif now_epoch_ms - self.captured_at_epoch_ms > maximum_age_ms:
            raise ValueError("remote health evidence is stale")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "captured_at_epoch_ms": self.captured_at_epoch_ms,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "device_codename": self.device_codename,
            "android_version": self.android_version,
            "sdk_int": self.sdk_int,
            "companion_version": self.companion_version,
            "battery_percent": self.battery_percent,
            "battery_temperature_celsius": self.battery_temperature_celsius,
            "storage_used_bytes": self.storage_used_bytes,
            "storage_total_bytes": self.storage_total_bytes,
            "memory_available_bytes": self.memory_available_bytes,
            "memory_total_bytes": self.memory_total_bytes,
            "network_validated": self.network_validated,
            "usb_connected": self.usb_connected,
            "health_score": self.health_score,
            "vitalis_state": self.vitalis_state,
            "vitalis_evidence_percent": self.vitalis_evidence_percent,
            "kernel_release": self.kernel_release,
            "root_signal": self.root_signal,
            "root_manager_candidate": self.root_manager_candidate,
            "bootloader_state": self.bootloader_state,
            "kernelsu_support": self.kernelsu_support,
            "user_data_backup_state": self.user_data_backup_state,
            "user_data_backup_confirmed_at_epoch_ms": self.user_data_backup_confirmed_at_epoch_ms,
            "backup_confirmation_scope": self.backup_confirmation_scope,
            "backup_execution_authority": self.backup_execution_authority,
            "guardian_active": self.guardian_active,
            "privacy_scope": self.privacy_scope,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> RemoteCompanionSnapshot:
        if not isinstance(payload, Mapping):
            raise ValueError("remote telemetry must be an object")
        forbidden = _FORBIDDEN_REMOTE_FIELDS.intersection(payload)
        if forbidden:
            raise ValueError(f"forbidden remote telemetry field: {sorted(forbidden)[0]}")
        guardian_active = payload.get("guardian_active")
        if guardian_active is not True:
            raise ValueError("remote telemetry requires Guardian to be active")
        schema_version = _integer(payload, "schema_version", minimum=1, maximum=5)
        privacy_scope = payload.get("privacy_scope")
        expected_scope = "health_only" if schema_version == 1 else "health_and_device_safety"
        if privacy_scope != expected_scope:
            raise ValueError("unsupported remote telemetry privacy scope")
        return cls(
            schema_version=schema_version,
            captured_at_epoch_ms=_integer(
                payload, "captured_at_epoch_ms", minimum=1, maximum=2**63 - 1
            ),
            manufacturer=_bounded_text(payload, "manufacturer"),
            model=_bounded_text(payload, "model"),
            device_codename=_bounded_text(payload, "device_codename"),
            android_version=_bounded_text(payload, "android_version"),
            sdk_int=_integer(payload, "sdk_int", minimum=1, maximum=10_000),
            companion_version=_bounded_text(payload, "companion_version", maximum=40),
            battery_percent=_optional_integer(payload, "battery_percent", minimum=0, maximum=100),
            storage_used_bytes=_optional_integer(
                payload, "storage_used_bytes", minimum=0, maximum=2**63 - 1
            ),
            storage_total_bytes=_optional_integer(
                payload, "storage_total_bytes", minimum=0, maximum=2**63 - 1
            ),
            memory_available_bytes=_optional_integer(
                payload, "memory_available_bytes", minimum=0, maximum=2**63 - 1
            ),
            memory_total_bytes=_optional_integer(
                payload, "memory_total_bytes", minimum=0, maximum=2**63 - 1
            ),
            health_score=_optional_integer(payload, "health_score", minimum=0, maximum=100),
            battery_temperature_celsius=(
                _optional_number(
                    payload,
                    "battery_temperature_celsius",
                    minimum=-20.0,
                    maximum=100.0,
                )
                if schema_version >= 4
                else None
            ),
            network_validated=(
                _optional_boolean(payload, "network_validated") if schema_version >= 4 else None
            ),
            usb_connected=(
                _optional_boolean(payload, "usb_connected") if schema_version >= 4 else None
            ),
            vitalis_state=(
                _bounded_text(payload, "vitalis_state", maximum=24)
                if schema_version >= 4
                else "UNCONFIRMED"
            ),
            vitalis_evidence_percent=(
                _integer(payload, "vitalis_evidence_percent", minimum=0, maximum=100)
                if schema_version >= 4
                else 0
            ),
            kernel_release=(
                _bounded_text(payload, "kernel_release", maximum=160) if schema_version >= 2 else ""
            ),
            root_signal=(
                _bounded_text(payload, "root_signal", maximum=20)
                if schema_version >= 2
                else "unknown"
            ),
            root_manager_candidate=(
                _bounded_text(payload, "root_manager_candidate", maximum=20)
                if schema_version >= 3
                else "unknown"
            ),
            bootloader_state=(
                _bounded_text(payload, "bootloader_state", maximum=20)
                if schema_version >= 2
                else "unknown"
            ),
            kernelsu_support=(
                _bounded_text(payload, "kernelsu_support", maximum=20)
                if schema_version >= 2
                else "unknown"
            ),
            user_data_backup_state=(
                _bounded_text(payload, "user_data_backup_state", maximum=24)
                if schema_version >= 5
                else "unconfirmed"
            ),
            user_data_backup_confirmed_at_epoch_ms=(
                _optional_integer(
                    payload,
                    "user_data_backup_confirmed_at_epoch_ms",
                    minimum=1,
                    maximum=2**63 - 1,
                )
                if schema_version >= 5
                else None
            ),
            backup_confirmation_scope=(
                _bounded_text(payload, "backup_confirmation_scope", maximum=40)
                if schema_version >= 5
                else "user_attestation_only"
            ),
            backup_execution_authority=(
                _bounded_text(payload, "backup_execution_authority", maximum=20)
                if schema_version >= 5
                else "none"
            ),
            guardian_active=True,
            privacy_scope=expected_scope,
        )
