from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath
from threading import Lock
from uuid import uuid4


class LiveConsoleStoreError(RuntimeError):
    """Raised when the privacy-safe Live Console ledger cannot be trusted."""


class MissionState(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    ATTENTION = "attention"
    INFORMATION = "information"


class MissionConfidence(StrEnum):
    VERIFIED = "verified"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNCONFIRMED = "unconfirmed"
    NOT_APPLICABLE = "not-applicable"


@dataclass(frozen=True, slots=True)
class LiveConsoleEvent:
    event_id: str
    mission_id: str
    recorded_at: str
    updated_at: str
    source: str
    stage: str
    title: str
    summary: str
    explanation: str
    next_action: str
    state: MissionState
    progress_percent: int
    confidence: MissionConfidence
    guardian_protected: bool
    project_id: str = ""
    evidence_refs: tuple[str, ...] = ()
    dedupe_key: str = ""

    @property
    def terminal(self) -> bool:
        return self.state in {
            MissionState.SUCCEEDED,
            MissionState.FAILED,
            MissionState.BLOCKED,
            MissionState.ATTENTION,
        }


class LiveConsoleEventStore:
    """Atomic, bounded ledger containing only events ROMVERSE actually reported.

    The store deliberately has no API that marks an operation successful by inference.
    Producers must finish a known running mission with an explicit terminal outcome.
    """

    FORMAT = "romverse.live-console"
    SCHEMA_VERSION = 1
    MAX_EVENTS = 1_000
    _process_lock = Lock()

    def __init__(self, workspace: Path) -> None:
        self.path = workspace / "logs" / "live-console-v1.json"
        self.lock_path = workspace / "logs" / "live-console-v1.lock"

    def start(
        self,
        *,
        source: str,
        stage: str,
        title: str,
        summary: str,
        explanation: str,
        next_action: str,
        project_id: str = "",
        confidence: MissionConfidence = MissionConfidence.NOT_APPLICABLE,
        guardian_protected: bool = True,
        evidence_refs: tuple[str, ...] = (),
    ) -> LiveConsoleEvent:
        now = datetime.now(UTC).isoformat()
        event = self._event(
            event_id=uuid4().hex,
            mission_id=uuid4().hex,
            recorded_at=now,
            updated_at=now,
            source=source,
            stage=stage,
            title=title,
            summary=summary,
            explanation=explanation,
            next_action=next_action,
            state=MissionState.RUNNING,
            progress_percent=0,
            confidence=confidence,
            guardian_protected=guardian_protected,
            project_id=project_id,
            evidence_refs=evidence_refs,
        )
        with self._locked():
            events = self._load_unlocked()
            self._save_unlocked((event, *events)[: self.MAX_EVENTS])
        return event

    def progress(
        self,
        mission_id: str,
        progress_percent: int,
        *,
        summary: str = "",
        explanation: str = "",
        next_action: str = "",
    ) -> LiveConsoleEvent:
        bounded = self._progress(progress_percent)
        with self._locked():
            events = list(self._load_unlocked())
            index, current = self._running(events, mission_id)
            if bounded < current.progress_percent:
                raise LiveConsoleStoreError("Live Console progress cannot move backwards")
            updated = replace(
                current,
                updated_at=datetime.now(UTC).isoformat(),
                progress_percent=bounded,
                summary=self._replacement(summary, current.summary, "summary", 500),
                explanation=self._replacement(
                    explanation, current.explanation, "explanation", 1_000
                ),
                next_action=self._replacement(next_action, current.next_action, "next action", 500),
            )
            events[index] = updated
            self._save_unlocked(tuple(events))
        return updated

    def finish(
        self,
        mission_id: str,
        state: MissionState,
        *,
        summary: str,
        explanation: str,
        next_action: str,
        confidence: MissionConfidence = MissionConfidence.NOT_APPLICABLE,
        evidence_refs: tuple[str, ...] = (),
    ) -> LiveConsoleEvent:
        if state not in {
            MissionState.SUCCEEDED,
            MissionState.FAILED,
            MissionState.BLOCKED,
            MissionState.ATTENTION,
        }:
            raise LiveConsoleStoreError("A Live Console mission needs an explicit terminal state")
        with self._locked():
            events = list(self._load_unlocked())
            index, current = self._running(events, mission_id)
            now = datetime.now(UTC).isoformat()
            events[index] = current
            final = self._event(
                event_id=uuid4().hex,
                mission_id=mission_id,
                recorded_at=now,
                updated_at=now,
                source=current.source,
                stage=current.stage,
                title=current.title,
                summary=summary,
                explanation=explanation,
                next_action=next_action,
                state=state,
                progress_percent=100
                if state is MissionState.SUCCEEDED
                else current.progress_percent,
                confidence=confidence,
                guardian_protected=current.guardian_protected,
                project_id=current.project_id,
                evidence_refs=evidence_refs or current.evidence_refs,
            )
            self._save_unlocked((final, *events)[: self.MAX_EVENTS])
        return final

    def note(
        self,
        *,
        source: str,
        stage: str,
        title: str,
        summary: str,
        explanation: str,
        next_action: str,
        state: MissionState = MissionState.INFORMATION,
        progress_percent: int = 100,
        confidence: MissionConfidence = MissionConfidence.NOT_APPLICABLE,
        guardian_protected: bool = True,
        project_id: str = "",
        evidence_refs: tuple[str, ...] = (),
        dedupe_key: str = "",
    ) -> LiveConsoleEvent:
        if state not in {
            MissionState.INFORMATION,
            MissionState.ATTENTION,
            MissionState.BLOCKED,
        }:
            raise LiveConsoleStoreError("Notes may only report information, attention, or blocked")
        now = datetime.now(UTC).isoformat()
        event = self._event(
            event_id=uuid4().hex,
            mission_id="",
            recorded_at=now,
            updated_at=now,
            source=source,
            stage=stage,
            title=title,
            summary=summary,
            explanation=explanation,
            next_action=next_action,
            state=state,
            progress_percent=progress_percent,
            confidence=confidence,
            guardian_protected=guardian_protected,
            project_id=project_id,
            evidence_refs=evidence_refs,
            dedupe_key=dedupe_key,
        )
        with self._locked():
            events = self._load_unlocked()
            if event.dedupe_key:
                existing = next(
                    (item for item in events if item.dedupe_key == event.dedupe_key), None
                )
                if existing is not None:
                    return existing
            self._save_unlocked((event, *events)[: self.MAX_EVENTS])
        return event

    def list_recent(self, limit: int = 200) -> tuple[LiveConsoleEvent, ...]:
        bounded = max(0, min(int(limit), self.MAX_EVENTS))
        with self._locked():
            return self._load_unlocked()[:bounded]

    def _event(self, **values: object) -> LiveConsoleEvent:
        values["event_id"] = self._identifier(values.get("event_id"), "event id")
        mission_id = values.get("mission_id", "")
        values["mission_id"] = self._identifier(mission_id, "mission id") if mission_id else ""
        values["recorded_at"] = self._timestamp(values.get("recorded_at"), "recorded at")
        values["updated_at"] = self._timestamp(values.get("updated_at"), "updated at")
        for name, maximum in (
            ("source", 80),
            ("stage", 100),
            ("title", 180),
            ("summary", 500),
            ("explanation", 1_000),
            ("next_action", 500),
        ):
            values[name] = self._text(values.get(name), name.replace("_", " "), maximum)
        values["project_id"] = self._optional_text(values.get("project_id", ""), "project id", 100)
        values["dedupe_key"] = self._optional_text(values.get("dedupe_key", ""), "dedupe key", 180)
        values["progress_percent"] = self._progress(values.get("progress_percent", 0))
        values["state"] = MissionState(values.get("state"))
        values["confidence"] = MissionConfidence(values.get("confidence"))
        if not isinstance(values.get("guardian_protected"), bool):
            raise LiveConsoleStoreError("Guardian protection marker must be true or false")
        refs = values.get("evidence_refs", ())
        if not isinstance(refs, (list, tuple)) or len(refs) > 20:
            raise LiveConsoleStoreError("Live Console evidence references are invalid")
        values["evidence_refs"] = tuple(self._evidence_ref(item) for item in refs)
        return LiveConsoleEvent(**values)  # type: ignore[arg-type]

    def _load_unlocked(self) -> tuple[LiveConsoleEvent, ...]:
        if not self.path.exists():
            return ()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            raw_events = payload["events"]
            if (
                payload.get("format") != self.FORMAT
                or payload.get("schema_version") != self.SCHEMA_VERSION
                or payload.get("privacy") != "redacted"
                or not isinstance(raw_events, list)
                or len(raw_events) > self.MAX_EVENTS
            ):
                raise ValueError("unsupported Live Console ledger schema")
            expected = payload.get("ledger_digest")
            if not isinstance(expected, str) or expected != self._digest(raw_events):
                raise ValueError("Live Console ledger digest mismatch")
            events = tuple(self._event(**item) for item in raw_events)
            if len({item.event_id for item in events}) != len(events):
                raise ValueError("duplicate Live Console event identifiers")
            return events
        except (
            OSError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
            LiveConsoleStoreError,
        ) as exc:
            raise LiveConsoleStoreError(f"Live Console ledger is unreadable: {exc}") from exc

    def _save_unlocked(self, events: tuple[LiveConsoleEvent, ...]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        encoded = [asdict(item) for item in events]
        payload = {
            "format": self.FORMAT,
            "schema_version": self.SCHEMA_VERSION,
            "privacy": "redacted",
            "ledger_digest": self._digest(encoded),
            "events": encoded,
        }
        temporary = self.path.with_name(f".{self.path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("x", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except OSError as exc:
            raise LiveConsoleStoreError(f"Could not preserve Live Console events: {exc}") from exc
        finally:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)

    @staticmethod
    def _running(events: list[LiveConsoleEvent], mission_id: str) -> tuple[int, LiveConsoleEvent]:
        clean = LiveConsoleEventStore._identifier(mission_id, "mission id")
        result = next(
            (
                (index, item)
                for index, item in enumerate(events)
                if item.mission_id == clean and item.state is MissionState.RUNNING
            ),
            None,
        )
        if result is None:
            raise LiveConsoleStoreError("No running Live Console mission matches this update")
        return result

    @staticmethod
    def _replacement(value: str, existing: str, label: str, maximum: int) -> str:
        return LiveConsoleEventStore._text(value, label, maximum) if value else existing

    @staticmethod
    def _progress(value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
            raise LiveConsoleStoreError("Live Console progress must be an integer from 0 to 100")
        return value

    @staticmethod
    def _identifier(value: object, label: str) -> str:
        if not isinstance(value, str):
            raise LiveConsoleStoreError(f"Live Console {label} must be text")
        clean = value.strip()
        if not clean or len(clean) > 100 or not clean.replace("-", "").isalnum():
            raise LiveConsoleStoreError(f"Live Console {label} is invalid")
        return clean

    @staticmethod
    def _text(value: object, label: str, maximum: int) -> str:
        if not isinstance(value, str):
            raise LiveConsoleStoreError(f"Live Console {label} must be text")
        clean = value.replace("\x00", "").strip()
        if not clean or len(clean) > maximum:
            raise LiveConsoleStoreError(f"Live Console {label} must contain 1–{maximum} characters")
        return clean

    @staticmethod
    def _timestamp(value: object, label: str) -> str:
        if not isinstance(value, str):
            raise LiveConsoleStoreError(f"Live Console {label} must be text")
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise LiveConsoleStoreError(f"Live Console {label} is invalid") from exc
        if parsed.tzinfo is None:
            raise LiveConsoleStoreError(f"Live Console {label} needs a timezone")
        return value

    @classmethod
    def _optional_text(cls, value: object, label: str, maximum: int) -> str:
        return "" if value == "" else cls._text(value, label, maximum)

    @classmethod
    def _evidence_ref(cls, value: object) -> str:
        clean = cls._text(value, "evidence reference", 220).replace("\\", "/")
        path = PurePosixPath(clean)
        if path.is_absolute() or ".." in path.parts:
            raise LiveConsoleStoreError(
                "Evidence references must stay inside the ROMVERSE workspace"
            )
        lowered = clean.casefold()
        if any(secret in lowered for secret in ("serial=", "token=", "password=", "secret=")):
            raise LiveConsoleStoreError("Evidence references cannot contain private credentials")
        return clean

    @staticmethod
    def _digest(events: list[dict[str, object]]) -> str:
        canonical = json.dumps(events, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @contextmanager
    def _locked(self):
        with self._process_lock:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            with self.lock_path.open("a+") as stream:
                try:
                    import fcntl

                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
                except ImportError:
                    pass
                try:
                    yield
                finally:
                    try:
                        import fcntl

                        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
                    except ImportError:
                        pass
