from __future__ import annotations

import hashlib
import hmac
import json
import os
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from romverse.core.activity import ActivityStore, ActivityStoreError
from romverse.core.privacy import WorkspacePrivacy
from romverse.device.models import AndroidDevice
from romverse.diagnostics.models import DiagnosticReport


@dataclass(frozen=True, slots=True)
class StoredFinding:
    finding_id: str
    severity: str
    title: str


@dataclass(frozen=True, slots=True)
class StoredDiagnosticReport:
    path: Path
    snapshot_id: str
    generated_at: str
    device_key: str
    device_name: str
    health_score: int
    summary: str
    findings: tuple[StoredFinding, ...]
    integrity_verified: bool
    snapshot_digest: str
    content_digest: str
    verification_reason: str


@dataclass(frozen=True, slots=True)
class RejectedDiagnosticSnapshot:
    path: Path
    reason: str


@dataclass(frozen=True, slots=True)
class DiagnosticHistoryScan:
    reports: tuple[StoredDiagnosticReport, ...]
    rejected: tuple[RejectedDiagnosticSnapshot, ...]


@dataclass(frozen=True, slots=True)
class ReportComparison:
    score_delta: int
    added: tuple[StoredFinding, ...]
    resolved: tuple[StoredFinding, ...]


class DiagnosticHistoryError(RuntimeError):
    """Raised when diagnostic evidence cannot be preserved or verified safely."""


