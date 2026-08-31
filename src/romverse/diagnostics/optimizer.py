from __future__ import annotations

import hashlib
import json
import os
import stat
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath


class OptimizerSafetyError(RuntimeError):
    """Raised when a cleanup plan cannot be executed inside its safety boundary."""


@dataclass(frozen=True, slots=True)
class CleanupCandidate:
    relative_path: str
    size: int
    modified_ns: int
    device: int
    inode: int


@dataclass(frozen=True, slots=True)
class CleanupPreview:
    schema_version: int
    created_at: str
    minimum_age_seconds: int
    candidates: tuple[CleanupCandidate, ...]
    skipped_recent: int
    skipped_unsafe: int
    plan_digest: str

    @property
    def file_count(self) -> int:
        return len(self.candidates)

    @property
    def total_bytes(self) -> int:
        return sum(candidate.size for candidate in self.candidates)


@dataclass(frozen=True, slots=True)
class CleanupReceipt:
    receipt_id: str
    created_at: str
    plan_digest: str
    files_removed: int
    bytes_recovered: int
    files_changed_or_missing: int
    receipt_path: Path
    phone_modified: bool = False


class RomverseCacheOptimizer:
    """Preview and remove only stale, regular files from ROMVERSE-owned cache roots.

    Projects, originals, builds, backups, tools, logs, and every device operation are
    outside this service's fixed allowlist. Symlinks are never traversed or removed.
    """

    SCHEMA_VERSION = 1
    ALLOWED_ROOTS = ("cache", "temp")
    DEFAULT_MINIMUM_AGE = timedelta(hours=24)
    MAX_CANDIDATES = 50_000

    def __init__(
        self,
        workspace: Path,
        *,
        minimum_age: timedelta = DEFAULT_MINIMUM_AGE,
    ) -> None:
        if minimum_age < timedelta(0):
            raise ValueError("minimum cleanup age cannot be negative")
        self.workspace = workspace.expanduser().resolve()
        self.minimum_age = minimum_age

    def preview(self, *, now: datetime | None = None) -> CleanupPreview:
        observed_at = self._normalized_now(now)
        cutoff_ns = int((observed_at - self.minimum_age).timestamp() * 1_000_000_000)
        candidates: list[CleanupCandidate] = []
        skipped_recent = 0
        skipped_unsafe = 0

        self._validate_workspace()
        for root_name in self.ALLOWED_ROOTS:
            root = self.workspace / root_name
            if not root.exists():
                continue
            root_stat = root.lstat()
            if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
                raise OptimizerSafetyError(
                    f"ROMVERSE cleanup root is not a real directory: {root_name}"
                )
            for path, entry_stat, unsafe in self._walk_regular_files(root):
                if unsafe:
                    skipped_unsafe += 1
                    continue
                if entry_stat.st_mtime_ns > cutoff_ns:
                    skipped_recent += 1
                    continue
                candidates.append(
                    CleanupCandidate(
                        relative_path=path.relative_to(self.workspace).as_posix(),
                        size=entry_stat.st_size,
                        modified_ns=entry_stat.st_mtime_ns,
                        device=entry_stat.st_dev,
                        inode=entry_stat.st_ino,
                    )
                )
                if len(candidates) > self.MAX_CANDIDATES:
                    raise OptimizerSafetyError(
                        "Cleanup preview exceeded the bounded file limit; no files were changed"
                    )

        ordered = tuple(sorted(candidates, key=lambda item: item.relative_path))
        created_at = observed_at.isoformat()
        minimum_age_seconds = int(self.minimum_age.total_seconds())
        digest = self._plan_digest(
            created_at,
            minimum_age_seconds,
            ordered,
            skipped_recent,
            skipped_unsafe,
        )
        return CleanupPreview(
            schema_version=self.SCHEMA_VERSION,
            created_at=created_at,
            minimum_age_seconds=minimum_age_seconds,
            candidates=ordered,
            skipped_recent=skipped_recent,
            skipped_unsafe=skipped_unsafe,
            plan_digest=digest,
        )

    def clean(self, preview: CleanupPreview) -> CleanupReceipt:
        self._validate_preview(preview)
        self._validate_workspace()
        receipt_id, created_at, receipt_path = self._prepare_receipt(preview)
        removed = 0
        recovered = 0
        changed_or_missing = 0

        for candidate in preview.candidates:
            path = self._contained_candidate(candidate.relative_path)
            try:
                current = path.lstat()
            except FileNotFoundError:
                changed_or_missing += 1
                continue
            if not self._same_regular_file(current, candidate):
                changed_or_missing += 1
                continue
            try:
                path.unlink()
            except OSError:
                changed_or_missing += 1
                continue
            removed += 1
            recovered += candidate.size

        return self._finalize_receipt(
            preview,
            receipt_id,
            created_at,
            receipt_path,
            removed,
            recovered,
            changed_or_missing,
        )

    def _walk_regular_files(self, root: Path):
        pending = [root]
        while pending:
            directory = pending.pop()
            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        path = Path(entry.path)
                        try:
                            entry_stat = entry.stat(follow_symlinks=False)
                        except OSError:
                            yield path, os.stat_result((0,) * 10), True
                            continue
                        if stat.S_ISLNK(entry_stat.st_mode):
                            yield path, entry_stat, True
                        elif stat.S_ISDIR(entry_stat.st_mode):
                            pending.append(path)
                        elif stat.S_ISREG(entry_stat.st_mode):
                            yield path, entry_stat, False
                        else:
                            yield path, entry_stat, True
            except OSError as exc:
                raise OptimizerSafetyError(
                    f"Could not safely inspect ROMVERSE cache directory: {exc}"
                ) from exc

    def _validate_workspace(self) -> None:
        try:
            workspace_stat = self.workspace.lstat()
        except OSError as exc:
            raise OptimizerSafetyError(f"ROMVERSE workspace is unavailable: {exc}") from exc
        if stat.S_ISLNK(workspace_stat.st_mode) or not stat.S_ISDIR(workspace_stat.st_mode):
            raise OptimizerSafetyError("ROMVERSE workspace must be a real directory")

    def _contained_candidate(self, relative_path: str) -> Path:
        relative = PurePosixPath(relative_path)
        if (
            relative.is_absolute()
            or len(relative.parts) < 2
            or relative.parts[0] not in self.ALLOWED_ROOTS
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            raise OptimizerSafetyError("Cleanup plan contains a path outside the allowlist")
        path = self.workspace.joinpath(*relative.parts)
        parent = self.workspace
        for part in relative.parts[:-1]:
            parent /= part
            try:
                parent_stat = parent.lstat()
            except OSError as exc:
                raise OptimizerSafetyError(
                    "Cleanup plan parent changed after preview; no unsafe path was followed"
                ) from exc
            if stat.S_ISLNK(parent_stat.st_mode) or not stat.S_ISDIR(parent_stat.st_mode):
                raise OptimizerSafetyError(
                    "Cleanup plan parent changed after preview; no unsafe path was followed"
                )
        return path

    def _validate_preview(self, preview: CleanupPreview) -> None:
        if preview.schema_version != self.SCHEMA_VERSION:
            raise OptimizerSafetyError("Unsupported cleanup preview schema")
        expected = self._plan_digest(
            preview.created_at,
            preview.minimum_age_seconds,
            preview.candidates,
            preview.skipped_recent,
            preview.skipped_unsafe,
        )
        if not preview.plan_digest or not self._constant_time_equal(preview.plan_digest, expected):
            raise OptimizerSafetyError("Cleanup preview fingerprint does not match its contents")
        if preview.minimum_age_seconds != int(self.minimum_age.total_seconds()):
            raise OptimizerSafetyError("Cleanup preview policy no longer matches the active policy")
        if len(preview.candidates) > self.MAX_CANDIDATES:
            raise OptimizerSafetyError("Cleanup preview exceeds the bounded file limit")

    @staticmethod
    def _same_regular_file(current: os.stat_result, candidate: CleanupCandidate) -> bool:
        return (
            stat.S_ISREG(current.st_mode)
            and current.st_size == candidate.size
            and current.st_mtime_ns == candidate.modified_ns
            and current.st_dev == candidate.device
            and current.st_ino == candidate.inode
        )

    def _prepare_receipt(self, preview: CleanupPreview) -> tuple[str, str, Path]:
        created_at = datetime.now(UTC).isoformat()
        receipt_id = hashlib.sha256(f"{preview.plan_digest}:{created_at}".encode()).hexdigest()[:24]
        receipt_root = self.workspace / "logs" / "optimizer"
        receipt_root.mkdir(parents=True, exist_ok=True)
        path = receipt_root / f"cleanup-{receipt_id}.json"
        self._atomic_json(
            path,
            {
                "format": "romverse.optimizer-cleanup-receipt",
                "schema_version": self.SCHEMA_VERSION,
                "receipt_id": receipt_id,
                "created_at": created_at,
                "plan_digest": preview.plan_digest,
                "scope": list(self.ALLOWED_ROOTS),
                "status": "in-progress",
                "phone_modified": False,
            },
        )
        return receipt_id, created_at, path

    def _finalize_receipt(
        self,
        preview: CleanupPreview,
        receipt_id: str,
        created_at: str,
        path: Path,
        removed: int,
        recovered: int,
        changed_or_missing: int,
    ) -> CleanupReceipt:
        payload = {
            "format": "romverse.optimizer-cleanup-receipt",
            "schema_version": self.SCHEMA_VERSION,
            "receipt_id": receipt_id,
            "created_at": created_at,
            "plan_digest": preview.plan_digest,
            "scope": list(self.ALLOWED_ROOTS),
            "status": "complete",
            "minimum_age_seconds": preview.minimum_age_seconds,
            "files_previewed": preview.file_count,
            "bytes_previewed": preview.total_bytes,
            "files_removed": removed,
            "bytes_recovered": recovered,
            "files_changed_or_missing": changed_or_missing,
            "skipped_recent": preview.skipped_recent,
            "skipped_unsafe": preview.skipped_unsafe,
            "phone_modified": False,
            "excluded": [
                "original_roms",
                "working_roms",
                "projects",
                "builds",
                "backups",
                "snapshots",
                "tools",
                "device_packs",
                "recipes",
                "diagnostics",
                "logs",
                "apks",
            ],
        }
        self._atomic_json(path, payload)
        with suppress(OptimizerSafetyError):
            self._atomic_json(path.parent / "latest.json", payload)
        # The immutable primary receipt is authoritative; a convenience pointer
        # failing after the operation must not erase or misreport that evidence.
        return CleanupReceipt(
            receipt_id=receipt_id,
            created_at=created_at,
            plan_digest=preview.plan_digest,
            files_removed=removed,
            bytes_recovered=recovered,
            files_changed_or_missing=changed_or_missing,
            receipt_path=path,
        )

    @staticmethod
    def _atomic_json(path: Path, payload: dict[str, object]) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise OptimizerSafetyError(f"Could not preserve cleanup receipt: {exc}") from exc

    @classmethod
    def _plan_digest(
        cls,
        created_at: str,
        minimum_age_seconds: int,
        candidates: tuple[CleanupCandidate, ...],
        skipped_recent: int,
        skipped_unsafe: int,
    ) -> str:
        canonical = json.dumps(
            {
                "schema_version": cls.SCHEMA_VERSION,
                "created_at": created_at,
                "minimum_age_seconds": minimum_age_seconds,
                "candidates": [asdict(candidate) for candidate in candidates],
                "skipped_recent": skipped_recent,
                "skipped_unsafe": skipped_unsafe,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    @staticmethod
    def _constant_time_equal(left: str, right: str) -> bool:
        import hmac

        return hmac.compare_digest(left, right)

    @staticmethod
    def _normalized_now(value: datetime | None) -> datetime:
        resolved = value or datetime.now(UTC)
        if resolved.tzinfo is None:
            raise ValueError("cleanup preview time must include a timezone")
        return resolved.astimezone(UTC)
