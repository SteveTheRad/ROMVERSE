from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

WORKSPACE_DIRECTORIES = (
    "original_roms",
    "working_roms",
    "builds",
    "projects",
    "apks",
    "backups",
    "snapshots",
    "tools",
    "device_packs",
    "recipes",
    "diagnostics",
    "logs",
    "cache",
    "temp",
)


@dataclass(frozen=True, slots=True)
class WorkspaceResult:
    root: Path
    created: tuple[Path, ...]
    manifest: Path


class WorkspaceInitializer:
    MANIFEST = ".romverse-workspace.json"

    def initialize(self, root: Path) -> WorkspaceResult:
        root = root.expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        created: list[Path] = []
        for name in WORKSPACE_DIRECTORIES:
            path = root / name
            if not path.exists():
                path.mkdir()
                created.append(path)

        manifest = root / self.MANIFEST
        payload = {
            "schema_version": 1,
            "product": "ROMVERSE",
            "initialized_at": datetime.now(UTC).isoformat(),
            "directories": list(WORKSPACE_DIRECTORIES),
            "safety": {"original_roms_immutable_by_policy": True},
        }
        if not manifest.exists():
            manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            created.append(manifest)
        return WorkspaceResult(root, tuple(created), manifest)
