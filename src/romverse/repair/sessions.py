from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from romverse.core.privacy import WorkspacePrivacy
from romverse.device.models import AndroidDevice
from romverse.diagnostics.models import DiagnosticReport
from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    bounded_regular_files,
    ensure_private_directory,
    read_json_object,
    remove_regular_file,
)
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
    archive_article_keys: tuple[str, ...] = ()
    reviewed_steps: tuple[int, ...] = ()
    verification_health_score: int | None = None
    verification_evidence_digest: str = ""
    verification_finding_ids: tuple[str, ...] = ()
    verification_direction: str = ""
    resolved_finding_ids: tuple[str, ...] = ()
    added_finding_ids: tuple[str, ...] = ()
    verification_summary: str = ""
    record_digest: str = ""

    @property
    def integrity_verified(self) -> bool:
        return bool(self.record_digest)


class RepairSessionStore:
    FORMAT = "romverse.repair-session"
    SCHEMA_VERSION = 2
    LEGACY_SCHEMA_VERSION = 1
    MAXIMUM_BYTES = 256 * 1024
    MAX_SESSIONS = 100
    MAX_SCAN_ENTRIES = 512
    SUFFIX = ".romverse-repair.json"

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.root = workspace / "diagnostics" / "repair-sessions"
        self.privacy = WorkspacePrivacy(workspace)

    def start(
        self,
        concern: RepairConcern,
        device: AndroidDevice,
        report: DiagnosticReport,
        recommendations: tuple[str, ...],
        archive_article_keys: tuple[str, ...] = (),
    ) -> RepairSession:
        now = datetime.now(UTC).isoformat()
        session = self._seal(
            RepairSession(
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
                archive_article_keys=tuple(dict.fromkeys(archive_article_keys))[:8],
            )
        )
        self._save(session)
        self._prune()
        return session

    def update_reviewed(self, session_id: str, reviewed_steps: tuple[int, ...]) -> RepairSession:
        session = self.load(session_id)
        normalized = tuple(sorted(set(self._integer(index) for index in reviewed_steps)))
        if any(index < 0 or index >= len(session.recommendations) for index in normalized):
            raise RepairSessionError("Repair checkpoint is outside this session")
        status = (
            "ready_for_verification"
            if len(normalized) == len(session.recommendations)
            else "active"
        )
        updated = self._seal(
            replace(
                session,
                reviewed_steps=normalized,
                status=status,
                updated_at=datetime.now(UTC).isoformat(),
                record_digest="",
            )
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
        resolved = tuple(sorted(set(session.initial_finding_ids) - set(current_ids)))
        added = tuple(sorted(set(current_ids) - set(session.initial_finding_ids)))
        delta = report.health_score - session.initial_health_score
        direction = self._direction(delta, resolved, added)
        summary = (
            f"Fresh read-only evidence is {direction}: health score {delta:+d}; "
            f"{len(resolved)} finding(s) resolved; {len(added)} new finding(s)."
        )
        updated = self._seal(
            replace(
                session,
                status="verified",
                updated_at=datetime.now(UTC).isoformat(),
                verification_health_score=report.health_score,
                verification_evidence_digest=self._evidence_digest(report),
                verification_finding_ids=current_ids,
                verification_direction=direction,
                resolved_finding_ids=resolved,
                added_finding_ids=added,
                verification_summary=summary,
                record_digest="",
            )
        )
        self._save(updated)
        return updated

    def load(self, session_id: str) -> RepairSession:
        if not re.fullmatch(r"[0-9a-f]{32}", session_id or ""):
            raise RepairSessionError("Invalid repair session identifier")
        path = self.root / f"{session_id}{self.SUFFIX}"
        try:
            payload = read_json_object(
                path,
                boundary=self.workspace,
                maximum_bytes=self.MAXIMUM_BYTES,
            )
            return self._parse(payload)
        except (LocalStoreError, KeyError, TypeError, ValueError) as exc:
            raise RepairSessionError(f"Repair session is unreadable: {exc}") from exc

    def list_recent(self) -> tuple[RepairSession, ...]:
        try:
            paths = bounded_regular_files(
                self.root,
                self.SUFFIX,
                boundary=self.workspace,
                maximum_entries=self.MAX_SCAN_ENTRIES,
            )
        except (FileNotFoundError, LocalStoreError, OSError):
            return ()
        sessions: list[RepairSession] = []
        for path in paths:
            try:
                payload = read_json_object(
                    path,
                    boundary=self.workspace,
                    maximum_bytes=self.MAXIMUM_BYTES,
                )
                sessions.append(self._parse(payload))
            except (LocalStoreError, KeyError, TypeError, ValueError):
                continue
        return tuple(
            sorted(sessions, key=lambda item: item.updated_at, reverse=True)[: self.MAX_SESSIONS]
        )

    def _save(self, session: RepairSession) -> None:
        if not session.integrity_verified or session.record_digest != self._session_digest(session):
            raise RepairSessionError("Repair session integrity envelope is invalid")
        path = self.root / f"{session.session_id}{self.SUFFIX}"
        payload: dict[str, object] = {
            "format": self.FORMAT,
            "schema_version": self.SCHEMA_VERSION,
            "privacy": "pseudonymous-local",
            "session": asdict(session),
        }
        try:
            self._parse(payload)
            ensure_private_directory(self.root, boundary=self.workspace)
            atomic_write_json(
                path,
                payload,
                boundary=self.workspace,
                maximum_bytes=self.MAXIMUM_BYTES,
            )
        except (LocalStoreError, KeyError, TypeError, ValueError) as exc:
            raise RepairSessionError(f"Could not preserve repair session: {exc}") from exc

    def _parse(self, payload: object) -> RepairSession:
        if not isinstance(payload, dict) or set(payload) != {
            "format",
            "schema_version",
            "privacy",
            "session",
        }:
            raise TypeError("repair session envelope is invalid")
        version = self._integer(payload["schema_version"])
        if (
            payload["format"] != self.FORMAT
            or version not in {self.LEGACY_SCHEMA_VERSION, self.SCHEMA_VERSION}
            or payload["privacy"] != "pseudonymous-local"
        ):
            raise ValueError("unsupported repair session schema")
        item = payload["session"]
        if not isinstance(item, dict):
            raise TypeError("repair session payload must be an object")
        current_fields = set(RepairSession.__dataclass_fields__)
        legacy_only = {
            "archive_article_keys",
            "verification_direction",
            "resolved_finding_ids",
            "added_finding_ids",
            "record_digest",
        }
        expected_fields = (
            current_fields if version == self.SCHEMA_VERSION else current_fields - legacy_only
        )
        if set(item) != expected_fields:
            raise ValueError("repair session fields do not match the schema")

        created_at = self._timestamp(item["created_at"])
        updated_at = self._timestamp(item["updated_at"])
        if datetime.fromisoformat(updated_at) < datetime.fromisoformat(created_at):
            raise ValueError("repair session update precedes creation")
        recommendations = self._text_tuple(item["recommendations"], "recommendations", 32, 400)
        reviewed_steps = self._integer_tuple(item.get("reviewed_steps", ()), 32)
        session = RepairSession(
            session_id=self._hex(item["session_id"], 32, "session identifier"),
            created_at=created_at,
            updated_at=updated_at,
            concern=self._concern(item["concern"]),
            device_key=self._hex(item["device_key"], 20, "device key"),
            device_name=self._text(item["device_name"], 120),
            status=self._text(item["status"], 40),
            initial_health_score=self._score(item["initial_health_score"]),
            initial_evidence_digest=self._hex(
                item["initial_evidence_digest"], 64, "initial evidence digest"
            ),
            initial_finding_ids=self._unique_text_tuple(
                item["initial_finding_ids"], "initial finding identifiers", 256, 100
            ),
            recommendations=recommendations,
            archive_article_keys=(
                self._article_keys(item["archive_article_keys"])
                if version == self.SCHEMA_VERSION
                else ()
            ),
            reviewed_steps=reviewed_steps,
            verification_health_score=(
                self._score(item["verification_health_score"])
                if item.get("verification_health_score") is not None
                else None
            ),
            verification_evidence_digest=(
                self._hex(
                    item["verification_evidence_digest"],
                    64,
                    "verification evidence digest",
                )
                if item.get("verification_evidence_digest")
                else ""
            ),
            verification_finding_ids=self._unique_text_tuple(
                item.get("verification_finding_ids", ()),
                "verification finding identifiers",
                256,
                100,
            ),
            verification_direction=(
                self._optional_text(item.get("verification_direction", ""), 40)
                if version == self.SCHEMA_VERSION
                else ""
            ),
            resolved_finding_ids=(
                self._unique_text_tuple(
                    item["resolved_finding_ids"], "resolved finding identifiers", 256, 100
                )
                if version == self.SCHEMA_VERSION
                else ()
            ),
            added_finding_ids=(
                self._unique_text_tuple(
                    item["added_finding_ids"], "added finding identifiers", 256, 100
                )
                if version == self.SCHEMA_VERSION
                else ()
            ),
            verification_summary=self._optional_text(item.get("verification_summary", ""), 600),
            record_digest=(
                self._hex(item["record_digest"], 64, "record digest")
                if version == self.SCHEMA_VERSION
                else ""
            ),
        )
        self._validate_state(session, version)
        if version == self.SCHEMA_VERSION and not hmac.compare_digest(
            session.record_digest, self._session_digest(session)
        ):
            raise ValueError("repair session integrity mismatch")
        return session

    def _validate_state(self, session: RepairSession, version: int) -> None:
        if session.status not in {"active", "ready_for_verification", "verified"}:
            raise ValueError("invalid repair session status")
        if not session.recommendations:
            raise ValueError("repair session has no recommendations")
        if (
            len(set(session.reviewed_steps)) != len(session.reviewed_steps)
            or tuple(sorted(session.reviewed_steps)) != session.reviewed_steps
        ):
            raise ValueError("reviewed repair checkpoints are invalid")
        if any(
            index < 0 or index >= len(session.recommendations) for index in session.reviewed_steps
        ):
            raise ValueError("invalid reviewed repair checkpoint")
        if session.status == "ready_for_verification" and len(session.reviewed_steps) != len(
            session.recommendations
        ):
            raise ValueError("repair session readiness is inconsistent")
        if session.status != "verified":
            if any(
                (
                    session.verification_health_score is not None,
                    bool(session.verification_evidence_digest),
                    bool(session.verification_finding_ids),
                    bool(session.verification_summary),
                    bool(session.verification_direction),
                    bool(session.resolved_finding_ids),
                    bool(session.added_finding_ids),
                )
            ):
                raise ValueError("unverified repair session contains outcome evidence")
            return
        if (
            session.verification_health_score is None
            or not session.verification_evidence_digest
            or not session.verification_summary
        ):
            raise ValueError("verified repair session is incomplete")
        resolved = tuple(
            sorted(set(session.initial_finding_ids) - set(session.verification_finding_ids))
        )
        added = tuple(
            sorted(set(session.verification_finding_ids) - set(session.initial_finding_ids))
        )
        delta = session.verification_health_score - session.initial_health_score
        direction = self._direction(delta, resolved, added)
        if version == self.SCHEMA_VERSION and (
            session.resolved_finding_ids != resolved
            or session.added_finding_ids != added
            or session.verification_direction != direction
        ):
            raise ValueError("repair outcome does not match its evidence")

    def _prune(self) -> None:
        try:
            paths = bounded_regular_files(
                self.root,
                self.SUFFIX,
                boundary=self.workspace,
                maximum_entries=self.MAX_SCAN_ENTRIES,
            )
            dated: list[tuple[int, Path]] = []
            for path in paths:
                try:
                    dated.append((path.stat().st_mtime_ns, path))
                except OSError:
                    continue
            for _modified, path in sorted(dated, reverse=True)[self.MAX_SESSIONS :]:
                try:
                    remove_regular_file(path, boundary=self.workspace)
                except LocalStoreError:
                    continue
        except (FileNotFoundError, LocalStoreError, OSError):
            return

    @classmethod
    def _seal(cls, session: RepairSession) -> RepairSession:
        return replace(session, record_digest=cls._session_digest(session))

    @staticmethod
    def _session_digest(session: RepairSession) -> str:
        payload = asdict(replace(session, record_digest=""))
        payload.pop("record_digest")
        return hashlib.sha256(_canonical(payload)).hexdigest()

    @staticmethod
    def _evidence_digest(report: DiagnosticReport) -> str:
        payload = {
            "health_score": report.health_score,
            "findings": sorted(item.finding_id for item in report.findings),
            "evidence": sorted((item.label, item.value, item.source) for item in report.evidence),
            "limitations": sorted(report.limitations),
        }
        return hashlib.sha256(_canonical(payload)).hexdigest()

    @staticmethod
    def _direction(delta: int, resolved: tuple[str, ...], added: tuple[str, ...]) -> str:
        if delta > 0 or (resolved and not added):
            return "improved"
        if delta < 0 or added:
            return "needs more attention"
        return "unchanged"

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

    @classmethod
    def _text_tuple(
        cls,
        value: object,
        label: str,
        maximum_items: int,
        maximum_text: int,
    ) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)) or len(value) > maximum_items:
            raise ValueError(f"repair session {label} are invalid")
        return tuple(cls._text(item, maximum_text) for item in value)

    @classmethod
    def _unique_text_tuple(
        cls,
        value: object,
        label: str,
        maximum_items: int,
        maximum_text: int,
    ) -> tuple[str, ...]:
        items = cls._text_tuple(value, label, maximum_items, maximum_text)
        if len(set(items)) != len(items):
            raise ValueError(f"repair session {label} are duplicated")
        return items

    @classmethod
    def _article_keys(cls, value: object) -> tuple[str, ...]:
        keys = cls._unique_text_tuple(value, "Archives article keys", 8, 80)
        if any(not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,79}", key) for key in keys):
            raise ValueError("repair session Archives article key is invalid")
        return keys

    @staticmethod
    def _integer(value: object) -> int:
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError("repair session integer field is invalid")
        return value

    @classmethod
    def _integer_tuple(cls, value: object, maximum_items: int) -> tuple[int, ...]:
        if not isinstance(value, (list, tuple)) or len(value) > maximum_items:
            raise ValueError("repair session integer collection is invalid")
        return tuple(cls._integer(item) for item in value)

    @classmethod
    def _score(cls, value: object) -> int:
        score = cls._integer(value)
        if not 0 <= score <= 100:
            raise ValueError("invalid repair health score")
        return score

    @classmethod
    def _timestamp(cls, value: object) -> str:
        text = cls._text(value, 80)
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            raise ValueError("repair session timestamp lacks timezone")
        return text

    @classmethod
    def _hex(cls, value: object, length: int, label: str) -> str:
        text = cls._text(value, length)
        if len(text) != length or not re.fullmatch(r"[0-9a-f]+", text):
            raise ValueError(f"repair session {label} is invalid")
        return text

    @staticmethod
    def _concern(value: object) -> str:
        text = str(value or "")
        if text not in {concern.value for concern in RepairConcern}:
            raise ValueError("repair session concern is invalid")
        return text


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
