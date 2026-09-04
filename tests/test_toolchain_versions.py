from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

import pytest

from romverse.infrastructure.toolchain_evidence import ToolchainEvidenceService
from romverse.infrastructure.toolchain_versions import (
    VersionedToolchainError,
    VersionedToolchainStore,
)
from romverse.infrastructure.tools import ToolStatus

AVB_SOURCE = (
    "https://android.googlesource.com/platform/external/avb/+/refs/heads/main/"
    "avbtool.py?format=TEXT"
)


def _managed_avb(workspace: Path, payload: bytes = b"managed avbtool") -> Path:
    root = workspace / "tools" / "downloads" / "avbtool"
    root.mkdir(parents=True, exist_ok=True)
    executable = root / "avbtool"
    executable.write_bytes(payload)
    if os.name != "nt":
        executable.chmod(0o700)
    (root / "managed-tool.romverse").write_text(
        json.dumps(
            {
                "format": "romverse.managed-tool",
                "schema_version": 1,
                "name": "AVBTool",
                "source": AVB_SOURCE,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "executable": "avbtool",
            }
        ),
        encoding="utf-8",
    )
    return executable


def _manifest(workspace: Path, executable: Path):
    return ToolchainEvidenceService(workspace, "Linux").capture(
        (ToolStatus("AVBTool", True, str(executable), "1.3.0", "Ready"),),
        required_tools=("AVBTool",),
        scope="local-build:test-project",
    )


def test_managed_tool_is_copied_to_immutable_content_addressed_slot(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    executable = _managed_avb(workspace)
    manifest = _manifest(workspace, executable)
    store = VersionedToolchainStore(workspace)

    first = store.isolate({"AVBTool": executable}, manifest)
    second = store.isolate({"AVBTool": executable}, manifest)

    isolated = first["AVBTool"]
    assert second == first
    assert isolated != executable
    assert isolated.read_bytes() == executable.read_bytes()
    assert manifest.tools[0].sha256 in isolated.parts
    assert isolated.is_relative_to(workspace / "tools" / "versioned")
    receipt = isolated.parent / store.RECEIPT_NAME
    assert receipt.is_file()
    if os.name != "nt":
        assert stat.S_IMODE(isolated.stat().st_mode) == 0o500
        assert stat.S_IMODE(receipt.stat().st_mode) == 0o600


def test_preserved_slot_survives_a_later_managed_tool_update(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    executable = _managed_avb(workspace, b"version one")
    old_manifest = _manifest(workspace, executable)
    store = VersionedToolchainStore(workspace)
    old_isolated = store.isolate({"AVBTool": executable}, old_manifest)["AVBTool"]

    executable = _managed_avb(workspace, b"version two")
    new_manifest = _manifest(workspace, executable)
    new_isolated = store.isolate({"AVBTool": executable}, new_manifest)["AVBTool"]
    recovered_old = store.isolate({"AVBTool": executable}, old_manifest)["AVBTool"]

    assert old_isolated.read_bytes() == b"version one"
    assert new_isolated.read_bytes() == b"version two"
    assert new_isolated != old_isolated
    assert recovered_old == old_isolated


def test_versioned_tool_tampering_fails_closed_without_replacing_slot(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    executable = _managed_avb(workspace)
    manifest = _manifest(workspace, executable)
    store = VersionedToolchainStore(workspace)
    isolated = store.isolate({"AVBTool": executable}, manifest)["AVBTool"]
    if os.name != "nt":
        isolated.chmod(0o700)
    isolated.write_bytes(b"tampered version slot")

    with pytest.raises(VersionedToolchainError, match="no longer matches"):
        store.isolate({"AVBTool": executable}, manifest)

    assert isolated.read_bytes() == b"tampered version slot"


def test_unreceipted_managed_tool_cannot_be_promoted_to_versioned_build_slot(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    executable = workspace / "tools" / "downloads" / "unknown" / "avbtool"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"unreceipted")
    manifest = _manifest(workspace, executable)

    with pytest.raises(VersionedToolchainError, match="validated source receipt"):
        VersionedToolchainStore(workspace).isolate({"AVBTool": executable}, manifest)

    assert not (workspace / "tools" / "versioned").exists()


def test_versioned_tool_store_rejects_linked_workspace_and_redirected_slot(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    linked_workspace = tmp_path / "linked-workspace"
    linked_workspace.symlink_to(workspace, target_is_directory=True)
    with pytest.raises(VersionedToolchainError, match="boundary is unsafe"):
        VersionedToolchainStore(linked_workspace)

    executable = _managed_avb(workspace)
    manifest = _manifest(workspace, executable)
    store = VersionedToolchainStore(workspace)
    item = manifest.tools[0]
    slot = store._slot(item)
    slot.parent.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    slot.symlink_to(outside, target_is_directory=True)

    with pytest.raises(VersionedToolchainError, match="slot is unsafe"):
        store.isolate({"AVBTool": executable}, manifest)

    assert not tuple(outside.iterdir())


def test_versioned_tool_store_rejects_redirected_version_root(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    executable = _managed_avb(workspace)
    manifest = _manifest(workspace, executable)
    outside = tmp_path / "outside"
    outside.mkdir()
    version_root = workspace / "tools" / "versioned"
    version_root.symlink_to(outside, target_is_directory=True)

    with pytest.raises(VersionedToolchainError, match="could not be isolated"):
        VersionedToolchainStore(workspace).isolate({"AVBTool": executable}, manifest)

    assert not tuple(outside.iterdir())
