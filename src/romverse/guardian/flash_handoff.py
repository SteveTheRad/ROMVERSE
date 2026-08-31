from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from romverse.core.privacy import WorkspacePrivacy
from romverse.device.models import AndroidDevice, DeviceState
from romverse.guardian.invariants import contains_bootloader_relock
from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    ensure_private_directory,
    read_json_object,
)
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.rom.readiness import BuildReadinessReport

_HANDOFF_LIMITATIONS = (
    "This handoff records a mode choice; it does not authorize or execute a device write.",
    "Dirty flashing cannot guarantee data compatibility across incompatible firmware bases.",
    "Clean flashing irreversibly erases user data after a separate final approval.",
    "Bootloader relocking is permanently prohibited by ROMVERSE.",
)


class FlashMode(StrEnum):
    DIRTY_KEEP_DATA = "dirty_keep_data"
    CLEAN_WIPE_DATA = "clean_wipe_data"

    @property
    def display_name(self) -> str:
        return {
            FlashMode.DIRTY_KEEP_DATA: "Dirty flash • keep user data",
            FlashMode.CLEAN_WIPE_DATA: "Clean flash • wipe user data",
        }[self]


@dataclass(frozen=True, slots=True)
class GuardianFlashHandoff:
    """Exact final-review intent. It is deliberately not execution authority."""

    schema_version: int
    handoff_id: str
    created_at: str
    project_id: str
    readiness_report_digest: str
    readiness_evidence_digest: str
    source_sha256: str
    device_key: str
    device_name: str
    model: str
    codename: str
    mode: FlashMode
    preserve_user_data: bool
    wipe_user_data: bool
    bootloader_relock: bool
    bootloader_relock_allowed: bool
    execution_authorized: bool
    execution_status: str
    command_manifest: tuple[tuple[str, ...], ...]
    limitations: tuple[str, ...]
    handoff_digest: str


