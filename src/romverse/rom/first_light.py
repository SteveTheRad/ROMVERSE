from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from romverse.core.privacy import WorkspacePrivacy
from romverse.device.intelligence import DeviceIntelligenceHistoryStore
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.registry import DevicePackRegistry
from romverse.infrastructure.local_store import atomic_write_json, read_json_object
from romverse.rom.boot_observation import BootObservationReceipt, BootObservationService
from romverse.rom.boot_observation import _digest as _boot_digest
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore

if TYPE_CHECKING:
    from romverse.knowledge.models import KnowledgeFailure


class FirstLightStatus(StrEnum):
    WORKING = "working"
    DEGRADED = "degraded"
    UNTESTED = "untested"
    FAILED = "failed"
    NOT_APPLICABLE = "not-applicable"


class FirstLightEvidenceKind(StrEnum):
    AUTOMATED = "automated-read-only"
    COMPANION = "companion-observed"
    USER = "user-observed"


class FirstLightOverall(StrEnum):
    INCOMPLETE = "incomplete"
    DEGRADED = "degraded"
    FAILED = "failed"
    VERIFIED = "verified"


@dataclass(frozen=True, slots=True)
class FirstLightSubsystem:
    subsystem_id: str
    label: str
    required: bool
    status: FirstLightStatus
    evidence_kind: FirstLightEvidenceKind
    observed_at: str
    evidence: str
    note: str


@dataclass(frozen=True, slots=True)
class FirstLightBaselineChange:
    field_id: str
    label: str
    before: str
    after: str
    state: str


@dataclass(frozen=True, slots=True)
class FirstLightReport:
    schema_version: int
    report_id: str
    project_id: str
    created_at: str
    updated_at: str
    device_key: str
    pack_id: str
    source_sha256: str
    guardian_execution_receipt_digest: str
    boot_observation_digest: str
    expected_build_id: str
    observed_build_id: str
    observed_build_fingerprint: str
    observed_android_version: str
    observed_slot: str
    baseline_scan_id: str
    baseline_changes: tuple[FirstLightBaselineChange, ...]
    subsystems: tuple[FirstLightSubsystem, ...]
    overall: FirstLightOverall
    knowledge_queries: tuple[str, ...]
    public_release_ready: bool
    exportable: bool
    phone_changed: bool
    report_digest: str


