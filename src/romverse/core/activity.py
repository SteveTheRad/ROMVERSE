from __future__ import annotations

import json
import os
import stat
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
    MAX_FILE_BYTES = 1_048_576
    OUTCOMES = {"success", "attention", "information"}
    _ROOT_FIELDS = {"format", "schema_version", "privacy", "events"}
    _EVENT_FIELDS = {
        "event_id",
        "recorded_at",
        "category",
        "title",
        "detail",
        "outcome",
        "source",
        "dedupe_key",
    }
    _process_lock = Lock()

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.expanduser().resolve()
        self.directory = self.workspace / "logs"
        self.path = self.directory / "activity-v1.json"
        self.lock_path = self.directory / "activity-v1.lock"

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
        self._require_regular_or_missing(destination, "activity export")
        temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
            os.chmod(destination, 0o600)
        except OSError as exc:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
            raise ActivityStoreError(f"Could not export activity ledger: {exc}") from exc
        return destination

    def _load(self) -> tuple[ActivityEvent, ...]:
        if not self.path.exists() and not self.path.is_symlink():
            return ()
        try:
            metadata = self.path.lstat()
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError("activity ledger must be a regular file")
            if metadata.st_size > self.MAX_FILE_BYTES:
                raise ValueError("activity ledger exceeds the size limit")
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(self.path, flags)
            with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
                opened = os.fstat(stream.fileno())
                if not stat.S_ISREG(opened.st_mode):
                    raise ValueError("activity ledger must be a regular file")
                raw = stream.read(self.MAX_FILE_BYTES + 1)
            if len(raw.encode("utf-8")) > self.MAX_FILE_BYTES:
                raise ValueError("activity ledger exceeds the size limit")
            payload = json.loads(raw)
            if (
                not isinstance(payload, dict)
                or set(payload) != self._ROOT_FIELDS
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
        except (
            ActivityStoreError,
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise ActivityStoreError(f"Activity ledger is unreadable: {exc}") from exc

    def _save(self, events: tuple[ActivityEvent, ...]) -> None:
        self._prepare_directory()
        self._require_regular_or_missing(self.path, "activity ledger")
        payload = {
            "format": "romverse.activity-ledger",
            "schema_version": self.SCHEMA_VERSION,
            "privacy": "redacted",
            "events": [asdict(event) for event in events],
        }
        encoded = json.dumps(payload, indent=2) + "\n"
        if len(encoded.encode("utf-8")) > self.MAX_FILE_BYTES:
            raise ActivityStoreError("Activity ledger exceeds the size limit")
        temporary = self.path.with_name(f".{self.path.name}.{uuid4().hex}.tmp")
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
        except OSError as exc:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
            raise ActivityStoreError(f"Could not preserve activity ledger: {exc}") from exc

    def _parse(self, payload: object) -> ActivityEvent:
        if not isinstance(payload, dict):
            raise TypeError("activity event must be an object")
        if set(payload) != self._EVENT_FIELDS:
            raise ValueError("activity event fields are invalid")
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
            self._prepare_directory()
            self._require_regular_or_missing(self.lock_path, "activity lock")
            flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(self.lock_path, flags, 0o600)
            os.chmod(self.lock_path, 0o600)
            with os.fdopen(descriptor, "a+") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ActivityStoreError("Activity lock must be a regular file")
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

    def _prepare_directory(self) -> None:
        if self.directory.is_symlink():
            raise ActivityStoreError("Activity directory cannot be a symbolic link")
        try:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            if not self.directory.is_dir():
                raise ActivityStoreError("Activity directory must be a directory")
            os.chmod(self.directory, 0o700)
        except OSError as exc:
            raise ActivityStoreError(f"Could not prepare activity directory: {exc}") from exc

    @staticmethod
    def _require_regular_or_missing(path: Path, label: str) -> None:
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            return
        except OSError as exc:
            raise ActivityStoreError(f"Could not inspect {label}: {exc}") from exc
        if not stat.S_ISREG(metadata.st_mode):
            raise ActivityStoreError(f"{label.title()} must be a regular file")
