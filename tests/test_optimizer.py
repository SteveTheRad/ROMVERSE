from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from romverse.core.workspace import WorkspaceInitializer
from romverse.diagnostics.optimizer import OptimizerSafetyError, RomverseCacheOptimizer


def _make_old(path, now: datetime) -> None:
    old_ns = int((now - timedelta(days=2)).timestamp() * 1_000_000_000)
    os.utime(path, ns=(old_ns, old_ns))


def test_optimizer_preview_and_clean_are_bounded_to_stale_romverse_cache(tmp_path):
    workspace = WorkspaceInitializer().initialize(tmp_path / "workspace").root
    now = datetime(2026, 8, 29, 2, 0, tzinfo=UTC)
    stale_cache = workspace / "cache" / "nested" / "thumbnail.bin"
    stale_temp = workspace / "temp" / "old-download.part"
    recent = workspace / "cache" / "current-session.bin"
    protected = workspace / "original_roms" / "firmware.zip"
    outside = tmp_path / "personal.txt"
    stale_cache.parent.mkdir(parents=True)
    stale_cache.write_bytes(b"cache")
    stale_temp.write_bytes(b"temporary")
    recent.write_bytes(b"active")
    protected.write_bytes(b"firmware")
    outside.write_bytes(b"personal")
    _make_old(stale_cache, now)
    _make_old(stale_temp, now)
    _make_old(protected, now)
    _make_old(outside, now)
    link = workspace / "cache" / "personal-link"
    try:
        link.symlink_to(outside)
    except OSError:
        link = None

    optimizer = RomverseCacheOptimizer(workspace)
    preview = optimizer.preview(now=now)

    assert {item.relative_path for item in preview.candidates} == {
        "cache/nested/thumbnail.bin",
        "temp/old-download.part",
    }
    assert preview.file_count == 2
    assert preview.total_bytes == len(b"cachetemporary")
    assert preview.skipped_recent == 1
    if link is not None:
        assert preview.skipped_unsafe == 1

    receipt = optimizer.clean(preview)

    assert receipt.files_removed == 2
    assert receipt.bytes_recovered == len(b"cachetemporary")
    assert not stale_cache.exists()
    assert not stale_temp.exists()
    assert recent.read_bytes() == b"active"
    assert protected.read_bytes() == b"firmware"
    assert outside.read_bytes() == b"personal"
    if link is not None:
        assert link.is_symlink()
    payload = json.loads(receipt.receipt_path.read_text(encoding="utf-8"))
    assert payload["format"] == "romverse.optimizer-cleanup-receipt"
    assert payload["status"] == "complete"
    assert payload["scope"] == ["cache", "temp"]
    assert payload["phone_modified"] is False
    assert "original_roms" in payload["excluded"]
    assert json.loads((receipt.receipt_path.parent / "latest.json").read_text()) == payload


def test_optimizer_preserves_a_file_that_changes_after_preview(tmp_path):
    workspace = WorkspaceInitializer().initialize(tmp_path / "workspace").root
    now = datetime(2026, 8, 29, 2, 0, tzinfo=UTC)
    candidate = workspace / "cache" / "stale.bin"
    candidate.write_bytes(b"old")
    _make_old(candidate, now)
    optimizer = RomverseCacheOptimizer(workspace)
    preview = optimizer.preview(now=now)
    candidate.write_bytes(b"new content")

    receipt = optimizer.clean(preview)

    assert receipt.files_removed == 0
    assert receipt.files_changed_or_missing == 1
    assert candidate.read_bytes() == b"new content"


def test_optimizer_rejects_a_tampered_preview_before_writing_a_receipt(tmp_path):
    workspace = WorkspaceInitializer().initialize(tmp_path / "workspace").root
    now = datetime(2026, 8, 29, 2, 0, tzinfo=UTC)
    candidate = workspace / "cache" / "stale.bin"
    candidate.write_bytes(b"old")
    _make_old(candidate, now)
    optimizer = RomverseCacheOptimizer(workspace)
    preview = optimizer.preview(now=now)
    tampered = replace(preview, skipped_recent=preview.skipped_recent + 1)

    with pytest.raises(OptimizerSafetyError, match="fingerprint"):
        optimizer.clean(tampered)

    assert candidate.exists()
    assert not (workspace / "logs" / "optimizer").exists()


def test_optimizer_rejects_a_symlinked_cleanup_root(tmp_path):
    workspace = WorkspaceInitializer().initialize(tmp_path / "workspace").root
    external = tmp_path / "external-cache"
    external.mkdir()
    (workspace / "cache").rmdir()
    try:
        (workspace / "cache").symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable on this host")

    with pytest.raises(OptimizerSafetyError, match="not a real directory"):
        RomverseCacheOptimizer(workspace).preview()


def test_optimizer_requires_timezone_aware_preview_time(tmp_path):
    workspace = WorkspaceInitializer().initialize(tmp_path / "workspace").root

    with pytest.raises(ValueError, match="timezone"):
        RomverseCacheOptimizer(workspace).preview(now=datetime(2026, 8, 29))