class GuardianFlashHandoffService:
    """Persist the user's mode choice without granting or performing a device write."""

    FORMAT = "romverse.guardian-flash-handoff"
    SCHEMA_VERSION = 2
    LATEST_NAME = "flash-handoff.romverse"
    MAX_RECEIPT_BYTES = 64 * 1024

    def __init__(self, store: RomProjectStore) -> None:
        self.store = store

    def prepare(
        self,
        project_id: str,
        report: BuildReadinessReport,
        device: AndroidDevice,
        mode: FlashMode,
    ) -> GuardianFlashHandoff:
        project = self.store.get(project_id)
        if project.original is None:
            raise ProjectError("Guardian handoff requires a protected source artifact")
        if report.project_id != project_id or not report.flash_ready:
            raise ProjectError("Every required readiness card must be green before flash review")
        if not report.guardian_handoff_ready or report.blockers:
            raise ProjectError("Guardian handoff evidence is incomplete")
        if device.state is not DeviceState.DEVICE or not device.serial:
            raise ProjectError("Connect and authorize the exact target phone before flash review")
        if (
            not device.display_name.strip()
            or not device.model.strip()
            or not device.codename.strip()
        ):
            raise ProjectError(
                "Guardian handoff requires the exact device name, model, and codename"
            )
        if not isinstance(mode, FlashMode):
            raise ProjectError("Choose one supported Guardian flash mode")

        preserve = mode is FlashMode.DIRTY_KEEP_DATA
        wipe = mode is FlashMode.CLEAN_WIPE_DATA
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "handoff_id": uuid4().hex,
            "created_at": datetime.now(UTC).isoformat(),
            "project_id": project_id,
            "readiness_report_digest": report.report_digest,
            "readiness_evidence_digest": readiness_evidence_digest(report),
            "source_sha256": project.original.sha256,
            "device_key": WorkspacePrivacy(self.store.workspace).pseudonym(device.serial),
            "device_name": device.display_name[:120],
            "model": device.model[:120],
            "codename": device.codename[:80],
            "mode": mode,
            "preserve_user_data": preserve,
            "wipe_user_data": wipe,
            "bootloader_relock": False,
            "bootloader_relock_allowed": False,
            "execution_authorized": False,
            "execution_status": "exact-manifest-review-and-final-consent-required",
            "command_manifest": (),
            "limitations": _HANDOFF_LIMITATIONS,
        }
        assert_never_relocks(payload["command_manifest"])
        handoff = GuardianFlashHandoff(
            **payload,
            handoff_digest=_digest(payload),
        )
        self.validate(handoff)
        self._write(project_id, handoff)
        return handoff

    def load(self, project_id: str) -> GuardianFlashHandoff | None:
        path = self._root(project_id) / self.LATEST_NAME
        try:
            project = self.store.get(project_id)
            data = read_json_object(
                path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
            schema_version = data.get("schema_version")
            expected_fields = {field.name for field in fields(GuardianFlashHandoff)}
            if schema_version == 1:
                expected_fields.remove("readiness_evidence_digest")
            elif schema_version != self.SCHEMA_VERSION:
                return None
            if (
                set(data) != {"format", *expected_fields}
                or data.pop("format") != self.FORMAT
                or not _valid_raw_handoff(data, schema_version)
            ):
                return None
            if schema_version == 1:
                data["readiness_evidence_digest"] = ""
            data["mode"] = FlashMode(str(data["mode"]))
            data["command_manifest"] = tuple(
                tuple(str(token) for token in command) for command in data["command_manifest"]
            )
            data["limitations"] = tuple(str(item) for item in data["limitations"])
            handoff = GuardianFlashHandoff(**data)
            self.validate(handoff)
            if (
                handoff.project_id != project_id
                or project.original is None
                or handoff.source_sha256 != project.original.sha256
            ):
                return None
            return handoff
        except (LocalStoreError, OSError, ValueError, TypeError, KeyError, ProjectError):
            return None

    def matches_current(
        self,
        project_id: str,
        handoff: GuardianFlashHandoff,
        device: AndroidDevice | None,
        report: BuildReadinessReport,
    ) -> bool:
        if (
            handoff.schema_version != self.SCHEMA_VERSION
            or device is None
            or device.state is not DeviceState.DEVICE
            or not device.serial
            or report.project_id != project_id
            or not report.flash_ready
            or not report.guardian_handoff_ready
            or bool(report.blockers)
            or handoff.readiness_evidence_digest != readiness_evidence_digest(report)
        ):
            return False
        try:
            self.validate(handoff)
            project = self.store.get(project_id)
        except ProjectError:
            return False
        return bool(
            project.original is not None
            and handoff.project_id == project_id
            and handoff.source_sha256 == project.original.sha256
            and handoff.device_key
            == WorkspacePrivacy(self.store.workspace).pseudonym(device.serial)
            and handoff.device_name.casefold() == device.display_name.casefold()
            and handoff.model.casefold() == device.model.casefold()
            and handoff.codename.casefold() == device.codename.casefold()
        )

    def validate(self, handoff: GuardianFlashHandoff) -> None:
        unsigned = asdict(handoff)
        expected = str(unsigned.pop("handoff_digest", ""))
        if handoff.schema_version == 1:
            unsigned.pop("readiness_evidence_digest", None)
        if (
            handoff.schema_version not in {1, self.SCHEMA_VERSION}
            or (
                handoff.schema_version == self.SCHEMA_VERSION
                and not re.fullmatch(r"[0-9a-f]{64}", handoff.readiness_evidence_digest)
            )
            or (handoff.schema_version == 1 and handoff.readiness_evidence_digest)
            or not re.fullmatch(r"[0-9a-f]{64}", handoff.readiness_report_digest)
            or not re.fullmatch(r"[0-9a-f]{64}", handoff.source_sha256)
            or handoff.bootloader_relock
            or handoff.bootloader_relock_allowed
            or handoff.execution_authorized
            or handoff.execution_status != "exact-manifest-review-and-final-consent-required"
            or handoff.command_manifest
            or handoff.limitations != _HANDOFF_LIMITATIONS
            or expected != _digest(unsigned)
            or handoff.preserve_user_data == handoff.wipe_user_data
            or handoff.preserve_user_data != (handoff.mode is FlashMode.DIRTY_KEEP_DATA)
        ):
            raise ProjectError("Guardian flash handoff failed integrity or safety validation")
        assert_never_relocks(handoff.command_manifest)

    def _write(self, project_id: str, handoff: GuardianFlashHandoff) -> None:
        root = self._root(project_id)
        ensure_private_directory(root, boundary=self.store.workspace)
        document = {"format": self.FORMAT, **asdict(handoff)}
        atomic_write_json(
            root / f"flash-handoff-{handoff.handoff_id[:12]}.romverse",
            document,
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_RECEIPT_BYTES,
        )
        atomic_write_json(
            root / self.LATEST_NAME,
            document,
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_RECEIPT_BYTES,
        )

    def _root(self, project_id: str) -> Path:
        self.store.get(project_id)
        return self.store.projects_root / project_id / "guardian"


def assert_never_relocks(commands: tuple[tuple[str, ...], ...]) -> None:
    """Fail closed if any future command plan attempts bootloader relocking."""

    if contains_bootloader_relock(commands):
        raise ProjectError("ROMVERSE permanently prohibits bootloader relocking")


def _digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def readiness_evidence_digest(report: BuildReadinessReport) -> str:
    """Hash only current readiness facts, excluding ephemeral report identity and time."""

    return _digest(
        {
            "project_id": report.project_id,
            "gates": [asdict(gate) for gate in report.gates],
            "workspace_ready": report.workspace_ready,
            "build_ready": report.build_ready,
            "local_candidate_ready": report.local_candidate_ready,
            "signing_ready": report.signing_ready,
            "flash_ready": report.flash_ready,
            "blockers": report.blockers,
            "next_actions": report.next_actions,
        }
    )


def _valid_raw_handoff(data: dict[str, object], schema_version: object) -> bool:
    strings = (
        "handoff_id",
        "created_at",
        "project_id",
        "readiness_report_digest",
        "source_sha256",
        "device_key",
        "device_name",
        "model",
        "codename",
        "mode",
        "execution_status",
        "handoff_digest",
    )
    if schema_version == GuardianFlashHandoffService.SCHEMA_VERSION:
        strings += ("readiness_evidence_digest",)
    if type(schema_version) is not int or any(type(data.get(name)) is not str for name in strings):
        return False
    if any(
        type(data.get(name)) is not bool
        for name in (
            "preserve_user_data",
            "wipe_user_data",
            "bootloader_relock",
            "bootloader_relock_allowed",
            "execution_authorized",
        )
    ):
        return False
    if (
        not re.fullmatch(r"[0-9a-f]{32}", str(data["handoff_id"]))
        or not _valid_timestamp(str(data["created_at"]))
        or not 0 < len(str(data["project_id"])) <= 128
        or not re.fullmatch(r"[0-9a-f]{64}", str(data["readiness_report_digest"]))
        or not re.fullmatch(r"[0-9a-f]{64}", str(data["source_sha256"]))
        or not re.fullmatch(r"[0-9a-f]{20}", str(data["device_key"]))
        or not all(
            0 < len(str(data[name])) <= limit
            for name, limit in (("device_name", 120), ("model", 120), ("codename", 80))
        )
        or "\x00" in "".join(str(data[name]) for name in ("device_name", "model", "codename"))
        or str(data["mode"]) not in {mode.value for mode in FlashMode}
        or data["command_manifest"] != []
        or data["limitations"] != list(_HANDOFF_LIMITATIONS)
        or not re.fullmatch(r"[0-9a-f]{64}", str(data["handoff_digest"]))
    ):
        return False
    return bool(
        schema_version == 1 or re.fullmatch(r"[0-9a-f]{64}", str(data["readiness_evidence_digest"]))
    )


def _valid_timestamp(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None
