from __future__ import annotations

import hashlib
import json
from pathlib import Path

MEDIA_BACKUP_REMOTE_PATHS = frozenset(
    {
        "/sdcard/DCIM",
        "/sdcard/Pictures",
        "/sdcard/Movies",
        "/sdcard/Download",
        "/sdcard/Documents",
    }
)


def media_pull_digest(serial: str, remote_path: str, local_path: Path) -> str:
    payload = {
        "schema_version": 1,
        "operation_id": "backup.pull_media",
        "serial": str(serial),
        "remote_path": str(remote_path),
        "local_path": str(local_path),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
