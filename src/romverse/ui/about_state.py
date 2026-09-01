"""Private local persistence for the optional ROMVERSE Origin discovery."""

from __future__ import annotations

import json
import os
import stat
from contextlib import suppress
from pathlib import Path
from uuid import uuid4


class OriginDiscoveryError(RuntimeError):
    """Raised when local Origin discovery state cannot be trusted or preserved."""


class OriginDiscoveryStore:
    """Strict one-bit discovery record with no account, XP, or entitlement authority."""

    MAX_BYTES = 4_096
    _FIELDS = {"format", "schema_version", "discovered", "award"}

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.expanduser().resolve()
        self.directory = self.workspace / "about"
        self.path = self.directory / "origin-discovery.romverse"

    def load(self) -> bool:
        if not self.path.exists() and not self.path.is_symlink():
            return False
        try:
            metadata = self.path.lstat()
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError("discovery state must be a regular file")
            if metadata.st_size > self.MAX_BYTES:
                raise ValueError("discovery state exceeds the size limit")
            descriptor = os.open(self.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
                opened = os.fstat(stream.fileno())
                if not stat.S_ISREG(opened.st_mode):
                    raise ValueError("discovery state must be a regular file")
                raw = stream.read(self.MAX_BYTES + 1)
            if len(raw.encode("utf-8")) > self.MAX_BYTES:
                raise ValueError("discovery state exceeds the size limit")
            payload = json.loads(raw)
            if not isinstance(payload, dict) or set(payload) != self._FIELDS:
                raise ValueError("discovery state fields are invalid")
            if (
                payload["format"] != "romverse.about.origin"
                or payload["schema_version"] != 1
                or payload["discovered"] is not True
                or payload["award"] != "beyond-the-verse"
            ):
                raise ValueError("discovery state values are invalid")
            return True
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise OriginDiscoveryError(f"Origin discovery state is unreadable: {exc}") from exc

    def discover(self) -> None:
        self._prepare_directory()
        self._require_regular_or_missing(self.path)
        encoded = json.dumps(
            {
                "format": "romverse.about.origin",
                "schema_version": 1,
                "discovered": True,
                "award": "beyond-the-verse",
            },
            sort_keys=True,
        )
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
            raise OriginDiscoveryError(f"Could not preserve Origin discovery: {exc}") from exc

    def _prepare_directory(self) -> None:
        if self.directory.is_symlink():
            raise OriginDiscoveryError("Origin discovery directory cannot be a symbolic link")
        try:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            if not self.directory.is_dir():
                raise OriginDiscoveryError("Origin discovery directory must be a directory")
            os.chmod(self.directory, 0o700)
        except OSError as exc:
            raise OriginDiscoveryError(
                f"Could not prepare Origin discovery directory: {exc}"
            ) from exc

    @staticmethod
    def _require_regular_or_missing(path: Path) -> None:
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            return
        except OSError as exc:
            raise OriginDiscoveryError(f"Could not inspect Origin discovery state: {exc}") from exc
        if not stat.S_ISREG(metadata.st_mode):
            raise OriginDiscoveryError("Origin discovery state must be a regular file")
