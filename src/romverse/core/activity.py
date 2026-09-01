from __future__ import annotations

import json
import os
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from uuid import uuid4


class ActivityStoreError(RuntimeError):
    """Raised when durable activity history cannot be read or preserved safely."""


@dataclass(frozen=True, slots=True)
class ActivityEvent:
    event_id: str
    recorded_at: str
    category: str
    title: str
    detail: str
    outcome: str
    source: str
    dedupe_key: str = ""


class ActivityStore:
    """Atomic, bounded, privacy-safe ledger of operations ROMVERSE really completed."""

    SCHEMA_VERSION = 1
    MAX_EVENTS = 500
    OUTCOMES = {"success", "attention", "information"}
    _process_lock = Lock()

    def __init__(self, workspace: Path) -> None:
        self.path = workspace / "logs" / "activity-v1.json"
        self.lock_path = workspace / "logs" / "activity-v1.lock"

    def record(
        self,
        category: str,
        title: str,
        detail: str,
        *,
        outcome: str = "information",
        source: str = "ROMVERSE",
        dedupe_key: str = "",
        dedupe_seconds: int = 0,
    ) -> ActivityEvent:
        clean_category = self._text(category, "category", 48)
        clean_title = self._text(title, "title", 140)
        clean_detail = self._text(detail, "detail", 600)
        clean_source = self._text(source, "source", 80)
        clean_key = self._optional_text(dedupe_key, "dedupe key", 160)
        if outcome not in self.OUTCOMES:
            raise ActivityStoreError("Unsupported activity outcome")
        now = datetime.now(UTC)
        with self._locked():
            events = self._load()
            if clean_key and dedupe_seconds > 0:
                existing = next(
                    (event for event in events if event.dedupe_key == clean_key),
                    None,
                )
                if existing is not None:
                    recorded = datetime.fromisoformat(existing.recorded_at)
                    if (now - recorded).total_seconds() < dedupe_seconds:
                        return existing
            event = ActivityEvent(
                event_id=uuid4().hex,
                recorded_at=now.isoformat(),
                category=clean_category,
                title=clean_title,
                detail=clean_detail,
                outcome=outcome,
                source=clean_source,
                dedupe_key=clean_key,
            )
            self._save((event, *events)[: self.MAX_EVENTS])
            return event

    def list_recent(self, limit: int = 50) -> tuple[ActivityEvent, ...]:
        bounded = max(0, min(int(limit), self.MAX_EVENTS))
        with self._locked():
            return self._load()[:bounded]

    def export(self, destination: Path) -> Path:
        destination = destination.expanduser().resolve()
        with self._locked():
            events = self._load()
        payload = {
            "format": "romverse.activity-ledger",
            "schema_version": self.SCHEMA_VERSION,
            "privacy": "redacted",
            "events": [asdict(event) for event in events],
        }
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        except OSError as exc:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
            raise ActivityStoreError(f"Could not export activity ledger: {exc}") from exc
        return destination

    def _load(self) -> tuple[ActivityEvent, ...]:
        if not self.path.exists():
            return ()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if (
                not isinstance(payload, dict)
                or payload.get("format") != "romverse.activity-ledger"
                or payload.get("schema_version") != self.SCHEMA_VERSION
                or payload.get("privacy") != "redacted"
            ):
                raise ValueError("unsupported activity ledger schema")
            raw_events = payload.get("events")
            if not isinstance(raw_events, list) or len(raw_events) > self.MAX_EVENTS:
                raise ValueError("invalid activity event collection")
            events = tuple(self._parse(item) for item in raw_events)
            if len({event.event_id for event in events}) != len(events):
                raise ValueError("duplicate activity identifiers")
            return events
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ActivityStoreError(f"Activity ledger is unreadable: {exc}") from exc

    def _save(self, events: tuple[ActivityEvent, ...]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "format": "romverse.activity-ledger",
            "schema_version": self.SCHEMA_VERSION,
            "privacy": "redacted",
            "events": [asdict(event) for event in events],
        }
        temporary = self.path.with_suffix(".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except OSError as exc:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
            raise ActivityStoreError(f"Could not preserve activity ledger: {exc}") from exc

    def _parse(self, payload: object) -> ActivityEvent:
        if not isinstance(payload, dict):
            raise TypeError("activity event must be an object")
        event_id = self._text(payload["event_id"], "event id", 80)
        recorded_at = self._text(payload["recorded_at"], "timestamp", 80)
        parsed_time = datetime.fromisoformat(recorded_at)
        if parsed_time.tzinfo is None:
            raise ValueError("activity timestamp must include a timezone")
        outcome = self._text(payload["outcome"], "outcome", 24)
        if outcome not in self.OUTCOMES:
            raise ValueError("unsupported activity outcome")
        return ActivityEvent(
            event_id=event_id,
            recorded_at=recorded_at,
            category=self._text(payload["category"], "category", 48),
            title=self._text(payload["title"], "title", 140),
            detail=self._text(payload["detail"], "detail", 600),
            outcome=outcome,
            source=self._text(payload["source"], "source", 80),
            dedupe_key=self._optional_text(payload.get("dedupe_key", ""), "dedupe key", 160),
        )

    @classmethod
    def _text(cls, value: object, label: str, maximum: int) -> str:
        if not isinstance(value, str):
            raise ActivityStoreError(f"Activity {label} must be text")
        clean = value.replace("\x00", "").strip()
        if not clean or len(clean) > maximum:
            raise ActivityStoreError(f"Activity {label} must be 1–{maximum} characters")
        return clean

    @classmethod
    def _optional_text(cls, value: object, label: str, maximum: int) -> str:
        if value == "":
            return ""
        return cls._text(value, label, maximum)

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
