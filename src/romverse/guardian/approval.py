from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from romverse.rom.models import ProjectError


@dataclass(frozen=True, slots=True)
class ApprovalRecord:
    approval_id: str
    plan_digest: str
    target: str
    issued_at: str
    schema_version: int = 2
    expires_at: str = ""
    previous_digest: str = ""
    record_digest: str = ""

    @property
    def legacy(self) -> bool:
        return self.schema_version == 1


@dataclass(frozen=True, slots=True)
class ApprovalVerification:
    valid: bool
    total_entries: int
    active_entries: int
    legacy_entries: int
    reason: str


@dataclass(frozen=True, slots=True)
class _ApprovalRead:
    records: tuple[ApprovalRecord, ...]
    verification: ApprovalVerification
    last_link: str


class ApprovalStore:
    """Short-lived exact approvals with an append-only SHA-256 integrity chain."""

    NAME = "guardian-approvals.jsonl"
    SCHEMA_VERSION = 2
    VALID_FOR = timedelta(minutes=10)
    MAX_FILE_BYTES = 4 * 1024 * 1024
    MAX_RECORDS = 10_000
    GENESIS_DIGEST = "0" * 64

    def __init__(
        self,
        workspace: Path,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.path = workspace / "logs" / self.NAME
        self._clock = clock or (lambda: datetime.now(UTC))

    def issue(self, plan_digest: str, target: str) -> ApprovalRecord:
        _bounded_text(plan_digest, "plan digest", 256)
        _bounded_text(target, "approval target", 256)
        loaded = self._read()
        if not loaded.verification.valid:
            raise ProjectError(
                "Guardian approval history failed integrity checks; preserve it for diagnosis before issuing another approval"
            )
        issued = self._aware_now()
        unsigned: dict[str, object] = {
            "approval_id": uuid4().hex,
            "plan_digest": plan_digest,
            "target": target,
            "issued_at": issued.isoformat(),
            "schema_version": self.SCHEMA_VERSION,
            "expires_at": (issued + self.VALID_FOR).isoformat(),
            "previous_digest": loaded.last_link,
        }
        record = ApprovalRecord(**unsigned, record_digest=_record_digest(unsigned))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(asdict(record), sort_keys=True, separators=(",", ":")) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        verified = self._read()
        if (
            not verified.verification.valid
            or not verified.records
            or verified.records[-1] != record
        ):
            raise ProjectError("Guardian could not verify the newly written approval record")
        return record

    def is_approved(self, plan_digest: str, target: str) -> bool:
        loaded = self._read()
        if not loaded.verification.valid:
            return False
        now = self._aware_now()
        return any(
            not record.legacy
            and record.plan_digest == plan_digest
            and record.target == target
            and _timestamp(record.issued_at) <= now < _timestamp(record.expires_at)
            for record in loaded.records
        )

    def count(self) -> int:
        loaded = self._read()
        return loaded.verification.total_entries if loaded.verification.valid else 0

    def read_recent(self, limit: int = 20) -> tuple[ApprovalRecord, ...]:
        if limit <= 0:
            return ()
        loaded = self._read()
        if not loaded.verification.valid:
            return ()
        return tuple(reversed(loaded.records[-min(limit, 100) :]))

    def verify(self) -> ApprovalVerification:
        return self._read().verification

    def _read(self) -> _ApprovalRead:
        if not self.path.exists():
            return _ApprovalRead(
                (),
                ApprovalVerification(True, 0, 0, 0, "No Guardian approvals have been recorded"),
                self.GENESIS_DIGEST,
            )
        if self.path.is_symlink() or not self.path.is_file():
            return self._rejected("Guardian approval history is not a regular file")
        try:
            if self.path.stat().st_size > self.MAX_FILE_BYTES:
                return self._rejected("Guardian approval history exceeds its size boundary")
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return self._rejected("Guardian approval history could not be read")
        if len(lines) > self.MAX_RECORDS:
            return self._rejected("Guardian approval history contains too many records")
        records: list[ApprovalRecord] = []
        link = self.GENESIS_DIGEST
        try:
            for line in lines:
                if not line or len(line) > 4096:
                    raise ValueError("Guardian approval record length is invalid")
                data = json.loads(line)
                if not isinstance(data, dict):
                    raise ValueError("Guardian approval record is not an object")
                schema = data.get("schema_version")
                if schema is None:
                    if set(data) != {"approval_id", "plan_digest", "target", "issued_at"}:
                        raise ValueError("Legacy Guardian approval shape is invalid")
                    record = ApprovalRecord(
                        str(data["approval_id"]),
                        str(data["plan_digest"]),
                        str(data["target"]),
                        str(data["issued_at"]),
                        schema_version=1,
                    )
                    self._validate_identity(record)
                    link = _legacy_link(link, data)
                elif schema == self.SCHEMA_VERSION:
                    record = ApprovalRecord(**data)
                    self._validate_identity(record)
                    issued = _timestamp(record.issued_at)
                    expires = _timestamp(record.expires_at)
                    unsigned = asdict(record)
                    expected = str(unsigned.pop("record_digest", ""))
                    if (
                        expires - issued != self.VALID_FOR
                        or record.previous_digest != link
                        or not _sha256_value(expected)
                        or expected != _record_digest(unsigned)
                    ):
                        raise ValueError("Guardian approval integrity chain is invalid")
                    link = record.record_digest
                else:
                    raise ValueError("Guardian approval schema is unsupported")
                records.append(record)
        except (ValueError, TypeError, KeyError, ProjectError, json.JSONDecodeError):
            return self._rejected("Guardian approval history failed integrity validation")
        now = self._aware_now()
        active = sum(
            not record.legacy
            and _timestamp(record.issued_at) <= now < _timestamp(record.expires_at)
            for record in records
        )
        legacy = sum(record.legacy for record in records)
        return _ApprovalRead(
            tuple(records),
            ApprovalVerification(
                True,
                len(records),
                active,
                legacy,
                "SHA-256 approval chain verified; legacy records remain audit-only",
            ),
            link,
        )

    def _validate_identity(self, record: ApprovalRecord) -> None:
        _bounded_text(record.approval_id, "approval id", 80)
        _bounded_text(record.plan_digest, "plan digest", 256)
        _bounded_text(record.target, "approval target", 256)
        _timestamp(record.issued_at)

    def _aware_now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ProjectError("Guardian approval clock must include a timezone")
        return value.astimezone(UTC)

    @classmethod
    def _rejected(cls, reason: str) -> _ApprovalRead:
        return _ApprovalRead((), ApprovalVerification(False, 0, 0, 0, reason), cls.GENESIS_DIGEST)


def _bounded_text(value: str, label: str, maximum: int) -> None:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= maximum
        or any(ord(character) < 32 for character in value)
    ):
        raise ProjectError(f"Approval {label} is invalid")


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Guardian approval timestamp requires a timezone")
    return parsed.astimezone(UTC)


def _record_digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _legacy_link(previous: str, payload: object) -> str:
    return _record_digest({"legacy": payload, "previous_digest": previous})


def _sha256_value(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)
