from __future__ import annotations

import json
import os
import stat
from concurrent.futures import ThreadPoolExecutor

import pytest

from romverse.infrastructure.local_store import (
    LocalStoreConflictError,
    LocalStoreError,
    exclusive_create_json,
    read_json_object,
)


def test_exclusive_json_create_has_exactly_one_concurrent_winner(tmp_path) -> None:
    target = tmp_path / "private" / "claim.json"

    def attempt(number: int) -> tuple[str, int]:
        try:
            exclusive_create_json(
                target,
                {"winner": number},
                boundary=tmp_path,
                maximum_bytes=1024,
            )
            return "created", number
        except LocalStoreConflictError:
            return "conflict", number

    with ThreadPoolExecutor(max_workers=16) as pool:
        outcomes = tuple(pool.map(attempt, range(32)))

    created = [number for outcome, number in outcomes if outcome == "created"]
    assert len(created) == 1
    assert sum(outcome == "conflict" for outcome, _number in outcomes) == 31
    assert read_json_object(target, boundary=tmp_path, maximum_bytes=1024) == {"winner": created[0]}
    if os.name != "nt":
        assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_exclusive_json_create_never_replaces_existing_or_linked_entry(tmp_path) -> None:
    target = tmp_path / "claim.json"
    exclusive_create_json(
        target,
        {"claim": "first"},
        boundary=tmp_path,
        maximum_bytes=1024,
    )

    with pytest.raises(LocalStoreConflictError, match="already exists"):
        exclusive_create_json(
            target,
            {"claim": "second"},
            boundary=tmp_path,
            maximum_bytes=1024,
        )
    assert json.loads(target.read_text(encoding="utf-8")) == {"claim": "first"}

    if os.name != "nt":
        linked = tmp_path / "linked.json"
        linked.symlink_to(target.name)
        with pytest.raises(LocalStoreConflictError, match="already exists"):
            exclusive_create_json(
                linked,
                {"claim": "replacement"},
                boundary=tmp_path,
                maximum_bytes=1024,
            )
        assert json.loads(target.read_text(encoding="utf-8")) == {"claim": "first"}


def test_exclusive_json_create_enforces_boundary_and_size(tmp_path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside" / "claim.json"
    with pytest.raises(LocalStoreError, match="escapes"):
        exclusive_create_json(
            outside,
            {"claim": "outside"},
            boundary=tmp_path,
            maximum_bytes=1024,
        )
    with pytest.raises(LocalStoreError, match="size boundary"):
        exclusive_create_json(
            tmp_path / "large.json",
            {"claim": "x" * 2048},
            boundary=tmp_path,
            maximum_bytes=128,
        )
