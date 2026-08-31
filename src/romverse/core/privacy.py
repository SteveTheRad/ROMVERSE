from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from contextlib import suppress
from pathlib import Path
from threading import Lock


class WorkspacePrivacy:
    """Owns the local secret used for non-reversible workspace pseudonyms."""

    def __init__(self, workspace: Path) -> None:
        self.path = workspace / ".romverse-privacy.json"
        self._lock = Lock()

    def pseudonym(self, value: str, length: int = 20) -> str:
        digest = hmac.new(self._key(), value.encode("utf-8"), hashlib.sha256).hexdigest()
        return digest[:length]

    def _key(self) -> bytes:
        with self._lock:
            if self.path.exists():
                data = json.loads(self.path.read_text(encoding="utf-8"))
                return bytes.fromhex(data["salt"])
            salt = secrets.token_bytes(32)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps({"schema_version": 1, "salt": salt.hex()}, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, self.path)
            with suppress(OSError):
                self.path.chmod(0o600)
            return salt
