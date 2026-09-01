from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PackageCandidate:
    path: str
    name: str
    size_bytes: int
    sha256: str


def inventory_apks(tree_root: Path) -> tuple[PackageCandidate, ...]:
    candidates: list[PackageCandidate] = []
    for path in sorted(tree_root.rglob("*.apk")):
        if path.is_symlink() or not path.is_file():
            continue
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(4 * 1024 * 1024):
                digest.update(chunk)
        candidates.append(
            PackageCandidate(
                path.relative_to(tree_root).as_posix(),
                path.stem,
                path.stat().st_size,
                digest.hexdigest(),
            )
        )
    return tuple(candidates)