class DiagnosticHistoryStore:
    """Persists deliberately redacted reports under the local workspace."""

    SNAPSHOT_FORMAT = "romverse.diagnostic-snapshot"
    SNAPSHOT_VERSION = 1
    MAXIMUM_BYTES = 2 * 1024 * 1024
    MAX_FINDINGS = 256
    MAX_EVIDENCE = 512
    MAX_LIMITATIONS = 128

    def __init__(
        self,
        workspace: Path,
        activity_store: ActivityStore | None = None,
    ) -> None:
        self.workspace = workspace
        self.activity_store = activity_store
        self.root = workspace / "diagnostics" / "history"
        self.privacy_path = workspace / ".romverse-privacy.json"
        self.privacy = WorkspacePrivacy(workspace)

    def save(self, report: DiagnosticReport, device: AndroidDevice) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        path = self.root / f"diagnostic-{timestamp}.json"
        payload = asdict(report)
        payload.update(
            {
                "privacy": "redacted",
                "device_key": self._device_key(device.serial),
                "transport": device.transport,
                "snapshot_format": self.SNAPSHOT_FORMAT,
                "snapshot_version": self.SNAPSHOT_VERSION,
            }
        )
        private_values = tuple(
            value
            for value in (device.serial, device.build_fingerprint)
            if isinstance(value, str) and value
        )
        encoded = json.dumps(payload, sort_keys=True)
        if any(value in encoded for value in private_values):
            raise DiagnosticHistoryError("Diagnostic snapshot contains a private device identifier")
        payload["snapshot_id"] = hashlib.sha256(
            f"{timestamp}:{payload['device_key']}:{report.generated_at}".encode()
        ).hexdigest()[:24]
        payload["snapshot_digest"] = hashlib.sha256(_canonical(payload)).hexdigest()
        self._atomic_write(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
        if self.activity_store is not None:
            with suppress(ActivityStoreError):
                self.activity_store.record(
                    "diagnostics",
                    "Health snapshot saved",
                    f"{report.device_name} • health score {report.health_score} • {len(report.findings)} finding(s)",
                    outcome="success",
                    source="System Scan",
                    source_route="health_timeline",
                    context_type="diagnostic-snapshot",
                    context_id=str(payload["snapshot_id"]),
                )
        return path

    def list_reports(self, limit: int = 20) -> tuple[Path, ...]:
        if not self.root.exists():
            return ()
        return tuple(sorted(self.root.glob("diagnostic-*.json"), reverse=True)[:limit])

    def load_reports(self, limit: int = 100) -> tuple[StoredDiagnosticReport, ...]:
        return self.scan_reports(limit).reports

    def scan_reports(self, limit: int = 100) -> DiagnosticHistoryScan:
        reports: list[StoredDiagnosticReport] = []
        rejected: list[RejectedDiagnosticSnapshot] = []
        for path in self.list_reports(limit):
            try:
                if path.is_symlink() or not path.is_file():
                    raise ValueError("snapshot is not a regular local file")
                size = path.stat().st_size
                if size <= 0 or size > self.MAXIMUM_BYTES:
                    raise ValueError("snapshot size is outside the accepted boundary")
                payload = json.loads(path.read_text(encoding="utf-8"))
                report = self._validated_report(path, payload)
            except (OSError, json.JSONDecodeError, ValueError, TypeError, KeyError) as exc:
                rejected.append(RejectedDiagnosticSnapshot(path, str(exc)))
                continue
            reports.append(report)
        return DiagnosticHistoryScan(tuple(reports), tuple(rejected))

    def export_report(self, report: StoredDiagnosticReport, destination: Path) -> Path:
        destination = destination.expanduser().resolve()
        scan = self._load_one(report.path)
        if scan.path != report.path or scan.content_digest != report.content_digest:
            raise DiagnosticHistoryError("Diagnostic snapshot changed after it was selected")
        try:
            content = report.path.read_text(encoding="utf-8")
            destination.parent.mkdir(parents=True, exist_ok=True)
            self._atomic_write(destination, content)
        except OSError as exc:
            raise DiagnosticHistoryError(f"Could not export diagnostic snapshot: {exc}") from exc
        return destination

    @staticmethod
    def compare(
        current: StoredDiagnosticReport,
        previous: StoredDiagnosticReport,
    ) -> ReportComparison | None:
        if current.device_key != previous.device_key:
            return None
        current_by_id = {item.finding_id: item for item in current.findings}
        previous_by_id = {item.finding_id: item for item in previous.findings}
        return ReportComparison(
            score_delta=current.health_score - previous.health_score,
            added=tuple(
                current_by_id[key] for key in sorted(current_by_id.keys() - previous_by_id)
            ),
            resolved=tuple(
                previous_by_id[key] for key in sorted(previous_by_id.keys() - current_by_id)
            ),
        )

    @classmethod
    def _validated_report(cls, path: Path, payload: dict) -> StoredDiagnosticReport:
        if not isinstance(payload, dict):
            raise TypeError("diagnostic report must be an object")
        content_digest = hashlib.sha256(_canonical(payload)).hexdigest()
        if payload.get("privacy") != "redacted" or payload.get("schema_version") != 1:
            raise ValueError("unsupported or unredacted diagnostic report")
        snapshot_keys = {
            "snapshot_format",
            "snapshot_version",
            "snapshot_id",
            "snapshot_digest",
        }
        present_snapshot_keys = snapshot_keys.intersection(payload)
        if present_snapshot_keys and present_snapshot_keys != snapshot_keys:
            raise ValueError("diagnostic snapshot integrity envelope is incomplete")
        integrity_verified = bool(present_snapshot_keys)
        snapshot_id = ""
        snapshot_digest = ""
        verification_reason = "Legacy snapshot; integrity fingerprint unavailable"
        if integrity_verified:
            if (
                payload.get("snapshot_format") != cls.SNAPSHOT_FORMAT
                or payload.get("snapshot_version") != cls.SNAPSHOT_VERSION
            ):
                raise ValueError("unsupported diagnostic snapshot format")
            snapshot_id = cls._bounded_text(payload["snapshot_id"], "snapshot id", 80)
            if len(snapshot_id) != 24 or not _is_lower_hex(snapshot_id):
                raise ValueError("invalid diagnostic snapshot identifier")
            snapshot_digest = cls._bounded_text(payload["snapshot_digest"], "snapshot digest", 64)
            unsigned = dict(payload)
            unsigned.pop("snapshot_digest", None)
            actual_digest = hashlib.sha256(_canonical(unsigned)).hexdigest()
            if len(snapshot_digest) != 64 or not hmac.compare_digest(
                snapshot_digest, actual_digest
            ):
                raise ValueError("diagnostic snapshot integrity mismatch")
            verification_reason = "SHA-256 snapshot integrity verified"
        score = int(payload["health_score"])
        if not 0 <= score <= 100:
            raise ValueError("invalid health score")
        generated_at = cls._bounded_text(payload["generated_at"], "generated time", 80)
        parsed_time = datetime.fromisoformat(generated_at)
        if parsed_time.tzinfo is None:
            raise ValueError("diagnostic timestamp must include a timezone")
        device_key = cls._bounded_text(payload["device_key"], "device key", 64)
        if not 16 <= len(device_key) <= 64 or not _is_lower_hex(device_key):
            raise ValueError("invalid pseudonymous device key")
        raw_findings = payload["findings"]
        if not isinstance(raw_findings, list) or len(raw_findings) > cls.MAX_FINDINGS:
            raise ValueError("invalid diagnostic finding collection")
        findings = tuple(
            StoredFinding(
                finding_id=cls._bounded_text(item["finding_id"], "finding id", 120),
                severity=cls._severity(item["severity"]),
                title=cls._bounded_text(item["title"], "finding title", 240),
            )
            for item in raw_findings
        )
        if len({item.finding_id for item in findings}) != len(findings):
            raise ValueError("duplicate diagnostic finding identifiers")
        cls._validate_supporting_collections(payload)
        return StoredDiagnosticReport(
            path=path,
            snapshot_id=snapshot_id,
            generated_at=generated_at,
            device_key=device_key,
            device_name=cls._bounded_text(payload["device_name"], "device name", 240),
            health_score=score,
            summary=cls._bounded_text(payload["summary"], "summary", 1000),
            findings=findings,
            integrity_verified=integrity_verified,
            snapshot_digest=snapshot_digest,
            content_digest=content_digest,
            verification_reason=verification_reason,
        )

    def _load_one(self, path: Path) -> StoredDiagnosticReport:
        if path.is_symlink() or not path.is_file():
            raise DiagnosticHistoryError("Diagnostic snapshot is not a regular local file")
        try:
            size = path.stat().st_size
            if size <= 0 or size > self.MAXIMUM_BYTES:
                raise ValueError("snapshot size is outside the accepted boundary")
            payload = json.loads(path.read_text(encoding="utf-8"))
            return self._validated_report(path, payload)
        except (OSError, json.JSONDecodeError, ValueError, TypeError, KeyError) as exc:
            raise DiagnosticHistoryError(f"Diagnostic snapshot failed verification: {exc}") from exc

    @classmethod
    def _validate_supporting_collections(cls, payload: dict) -> None:
        evidence = payload.get("evidence")
        limitations = payload.get("limitations")
        if not isinstance(evidence, list) or len(evidence) > cls.MAX_EVIDENCE:
            raise ValueError("invalid diagnostic evidence collection")
        if not isinstance(limitations, list) or len(limitations) > cls.MAX_LIMITATIONS:
            raise ValueError("invalid diagnostic limitation collection")
        for item in evidence:
            if not isinstance(item, dict):
                raise TypeError("diagnostic evidence must be an object")
            cls._bounded_text(item.get("evidence_id"), "evidence id", 120)
            cls._bounded_text(item.get("label"), "evidence label", 240)
            cls._bounded_text(item.get("value"), "evidence value", 1000)
            cls._bounded_text(item.get("source"), "evidence source", 240)
        for item in limitations:
            cls._bounded_text(item, "limitation", 1000)

    @staticmethod
    def _severity(value: object) -> str:
        severity = DiagnosticHistoryStore._bounded_text(value, "finding severity", 24)
        if severity not in {"healthy", "information", "advisory", "warning", "critical"}:
            raise ValueError("unsupported diagnostic finding severity")
        return severity

    @staticmethod
    def _bounded_text(value: object, label: str, maximum: int) -> str:
        if not isinstance(value, str):
            raise TypeError(f"diagnostic {label} must be text")
        clean = value.replace("\x00", "").strip()
        if not clean or len(clean) > maximum:
            raise ValueError(f"diagnostic {label} must be 1–{maximum} characters")
        return clean

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)

    def _device_key(self, serial: str) -> str:
        return self.privacy.pseudonym(serial)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _is_lower_hex(value: str) -> bool:
    return all(character in "0123456789abcdef" for character in value)
