from __future__ import annotations

import hashlib
import json
import os
from contextlib import suppress
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from uuid import uuid4

from romverse.core.privacy import WorkspacePrivacy
from romverse.device.models import AndroidDevice
from romverse.diagnostics.models import DiagnosticReport
from romverse.repair.templates import RepairConcern


class RepairSessionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RepairSession:
    session_id: str
    created_at: str
    updated_at: str
    concern: str
    device_key: str
    device_name: str
    status: str
    initial_health_score: int
    initial_evidence_digest: str
    initial_finding_ids: tuple[str, ...]
    recommendations: tuple[str, ...]
    reviewed_steps: tuple[int, ...] = ()
    verification_health_score: int | None = None
    verification_evidence_digest: str = ""
    verification_finding_ids: tuple[str, ...] = ()
    verification_summary: str = ""


class RepairSessionStore:
    SCHEMA_VERSION = 1
    MAX_SESSIONS = 100
    _lock = Lock()

    def __init__(self, workspace: Path) -> None:
        self.root = workspace / "diagnostics" / "repair-sessions"
        self.privacy = WorkspacePrivacy(workspace)

    def start(
        self,
        concern: RepairConcern,
        device: AndroidDevice,
        report: DiagnosticReport,
        recommendations: tuple[str, ...],
    ) -> RepairSession:
        now = datetime.now(UTC).isoformat()
        session = RepairSession(
            session_id=uuid4().hex,
            created_at=now,
            updated_at=now,
            concern=concern.value,
            device_key=self.privacy.pseudonym(device.serial),
            device_name=self._text(device.display_name, 120),
            status="active",
            initial_health_score=report.health_score,
            initial_evidence_digest=self._evidence_digest(report),
            initial_finding_ids=tuple(sorted(item.finding_id for item in report.findings)),
            recommendations=tuple(self._text(item, 400) for item in recommendations),
        )
        self._save(session)
        self._prune()
        return session

    def update_reviewed(self, session_id: str, reviewed_steps: tuple[int, ...]) -> RepairSession:
        session = self.load(session_id)
        normalized = tuple(sorted(set(int(index) for index in reviewed_steps)))
        if any(index < 0 or index >= len(session.recommendations) for index in normalized):
            raise RepairSessionError("Repair checkpoint is outside this session")
        status = (
            "ready_for_verification"
            if len(normalized) == len(session.recommendations)
            else "active"
        )
        updated = replace(
            session,
            reviewed_steps=normalized,
            status=status,
            updated_at=datetime.now(UTC).isoformat(),
        )
        self._save(updated)
        return updated

    def verify(
        self,
        session_id: str,
        device: AndroidDevice,
        report: DiagnosticReport,
    ) -> RepairSession:
        session = self.load(session_id)
        if self.privacy.pseudonym(device.serial) != session.device_key:
            raise RepairSessionError("Connected device does not match this repair session")
        current_ids = tuple(sorted(item.finding_id for item in report.findings))
        resolved = sorted(set(session.initial_finding_ids) - set(current_ids))
        added = sorted(set(current_ids) - set(session.initial_finding_ids))
        delta = report.health_score - session.initial_health_score
        if delta > 0 or (resolved and not added):
            direction = "improved"
        elif delta < 0 or added:
            direction = "needs more attention"
        else:
            direction = "unchanged"
        summary = (
            f"Fresh read-only evidence is {direction}: health score {delta:+d}; "
            f"{len(resolved)} finding(s) resolved; {len(added)} new finding(s)."
        )
        updated = replace(
            session,
            status="verified",
            updated_at=datetime.now(UTC).isoformat(),
            verification_health_score=report.health_score,
            verification_evidence_digest=self._evidence_digest(report),
            verification_finding_ids=current_ids,
            verification_summary=summary,
        )
        self._save(updated)
        return updated

    def load(self, session_id: str) -> RepairSession:
        if not session_id or len(session_id) > 80:
            raise RepairSessionError("Invalid repair session identifier")
        path = self.root / f"{session_id}.romverse-repair.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return self._parse(payload)
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise RepairSessionError(f"Repair session is unreadable: {exc}") from exc

    def list_recent(self) -> tuple[RepairSession, ...]:
        if not self.root.exists():
            return ()
        sessions: list[RepairSession] = []
        for path in sorted(self.root.glob("*.romverse-repair.json"), reverse=True):
            try:
                sessions.append(self._parse(json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
        return tuple(sorted(sessions, key=lambda item: item.updated_at, reverse=True))

    def _save(self, session: RepairSession) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{session.session_id}.romverse-repair.json"
        temporary = path.with_suffix(".tmp")
        payload = {
            "format": "romverse.repair-session",
            "schema_version": self.SCHEMA_VERSION,
            "privacy": "pseudonymous-local",
            "session": asdict(session),
        }
        try:
            with self._lock:
                with temporary.open("w", encoding="utf-8") as stream:
                    json.dump(payload, stream, indent=2)
                    stream.write("\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
        except OSError as exc:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
            raise RepairSessionError(f"Could not preserve repair session: {exc}") from exc

    def _parse(self, payload: object) -> RepairSession:
        if not isinstance(payload, dict):
            raise TypeError("repair session must be an object")
        if (
            payload.get("format") != "romverse.repair-session"
            or payload.get("schema_version") != self.SCHEMA_VERSION
            or payload.get("privacy") != "pseudonymous-local"
        ):
            raise ValueError("unsupported repair session schema")
        item = payload["session"]
        if not isinstance(item, dict):
            raise TypeError("repair session payload must be an object")
        session = RepairSession(
            session_id=self._text(item["session_id"], 80),
            created_at=self._timestamp(item["created_at"]),
            updated_at=self._timestamp(item["updated_at"]),
            concern=self._text(item["concern"], 160),
            device_key=self._text(item["device_key"], 80),
            device_name=self._text(item["device_name"], 120),
            status=self._text(item["status"], 40),
            initial_health_score=int(item["initial_health_score"]),
            initial_evidence_digest=self._digest(item["initial_evidence_digest"]),
            initial_finding_ids=tuple(
                self._text(value, 100) for value in item["initial_finding_ids"]
            ),
            recommendations=tuple(self._text(value, 400) for value in item["recommendations"]),
            reviewed_steps=tuple(int(value) for value in item.get("reviewed_steps", ())),
            verification_health_score=(
                int(item["verification_health_score"])
                if item.get("verification_health_score") is not None
                else None
            ),
            verification_evidence_digest=(
                self._digest(item["verification_evidence_digest"])
                if item.get("verification_evidence_digest")
                else ""
            ),
            verification_finding_ids=tuple(
                self._text(value, 100) for value in item.get("verification_finding_ids", ())
            ),
            verification_summary=self._optional_text(item.get("verification_summary", ""), 600),
        )
        if session.status not in {"active", "ready_for_verification", "verified"}:
            raise ValueError("invalid repair session status")
        if not 0 <= session.initial_health_score <= 100:
            raise ValueError("invalid initial health score")
        if (
            session.verification_health_score is not None
            and not 0 <= session.verification_health_score <= 100
        ):
            raise ValueError("invalid verification health score")
        if any(
            index < 0 or index >= len(session.recommendations) for index in session.reviewed_steps
        ):
            raise ValueError("invalid reviewed repair checkpoint")
        return session

    def _prune(self) -> None:
        paths = sorted(
            self.root.glob("*.romverse-repair.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for path in paths[self.MAX_SESSIONS :]:
            with suppress(OSError):
                path.unlink()

    @staticmethod
    def _evidence_digest(report: DiagnosticReport) -> str:
        payload = {
            "health_score": report.health_score,
            "findings": sorted(item.finding_id for item in report.findings),
            "evidence": sorted((item.label, item.value, item.source) for item in report.evidence),
            "limitations": sorted(report.limitations),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @staticmethod
    def _text(value: object, maximum: int) -> str:
        if not isinstance(value, str):
            raise TypeError("repair session text field is invalid")
        clean = value.replace("\x00", "").strip()
        if not clean or len(clean) > maximum:
            raise ValueError("repair session text field is invalid")
        return clean

    @classmethod
    def _optional_text(cls, value: object, maximum: int) -> str:
        return "" if value == "" else cls._text(value, maximum)

    @staticmethod
    def _timestamp(value: object) -> str:
        if not isinstance(value, str):
            raise TypeError("repair session timestamp is invalid")
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError("repair session timestamp lacks timezone")
        return value

    @staticmethod
    def _digest(value: object) -> str:
        if not isinstance(value, str) or len(value) != 64:
            raise ValueError("repair evidence digest is invalid")
        int(value, 16)
        return value