class FirstLightService:
    """Prove post-flash identity and subsystem outcomes without changing the phone."""

    NAME = "first-light-report.romverse"
    FORMAT = "romverse.first-light-report"
    SCHEMA_VERSION = 1
    MAX_BYTES = 1024 * 1024
    MAX_SUBSYSTEMS = 32
    MAX_CHANGES = 32
    MAX_QUERIES = 32
    AUTOMATED_IDS = frozenset({"first_boot", "build_identity", "partition_state", "usb", "storage"})
    SUBSYSTEMS = (
        ("first_boot", "Stable first boot", True),
        ("build_identity", "Build and firmware identity", True),
        ("partition_state", "Partition, slot and Verified Boot state", True),
        ("wifi", "Wi-Fi", True),
        ("bluetooth", "Bluetooth", True),
        ("mobile_data", "Mobile data", True),
        ("calls", "Calls and telephony", True),
        ("gps", "GPS and location", True),
        ("nfc", "NFC", True),
        ("usb", "USB data connection", True),
        ("storage", "App-private storage and data mount", True),
        ("camera", "Camera", True),
        ("microphone", "Microphone", True),
        ("speakers", "Speakers and media audio", True),
        ("sensors", "Sensors", True),
        ("biometrics", "Biometrics", True),
        ("charging", "Charging", True),
        ("android_auto_components", "Android Auto system integration", True),
        ("android_auto", "Android Auto vehicle projection", True),
        ("thermal", "Thermal stability", True),
        ("battery_drain", "Abnormal battery drain", True),
        ("crashes", "Crashes and system stability", True),
    )

    def __init__(self, store: RomProjectStore, registry: DevicePackRegistry) -> None:
        self.store = store
        self.registry = registry
        self.privacy = WorkspacePrivacy(store.workspace)

    def start(
        self,
        project_id: str,
        device: AndroidDevice,
        boot: BootObservationReceipt,
    ) -> FirstLightReport:
        project, pack = self._context(project_id)
        self._validate_boot(
            project_id,
            device,
            boot,
            project.original.sha256,
            pack.pack_id,
            pack.build_contract.contract_id,
        )
        existing_path = self.store.projects_root / project_id / self.NAME
        previous = self.load(project_id)
        if previous is None and (existing_path.exists() or existing_path.is_symlink()):
            raise ProjectError(
                "Existing First Light evidence is unreadable and will not be overwritten"
            )
        if previous is not None and (
            previous.device_key != self.privacy.pseudonym(device.serial)
            or previous.guardian_execution_receipt_digest != boot.guardian_execution_receipt_digest
            or previous.boot_observation_digest != boot.receipt_digest
        ):
            previous = None
        now = datetime.now(UTC).isoformat()
        baseline = self._baseline(device, boot.guardian_execution_receipt_digest)
        changes = self._baseline_changes(device, baseline)
        expected_build = pack.build_contract.source.build_id
        identity_ok = bool(device.build_id and device.build_id == expected_build)
        partition_state_known = bool(
            device.verified_boot
            and device.ab_update is not None
            and device.dynamic_partitions is not None
            and (device.ab_update is False or device.slot_suffix)
        )
        partition_evidence = (
            f"Active slot {device.slot_suffix.removeprefix('_') or 'single-slot'}; "
            f"Verified Boot {device.verified_boot or 'unavailable'}; "
            f"A/B {_yes_no_unknown(device.ab_update)}; "
            f"Virtual A/B {_yes_no_unknown(device.virtual_ab)}; "
            f"dynamic partitions {_yes_no_unknown(device.dynamic_partitions)}."
        )
        automatic = {
            "first_boot": self._automatic(
                "first_boot",
                "Stable first boot",
                boot.verified_first_boot,
                "Boot Observatory recorded a stable boot linked to the exact successful Guardian execution.",
                now,
            ),
            "build_identity": self._automatic(
                "build_identity",
                "Build and firmware identity",
                identity_ok,
                f"Expected {expected_build}; observed {device.build_id or 'unavailable'}.",
                now,
            ),
            "partition_state": self._automatic(
                "partition_state",
                "Partition, slot and Verified Boot state",
                partition_state_known,
                partition_evidence,
                now,
                unknown=not partition_state_known,
            ),
            "usb": self._automatic(
                "usb",
                "USB data connection",
                device.state is DeviceState.DEVICE and device.transport.casefold() == "usb",
                f"ADB state {device.state.value}; transport {device.transport or 'unknown'}.",
                now,
                unknown=not device.transport,
            ),
            "storage": self._automatic(
                "storage",
                "App-private storage and data mount",
                device.storage.total_bytes is not None
                and device.storage.available_bytes is not None,
                "Android reported readable total and available data-storage values."
                if device.storage.total_bytes is not None
                and device.storage.available_bytes is not None
                else "Storage telemetry is unavailable.",
                now,
                unknown=device.storage.total_bytes is None
                or device.storage.available_bytes is None,
            ),
        }
        prior = {item.subsystem_id: item for item in previous.subsystems} if previous else {}
        subsystems = tuple(
            automatic.get(subsystem_id)
            or prior.get(subsystem_id)
            or FirstLightSubsystem(
                subsystem_id,
                label,
                required,
                FirstLightStatus.UNTESTED,
                FirstLightEvidenceKind.USER,
                "",
                "No observation has been recorded.",
                "",
            )
            for subsystem_id, label, required in self.SUBSYSTEMS
        )
        created = previous.created_at if previous is not None else now
        report_id = previous.report_id if previous is not None else uuid4().hex
        return self._save(
            self._report(
                report_id,
                project_id,
                created,
                now,
                device,
                pack.pack_id,
                project.original.sha256,
                boot,
                expected_build,
                baseline.scan_id if baseline is not None else "",
                changes,
                subsystems,
            )
        )

    def record_observation(
        self,
        report: FirstLightReport,
        subsystem_id: str,
        status: FirstLightStatus,
        evidence_kind: FirstLightEvidenceKind,
        evidence: str,
        note: str = "",
    ) -> FirstLightReport:
        current = self.load(report.project_id)
        if current is None or current.report_digest != report.report_digest:
            raise ProjectError("First Light report changed; reload it before recording a result")
        if subsystem_id in self.AUTOMATED_IDS:
            raise ProjectError("This First Light result is owned by automated read-only evidence")
        if evidence_kind is FirstLightEvidenceKind.AUTOMATED:
            raise ProjectError("Manual observations cannot claim automated evidence")
        clean_evidence = self._text(evidence, "test evidence", 600, required=True)
        clean_note = self._text(note, "test note", 600)
        observed_at = "" if status is FirstLightStatus.UNTESTED else datetime.now(UTC).isoformat()
        replacements = []
        found = False
        for item in current.subsystems:
            if item.subsystem_id != subsystem_id:
                replacements.append(item)
                continue
            found = True
            replacements.append(
                FirstLightSubsystem(
                    item.subsystem_id,
                    item.label,
                    item.required,
                    status,
                    evidence_kind,
                    observed_at,
                    clean_evidence,
                    clean_note,
                )
            )
        if not found:
            raise ProjectError("Unknown First Light subsystem")
        payload = asdict(current)
        payload.pop("report_digest")
        payload["updated_at"] = datetime.now(UTC).isoformat()
        payload["subsystems"] = tuple(replacements)
        overall, queries, ready = self._classify(tuple(replacements))
        payload["overall"] = overall
        payload["knowledge_queries"] = queries
        payload["public_release_ready"] = ready
        updated = FirstLightReport(**payload, report_digest=_digest(payload))
        return self._save(updated)

    def load(self, project_id: str) -> FirstLightReport | None:
        try:
            data = read_json_object(
                self.store.projects_root / project_id / self.NAME,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            if data.pop("format") != self.FORMAT:
                return None
            raw_changes = data.pop("baseline_changes")
            raw_subsystems = data.pop("subsystems")
            data["overall"] = FirstLightOverall(data["overall"])
            data["knowledge_queries"] = tuple(data["knowledge_queries"])
            report = FirstLightReport(
                **data,
                baseline_changes=tuple(FirstLightBaselineChange(**item) for item in raw_changes),
                subsystems=tuple(
                    FirstLightSubsystem(
                        **{
                            **item,
                            "status": FirstLightStatus(item["status"]),
                            "evidence_kind": FirstLightEvidenceKind(item["evidence_kind"]),
                        }
                    )
                    for item in raw_subsystems
                ),
            )
            if not self._valid(report, project_id):
                return None
            return report
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError, ProjectError):
            return None

    def export_report(self, report: FirstLightReport, destination: Path) -> Path:
        current = self.load(report.project_id)
        if current is None or current.report_digest != report.report_digest:
            raise ProjectError("First Light report is missing, changed or superseded")
        target = destination.expanduser()
        if target.exists() and target.is_dir():
            target = target / f"romverse-first-light-{report.report_id[:12]}.json"
        parent = target.parent.resolve(strict=True)
        if parent.is_relative_to(self.store.workspace.resolve()):
            raise ProjectError("Tester reports must be exported outside the workspace")
        if target.exists() or target.is_symlink():
            raise ProjectError("The tester-report export already exists")
        atomic_write_json(
            target,
            {"format": self.FORMAT, **asdict(report)},
            boundary=parent,
            maximum_bytes=self.MAX_BYTES,
        )
        return target

    @classmethod
    def needs_knowledge_lookup(cls, report: FirstLightReport | None) -> bool:
        return bool(
            report is not None
            and report.overall in {FirstLightOverall.DEGRADED, FirstLightOverall.FAILED}
            and report.knowledge_queries
        )

    @classmethod
    def knowledge_failure(
        cls,
        report: FirstLightReport | None,
    ) -> KnowledgeFailure | None:
        """Translate measured subsystem failures into an inert offline Archives query."""

        if not cls.needs_knowledge_lookup(report) or report is None:
            return None
        from romverse.knowledge.models import KnowledgeFailure

        affected = tuple(
            item.subsystem_id
            for item in report.subsystems
            if item.status in {FirstLightStatus.DEGRADED, FirstLightStatus.FAILED}
        )
        return KnowledgeFailure(
            phase="first-light",
            message="\n".join(report.knowledge_queries),
            finding_ids=tuple(f"first-light.{item}" for item in affected),
            operation="read-only post-flash subsystem validation",
            verified_inputs=(
                f"pack:{report.pack_id}",
                f"source:{report.source_sha256}",
                f"guardian:{report.guardian_execution_receipt_digest}",
                f"boot:{report.boot_observation_digest}",
            ),
        )

    def _context(self, project_id: str):
        project = self.store.get(project_id)
        pack = next(
            (item for item in self.registry.packs if item.pack_id == project.device_pack_id),
            None,
        )
        if project.original is None or pack is None or pack.build_contract is None:
            raise ProjectError("First Light requires an exact source-bound Device Pack")
        if pack.build_contract.source.archive_sha256 != project.original.sha256:
            raise ProjectError("First Light source and Device Pack do not match")
        return project, pack

    def _validate_boot(
        self,
        project_id: str,
        device: AndroidDevice,
        boot: BootObservationReceipt,
        source_sha256: str,
        pack_id: str,
        contract_id: str,
    ) -> None:
        resolution = self.registry.resolve(device)
        try:
            boot_payload = asdict(boot) if isinstance(boot, BootObservationReceipt) else {}
            boot_digest = boot_payload.pop("receipt_digest", "")
            classification = (
                BootObservationService._classify(boot.samples)
                if isinstance(boot, BootObservationReceipt) and boot.samples
                else None
            )
            sequence_valid = bool(
                isinstance(boot, BootObservationReceipt)
                and BootObservationService._valid_sample_sequence(boot.samples)
            )
        except (AttributeError, TypeError, ValueError):
            classification = None
            sequence_valid = False
            boot_digest = ""
        if (
            not isinstance(boot, BootObservationReceipt)
            or boot.schema_version != BootObservationService.SCHEMA_VERSION
            or boot.project_id != project_id
            or boot.pack_id != pack_id
            or boot.contract_id != contract_id
            or boot.source_original_sha256 != source_sha256
            or not boot.flash_linked
            or not boot.verified_first_boot
            or not boot.stable
            or not _sha256_value(boot.guardian_execution_receipt_digest)
            or not _sha256_value(boot.receipt_digest)
            or not boot.samples
            or boot.samples[-1].device_pseudonym != self.privacy.pseudonym(device.serial)
            or boot.phone_changed
            or classification is None
            or boot.status is not classification[0]
            or boot.stable is not classification[1]
            or boot.reboot_detected is not classification[2]
            or boot.diagnosis != classification[3]
            or boot.failure_kind is not classification[4]
            or boot.knowledge_queries
            != BootObservationService._knowledge_queries(boot.samples, classification[4])
            or not sequence_valid
            or boot_digest != _boot_digest(boot_payload)
            or resolution.pack is None
            or resolution.pack.pack_id != pack_id
        ):
            raise ProjectError(
                "First Light requires stable first boot linked to the exact successful Guardian execution"
            )

    def _baseline(self, device: AndroidDevice, guardian_digest: str):
        history = DeviceIntelligenceHistoryStore(self.store.workspace)
        operation = next(
            (
                item
                for item in history.load_operations(device_serial=device.serial)
                if item.evidence_digest == guardian_digest
            ),
            None,
        )
        if operation is None:
            return None
        cutoff = datetime.fromisoformat(operation.occurred_at)
        return next(
            (
                item
                for item in history.load(device_serial=device.serial)
                if datetime.fromisoformat(item.observed_at) <= cutoff
            ),
            None,
        )

    @staticmethod
    def _baseline_changes(device: AndroidDevice, baseline) -> tuple[FirstLightBaselineChange, ...]:
        if baseline is None:
            return ()
        values = (
            ("codename", "Codename", baseline.codename, device.codename),
            ("android", "Android version", baseline.android_version, device.android_version),
            (
                "firmware",
                "Firmware version",
                baseline.firmware_version,
                device.rom_display or device.build_id or device.build_incremental,
            ),
            ("slot", "Active slot", baseline.active_slot, device.slot_suffix.removeprefix("_")),
            (
                "slot_scheme",
                "Slot scheme",
                baseline.slot_scheme,
                "Virtual A/B"
                if device.virtual_ab is True
                else "A/B"
                if device.ab_update is True
                else "Single-slot reported"
                if device.ab_update is False
                else "Unconfirmed",
            ),
            ("verified_boot", "Verified Boot", baseline.verified_boot_state, device.verified_boot),
            (
                "partitions",
                "Partition state",
                baseline.partition_summary,
                "Dynamic partitions reported by Android; exact inventory bound by Device Pack"
                if device.dynamic_partitions is True
                else "Non-dynamic layout reported by Android; exact inventory bound by Device Pack"
                if device.dynamic_partitions is False
                else "Exact partition state unconfirmed",
            ),
            ("security_patch", "Security patch", baseline.security_patch, device.security_patch),
        )
        return tuple(
            FirstLightBaselineChange(
                field_id,
                label,
                before or "unavailable",
                after or "unavailable",
                "unchanged"
                if before and before == after
                else "changed"
                if before and after
                else "unknown",
            )
            for field_id, label, before, after in values
        )

    @staticmethod
    def _automatic(
        subsystem_id: str,
        label: str,
        passed: bool,
        evidence: str,
        observed_at: str,
        *,
        unknown: bool = False,
    ) -> FirstLightSubsystem:
        return FirstLightSubsystem(
            subsystem_id,
            label,
            True,
            FirstLightStatus.UNTESTED
            if unknown
            else FirstLightStatus.WORKING
            if passed
            else FirstLightStatus.FAILED,
            FirstLightEvidenceKind.AUTOMATED,
            "" if unknown else observed_at,
            evidence,
            "",
        )

    def _report(
        self,
        report_id: str,
        project_id: str,
        created_at: str,
        updated_at: str,
        device: AndroidDevice,
        pack_id: str,
        source_sha256: str,
        boot: BootObservationReceipt,
        expected_build: str,
        baseline_scan_id: str,
        changes: tuple[FirstLightBaselineChange, ...],
        subsystems: tuple[FirstLightSubsystem, ...],
    ) -> FirstLightReport:
        overall, queries, ready = self._classify(subsystems)
        payload: dict[str, object] = {
            "schema_version": 1,
            "report_id": report_id,
            "project_id": project_id,
            "created_at": created_at,
            "updated_at": updated_at,
            "device_key": self.privacy.pseudonym(device.serial),
            "pack_id": pack_id,
            "source_sha256": source_sha256,
            "guardian_execution_receipt_digest": boot.guardian_execution_receipt_digest,
            "boot_observation_digest": boot.receipt_digest,
            "expected_build_id": expected_build,
            "observed_build_id": device.build_id,
            "observed_build_fingerprint": device.build_fingerprint,
            "observed_android_version": device.android_version,
            "observed_slot": device.slot_suffix,
            "baseline_scan_id": baseline_scan_id,
            "baseline_changes": changes,
            "subsystems": subsystems,
            "overall": overall,
            "knowledge_queries": queries,
            "public_release_ready": ready,
            "exportable": True,
            "phone_changed": False,
        }
        return FirstLightReport(**payload, report_digest=_digest(payload))

    def _save(self, report: FirstLightReport) -> FirstLightReport:
        if not self._valid(report, report.project_id):
            raise ProjectError("First Light report failed integrity validation")
        atomic_write_json(
            self.store.projects_root / report.project_id / self.NAME,
            {"format": self.FORMAT, **asdict(report)},
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_BYTES,
        )
        return report

    def _valid(self, report: FirstLightReport, project_id: str) -> bool:
        try:
            project, pack = self._context(project_id)
        except ProjectError:
            return False
        payload = asdict(report)
        digest = payload.pop("report_digest", "")
        overall, queries, ready = self._classify(report.subsystems)
        created_at = self._parsed_timestamp(report.created_at)
        updated_at = self._parsed_timestamp(report.updated_at)
        subsystem_contract = tuple(
            (item.subsystem_id, item.label, item.required) for item in report.subsystems
        )
        return bool(
            report.schema_version == self.SCHEMA_VERSION
            and re.fullmatch(r"[0-9a-f]{32}", report.report_id)
            and report.project_id == project_id
            and created_at is not None
            and updated_at is not None
            and created_at <= updated_at
            and bool(re.fullmatch(r"[0-9a-f]{20}", report.device_key))
            and report.pack_id == pack.pack_id
            and project.original is not None
            and report.source_sha256 == project.original.sha256
            and _sha256_value(report.guardian_execution_receipt_digest)
            and _sha256_value(report.boot_observation_digest)
            and (
                not report.baseline_scan_id
                or bool(re.fullmatch(r"[0-9a-f]{24}", report.baseline_scan_id))
            )
            and len(report.baseline_changes) <= self.MAX_CHANGES
            and len({item.field_id for item in report.baseline_changes})
            == len(report.baseline_changes)
            and all(self._valid_change(item) for item in report.baseline_changes)
            and self._valid_text(report.expected_build_id, 180, required=True)
            and self._valid_text(report.observed_build_id, 180)
            and self._valid_text(report.observed_build_fingerprint, 600)
            and self._valid_text(report.observed_android_version, 80)
            and self._valid_text(report.observed_slot, 40)
            and len(report.subsystems) == len(self.SUBSYSTEMS)
            and subsystem_contract == self.SUBSYSTEMS
            and all(self._valid_subsystem(item) for item in report.subsystems)
            and len(report.knowledge_queries) <= self.MAX_QUERIES
            and all(self._valid_text(item, 600, required=True) for item in report.knowledge_queries)
            and len(set(report.knowledge_queries)) == len(report.knowledge_queries)
            and isinstance(report.overall, FirstLightOverall)
            and report.overall is overall
            and report.knowledge_queries == queries
            and type(report.public_release_ready) is bool
            and report.public_release_ready is ready
            and report.exportable is True
            and report.phone_changed is False
            and _sha256_value(digest)
            and digest == _digest(payload)
        )

    @classmethod
    def _classify(
        cls,
        subsystems: tuple[FirstLightSubsystem, ...],
    ) -> tuple[FirstLightOverall, tuple[str, ...], bool]:
        failures = tuple(
            item
            for item in subsystems
            if item.status in {FirstLightStatus.FAILED, FirstLightStatus.DEGRADED}
        )
        pending = tuple(
            item
            for item in subsystems
            if item.required and item.status is FirstLightStatus.UNTESTED
        )
        if any(item.status is FirstLightStatus.FAILED for item in failures):
            overall = FirstLightOverall.FAILED
        elif failures:
            overall = FirstLightOverall.DEGRADED
        elif pending:
            overall = FirstLightOverall.INCOMPLETE
        else:
            overall = FirstLightOverall.VERIFIED
        queries = tuple(
            dict.fromkeys(
                f"Android {item.label} {item.status.value} after ROM flash" for item in failures
            )
        )[: cls.MAX_QUERIES]
        ready = bool(
            overall is FirstLightOverall.VERIFIED
            and subsystems
            and all(
                item.status in {FirstLightStatus.WORKING, FirstLightStatus.NOT_APPLICABLE}
                for item in subsystems
            )
        )
        return overall, queries, ready

    @classmethod
    def _valid_subsystem(cls, item: FirstLightSubsystem) -> bool:
        known = {
            subsystem_id: (label, required) for subsystem_id, label, required in cls.SUBSYSTEMS
        }
        expected = known.get(item.subsystem_id)
        return bool(
            expected == (item.label, item.required)
            and isinstance(item.status, FirstLightStatus)
            and isinstance(item.evidence_kind, FirstLightEvidenceKind)
            and (not item.observed_at or cls._timestamp(item.observed_at))
            and cls._valid_text(item.evidence, 600, required=True)
            and cls._valid_text(item.note, 600)
            and (
                (item.status is FirstLightStatus.UNTESTED and not item.observed_at)
                or (item.status is not FirstLightStatus.UNTESTED and bool(item.observed_at))
            )
            and (
                (item.subsystem_id in cls.AUTOMATED_IDS)
                == (item.evidence_kind is FirstLightEvidenceKind.AUTOMATED)
            )
        )

    @classmethod
    def _valid_change(cls, item: FirstLightBaselineChange) -> bool:
        return bool(
            re.fullmatch(r"[a-z][a-z0-9_]{0,63}", item.field_id)
            and cls._valid_text(item.label, 100, required=True)
            and cls._valid_text(item.before, 600, required=True)
            and cls._valid_text(item.after, 600, required=True)
            and item.state in {"unchanged", "changed", "unknown"}
        )

    @staticmethod
    def _timestamp(value: object) -> bool:
        return FirstLightService._parsed_timestamp(value) is not None

    @staticmethod
    def _parsed_timestamp(value: object) -> datetime | None:
        if not isinstance(value, str) or len(value) > 80:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None or parsed > datetime.now(UTC) + timedelta(minutes=5):
            return None
        return parsed.astimezone(UTC)

    @staticmethod
    def _valid_text(value: object, maximum: int, *, required: bool = False) -> bool:
        if not isinstance(value, str):
            return False
        try:
            FirstLightService._text(value, "evidence", maximum, required=required)
        except ProjectError:
            return False
        return True

    @staticmethod
    def _text(
        value: object,
        label: str,
        maximum: int,
        *,
        required: bool = False,
    ) -> str:
        clean = str(value).strip()
        if (
            len(clean) > maximum
            or (required and not clean)
            or "\x00" in clean
            or any(ord(char) < 32 and char not in "\n\t" for char in clean)
        ):
            raise ProjectError(f"First Light {label} is invalid")
        return clean


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            default=lambda item: asdict(item),
        ).encode("ascii")
    ).hexdigest()


def _sha256_value(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _yes_no_unknown(value: bool | None) -> str:
    return "yes" if value is True else "no" if value is False else "unavailable"
