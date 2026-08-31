from __future__ import annotations

import hashlib
import json
import os
import re
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Protocol

from romverse.core.privacy import WorkspacePrivacy
from romverse.guardian.models import GuardianDecision, OperationRequest
from romverse.infrastructure.process import CommandResult


class AuditIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AuditVerification:
    valid: bool
    total_entries: int
    reason: str = ""
    last_hash: str = ""


class AuditSink(Protocol):
    def assert_ready(self) -> None: ...

    def record(
        self,
        request: OperationRequest,
        decision: GuardianDecision,
        result: CommandResult | None,
        duration_ms: int,
        error_type: str = "",
    ) -> None: ...


class GuardianAuditStore:
    """Append-only JSONL audit records linked by SHA-256 hashes."""

    SCHEMA_VERSION = 1
    MAX_FILE_BYTES = 16 * 1024 * 1024
    MAX_RECORDS = 50_000
    MAX_LINE_BYTES = 64 * 1024
    # Older ROMVERSE builds did not roll the ledger before it reached the active-file
    # bound. Recovery remains bounded, and an oversized ledger is rolled only after its
    # complete hash chain has been verified. Corrupt or tampered evidence still fails
    # closed.
    MAX_ROLLOVER_FILE_BYTES = 256 * 1024 * 1024
    MAX_ROLLOVER_RECORDS = 1_000_000
    MAX_ARCHIVE_CHAIN = 64
    MAX_ARCHIVE_TOTAL_BYTES = 1024 * 1024 * 1024

    def __init__(self, workspace: Path) -> None:
        self.path = workspace / "logs" / "guardian-audit.jsonl"
        self.lock_path = workspace / "logs" / "guardian-audit.lock"
        self.archive_dir = workspace / "logs" / "guardian-audit-archives"
        self.privacy = WorkspacePrivacy(workspace)
        self._lock = Lock()
        self._cached_identity: tuple[int, int, int, int, int] | None | object = _UNSET
        self._cached_verification: AuditVerification | None = None
        self._cached_archive_identities: tuple[
            tuple[Path, tuple[int, int, int, int, int] | None | object], ...
        ] = ()

    def assert_ready(self) -> None:
        with self._lock, self._process_lock():
            verification = self._ready_verification_locked()
            if verification.total_entries >= self.MAX_RECORDS:
                verification = self._rollover_locked(verification)
            try:
                current_size = self.path.stat().st_size if self.path.exists() else 0
            except OSError as exc:
                raise AuditIntegrityError("Guardian audit capacity could not be verified") from exc
            if current_size > self.MAX_FILE_BYTES - self.MAX_LINE_BYTES:
                self._rollover_locked(verification)

    def record(
        self,
        request: OperationRequest,
        decision: GuardianDecision,
        result: CommandResult | None,
        duration_ms: int,
        error_type: str = "",
    ) -> None:
        with self._lock, self._process_lock():
            verification = self._ready_verification_locked()
            if verification.total_entries >= self.MAX_RECORDS:
                verification = self._rollover_locked(verification)
            payload = {
                "schema_version": self.SCHEMA_VERSION,
                "sequence": verification.total_entries + 1,
                "timestamp": datetime.now(UTC).isoformat(),
                "previous_hash": verification.last_hash,
                "operation_id": request.operation_id,
                "category": request.category.value,
                "purpose": request.purpose,
                "target": self._redacted_target(request.target),
                "executable": Path(request.executable).name,
                "arguments": self._redacted_arguments(request.arguments),
                "approval_digest": request.approval_digest,
                "allowed": decision.allowed,
                "risk": decision.risk.value,
                "reasons": list(decision.reasons),
                "result": {
                    "returncode": result.returncode if result is not None else None,
                    "timed_out": result.timed_out if result is not None else False,
                    "duration_ms": max(0, duration_ms),
                    "error_type": error_type,
                },
            }
            payload["hash"] = self._hash(payload)
            encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
            encoded_bytes = encoded.encode("utf-8")
            if len(encoded_bytes) > self.MAX_LINE_BYTES:
                raise AuditIntegrityError("Guardian audit record exceeds its bounded size")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            current_size = self.path.stat().st_size if self.path.exists() else 0
            if current_size + len(encoded_bytes) > self.MAX_FILE_BYTES:
                verification = self._rollover_locked(verification)
                payload["sequence"] = verification.total_entries + 1
                payload["previous_hash"] = verification.last_hash
                payload["hash"] = self._hash(
                    {key: value for key, value in payload.items() if key != "hash"}
                )
                encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
                encoded_bytes = encoded.encode("utf-8")
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            self._cached_identity = self._file_identity()
            self._cached_verification = AuditVerification(
                True,
                verification.total_entries + 1,
                last_hash=str(payload["hash"]),
            )

    def _ready_verification_locked(self) -> AuditVerification:
        verification = self._verify_locked()
        if not verification.valid and verification.reason == "audit exceeds its bounded file size":
            verification = self._rollover_locked(verification, legacy_oversized=True)
        if not verification.valid:
            raise AuditIntegrityError(
                f"Guardian audit integrity check failed: {verification.reason}"
            )
        return verification

    def _rollover_locked(
        self,
        verification: AuditVerification,
        *,
        legacy_oversized: bool = False,
    ) -> AuditVerification:
        """Archive a verified full ledger and begin a linked active ledger.

        The archive is moved, never rewritten. The first record in the new active
        ledger carries both the archived chain tail and a SHA-256 of the complete
        archived file, preserving an independently verifiable continuity receipt.
        """

        if not self.path.exists():
            return AuditVerification(True, 0)
        identity_before = self._file_identity()
        if legacy_oversized:
            records, verified_full = self._load(
                max_file_bytes=self.MAX_ROLLOVER_FILE_BYTES,
                max_records=self.MAX_ROLLOVER_RECORDS,
            )
            if verified_full.valid:
                chain_reason, _identities = self._verify_rollover_chain(records)
                if chain_reason:
                    verified_full = AuditVerification(
                        False,
                        verified_full.total_entries,
                        chain_reason,
                        verified_full.last_hash,
                    )
            if not verified_full.valid:
                raise AuditIntegrityError(
                    "Guardian audit rollover refused because legacy evidence failed "
                    f"verification: {verified_full.reason}"
                )
            verification = verified_full
        elif not verification.valid:
            raise AuditIntegrityError(f"Guardian audit rollover refused: {verification.reason}")
        if verification.total_entries <= 0 or not verification.last_hash:
            raise AuditIntegrityError("Guardian audit rollover refused an empty ledger")

        archive_digest = self._file_sha256(self.path)
        if self._file_identity() != identity_before:
            raise AuditIntegrityError("Guardian audit changed during rollover verification")
        archive_name = (
            f"guardian-audit-{verification.total_entries:06d}-{verification.last_hash[:16]}.jsonl"
        )
        archive_path = self.archive_dir / archive_name
        if archive_path.exists():
            raise AuditIntegrityError("Guardian audit archive collision; rollover stopped safely")

        rollover_payload = {
            "schema_version": self.SCHEMA_VERSION,
            "sequence": 1,
            "timestamp": datetime.now(UTC).isoformat(),
            "previous_hash": "",
            "operation_id": "guardian.audit.rollover",
            "category": "read_only",
            "purpose": "Continue the Guardian ledger after lossless archival",
            "target": "host",
            "executable": "romverse",
            "arguments": [],
            "approval_digest": "",
            "allowed": True,
            "risk": "none",
            "reasons": ["verified ledger reached its active-file capacity"],
            "result": {
                "returncode": 0,
                "timed_out": False,
                "duration_ms": 0,
                "error_type": "",
            },
            "rollover": {
                "archive": archive_name,
                "archive_sha256": archive_digest,
                "archived_records": verification.total_entries,
                "archived_last_hash": verification.last_hash,
            },
        }
        rollover_payload["hash"] = self._hash(rollover_payload)
        encoded = json.dumps(rollover_payload, sort_keys=True, separators=(",", ":")) + "\n"
        pending_path = self.path.with_name(f".{archive_name}.pending")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        try:
            with pending_path.open("x", encoding="utf-8") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(self.path, archive_path)
            self._fsync_directory(self.path.parent)
            os.replace(pending_path, self.path)
            self._fsync_directory(self.path.parent)
        except Exception:
            # If the archive move completed, restore the original active name before
            # surfacing the failure. Evidence is never abandoned in a hidden state.
            if not self.path.exists() and archive_path.exists():
                os.replace(archive_path, self.path)
                self._fsync_directory(self.path.parent)
            pending_path.unlink(missing_ok=True)
            raise

        self._cached_identity = _UNSET
        self._cached_verification = None
        self._cached_archive_identities = ()
        return self._verify_locked()

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        try:
            descriptor = os.open(path, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def verify(self) -> AuditVerification:
        with self._lock, self._process_lock():
            return self._verify_locked()

    @contextmanager
    def _process_lock(self):
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

    def read_recent(self, limit: int = 30) -> tuple[dict, ...]:
        if limit <= 0:
            return ()
        with self._lock, self._process_lock():
            verification = self._verify_locked()
            if not verification.valid:
                return ()
            try:
                with self.path.open("r", encoding="utf-8") as stream:
                    lines = deque(stream, maxlen=limit)
                records = tuple(json.loads(line) for line in lines)
            except (OSError, json.JSONDecodeError, TypeError):
                # A verified identity cannot change while the process lock is held, but
                # fail closed if the filesystem behaves unexpectedly.
                self._cached_identity = _UNSET
                self._cached_verification = None
                return ()
            return tuple(reversed(records))

    def _verify_locked(self) -> AuditVerification:
        identity_before = self._file_identity()
        if (
            self._cached_identity == identity_before
            and self._cached_verification is not None
            and self._archive_cache_is_current()
        ):
            return self._cached_verification
        records, verification = self._load()
        archive_identities: tuple[
            tuple[Path, tuple[int, int, int, int, int] | None | object], ...
        ] = ()
        if verification.valid:
            chain_reason, archive_identities = self._verify_rollover_chain(records)
            if chain_reason:
                verification = AuditVerification(
                    False,
                    verification.total_entries,
                    chain_reason,
                    verification.last_hash,
                )
        identity_after = self._file_identity()
        if identity_after != identity_before:
            verification = AuditVerification(
                False,
                verification.total_entries,
                "audit changed during verification",
                verification.last_hash,
            )
        self._cached_identity = identity_after
        self._cached_verification = verification
        self._cached_archive_identities = archive_identities
        return verification

    def _archive_cache_is_current(self) -> bool:
        return all(
            self._path_identity(path) == identity
            for path, identity in self._cached_archive_identities
        )

    def _file_identity(self) -> tuple[int, int, int, int, int] | None | object:
        return self._path_identity(self.path)

    @staticmethod
    def _path_identity(path: Path) -> tuple[int, int, int, int, int] | None | object:
        try:
            stat = path.stat()
        except FileNotFoundError:
            return None
        except OSError:
            return _UNREADABLE
        return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)

    def _verify_rollover_chain(
        self,
        records: list[dict],
        *,
        seen: frozenset[str] = frozenset(),
        total_bytes: int = 0,
    ) -> tuple[
        str,
        tuple[tuple[Path, tuple[int, int, int, int, int] | None | object], ...],
    ]:
        if not records or records[0].get("operation_id") != "guardian.audit.rollover":
            return "", ()
        if len(seen) >= self.MAX_ARCHIVE_CHAIN:
            return "Guardian audit archive chain exceeds its bounded depth", ()
        rollover = records[0].get("rollover")
        if not isinstance(rollover, dict) or set(rollover) != {
            "archive",
            "archive_sha256",
            "archived_records",
            "archived_last_hash",
        }:
            return "Guardian audit rollover receipt has an invalid shape", ()
        archive_name = rollover.get("archive")
        archive_sha256 = rollover.get("archive_sha256")
        archived_records = rollover.get("archived_records")
        archived_last_hash = rollover.get("archived_last_hash")
        if (
            not isinstance(archive_name, str)
            or Path(archive_name).name != archive_name
            or not re.fullmatch(r"guardian-audit-[0-9]{6,7}-[0-9a-f]{16}\.jsonl", archive_name)
            or archive_name in seen
            or not isinstance(archive_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", archive_sha256)
            or isinstance(archived_records, bool)
            or not isinstance(archived_records, int)
            or not 1 <= archived_records <= self.MAX_ROLLOVER_RECORDS
            or not isinstance(archived_last_hash, str)
            or not re.fullmatch(r"[0-9a-f]{64}", archived_last_hash)
            or archive_name
            != f"guardian-audit-{archived_records:06d}-{archived_last_hash[:16]}.jsonl"
        ):
            return "Guardian audit rollover receipt contains invalid archive evidence", ()
        if self.archive_dir.is_symlink():
            return "Guardian audit archive directory is redirected", ()
        archive_path = self.archive_dir / archive_name
        identity_before = self._path_identity(archive_path)
        if (
            identity_before in {None, _UNREADABLE}
            or archive_path.is_symlink()
            or not archive_path.is_file()
        ):
            return "Guardian audit archive is unavailable or unsafe", ()
        assert isinstance(identity_before, tuple)
        archive_bytes = identity_before[2]
        if archive_bytes > self.MAX_ROLLOVER_FILE_BYTES:
            return "Guardian audit archive exceeds its bounded file size", ()
        if total_bytes + archive_bytes > self.MAX_ARCHIVE_TOTAL_BYTES:
            return "Guardian audit archive chain exceeds its bounded total size", ()
        try:
            digest = self._file_sha256(archive_path)
        except OSError:
            return "Guardian audit archive could not be hashed", ()
        identity_after_hash = self._path_identity(archive_path)
        if identity_after_hash != identity_before:
            return "Guardian audit archive changed during verification", ()
        if digest != archive_sha256:
            return "Guardian audit archive digest mismatch", ((archive_path, identity_after_hash),)
        archived, verification = self._load_path(
            archive_path,
            max_file_bytes=self.MAX_ROLLOVER_FILE_BYTES,
            max_records=self.MAX_ROLLOVER_RECORDS,
        )
        identity_after_load = self._path_identity(archive_path)
        identity = ((archive_path, identity_after_load),)
        if identity_after_load != identity_before:
            return "Guardian audit archive changed during verification", identity
        if not verification.valid:
            return f"Guardian audit archive failed verification: {verification.reason}", identity
        if (
            verification.total_entries != archived_records
            or verification.last_hash != archived_last_hash
        ):
            return "Guardian audit archive chain tail does not match its rollover receipt", identity
        nested_reason, nested_identities = self._verify_rollover_chain(
            archived,
            seen=seen | {archive_name},
            total_bytes=total_bytes + archive_bytes,
        )
        return nested_reason, identity + nested_identities

    def _load(
        self,
        *,
        max_file_bytes: int | None = None,
        max_records: int | None = None,
    ) -> tuple[list[dict], AuditVerification]:
        file_limit = self.MAX_FILE_BYTES if max_file_bytes is None else max_file_bytes
        record_limit = self.MAX_RECORDS if max_records is None else max_records
        return self._load_path(
            self.path,
            max_file_bytes=file_limit,
            max_records=record_limit,
        )

    def _load_path(
        self,
        path: Path,
        *,
        max_file_bytes: int,
        max_records: int,
    ) -> tuple[list[dict], AuditVerification]:
        if not path.exists():
            return [], AuditVerification(True, 0)
        if path.is_symlink() or not path.is_file():
            return [], AuditVerification(False, 0, "audit is not a regular local file")
        try:
            if path.stat().st_size > max_file_bytes:
                return [], AuditVerification(False, 0, "audit exceeds its bounded file size")
        except (OSError, UnicodeDecodeError) as exc:
            return [], AuditVerification(False, 0, type(exc).__name__)
        records: list[dict] = []
        previous_hash = ""
        try:
            with path.open("r", encoding="utf-8") as stream:
                for index, line in enumerate(stream, start=1):
                    try:
                        if index > max_records:
                            raise ValueError("record capacity exceeded")
                        if len(line.encode("utf-8")) > self.MAX_LINE_BYTES:
                            raise ValueError("record size exceeded")
                        record = json.loads(line)
                        stored_hash = record.pop("hash")
                        if record.get("schema_version") != self.SCHEMA_VERSION:
                            raise ValueError("unsupported schema")
                        if record.get("sequence") != index:
                            raise ValueError("sequence mismatch")
                        if record.get("previous_hash") != previous_hash:
                            raise ValueError("hash chain mismatch")
                        calculated = self._hash(record)
                        if not isinstance(stored_hash, str) or calculated != stored_hash:
                            raise ValueError("record hash mismatch")
                        record["hash"] = stored_hash
                        records.append(record)
                        previous_hash = stored_hash
                    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                        return records, AuditVerification(
                            False,
                            len(records),
                            f"entry {index}: {exc}",
                            previous_hash,
                        )
        except (OSError, UnicodeDecodeError) as exc:
            return [], AuditVerification(False, 0, type(exc).__name__)
        return records, AuditVerification(True, len(records), last_hash=previous_hash)

    def _redacted_target(self, target: str) -> str:
        return "host" if target == "host" else f"device:{self.privacy.pseudonym(target)}"

    @staticmethod
    def _redacted_arguments(arguments: tuple[str, ...]) -> list[str]:
        redacted: list[str] = []
        hide_next = False
        for argument in arguments:
            if hide_next:
                redacted.append("<redacted-device>")
                hide_next = False
                continue
            redacted.append(argument)
            hide_next = argument == "-s"
        return redacted

    @staticmethod
    def _hash(payload: dict) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


_UNSET = object()
_UNREADABLE = object()
