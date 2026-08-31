from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

# Android's bounded ``ls -1t`` form returns filenames only, newest modified first.
ASCENSION_OUTPUT_LIST_COMMAND = ("shell", "ls", "-1t", "/sdcard/Download")
MAGISK_OUTPUT_NAME = re.compile(
    r"magisk[_-]patched[A-Za-z0-9_.-]{0,96}\.img",
    re.IGNORECASE,
)
KERNELSU_OUTPUT_NAME = re.compile(
    r"kernelsu[_-](?:patched|restore)[A-Za-z0-9_.-]{0,96}\.img",
    re.IGNORECASE,
)
ASCENSION_OUTPUT_NAME = re.compile(
    rf"(?:{MAGISK_OUTPUT_NAME.pattern}|{KERNELSU_OUTPUT_NAME.pattern})",
    re.IGNORECASE,
)


def ascension_output_matches_method(name: str, method: str) -> bool:
    """Return whether a safe manager filename belongs to the selected root route."""

    return ascension_output_method(name) == method


def ascension_output_method(name: str) -> str | None:
    """Classify only filenames that positively identify a supported manager output."""

    if MAGISK_OUTPUT_NAME.fullmatch(name):
        return "magisk"
    if KERNELSU_OUTPUT_NAME.fullmatch(name):
        return "kernelsu_lkm"
    return None


def ascension_output_list_digest(serial: str) -> str:
    return _digest(
        {
            "schema_version": 2,
            "operation_id": "ascension.list_outputs",
            "serial": serial,
            "directory": "/sdcard/Download",
            "ordering": "modified-descending",
        }
    )


def ascension_output_pull_digest(serial: str, remote_path: str, local_path: Path) -> str:
    return _digest(
        {
            "schema_version": 1,
            "operation_id": "ascension.pull_output",
            "serial": serial,
            "remote_path": remote_path,
            "local_path": str(local_path),
        }
    )


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
