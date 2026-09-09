from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from romverse.infrastructure.toolchain_evidence import (
    ToolchainEvidenceError,
    ToolchainEvidenceService,
)
from romverse.infrastructure.tools import ToolStatus


def _service(workspace: Path, *, path_value: str = "") -> ToolchainEvidenceService:
    return ToolchainEvidenceService(
        workspace,
        "Linux",
        "fedora",
        clock=lambda: 1_800_000_000.0,
        path_value=path_value,
    )


def test_manifest_hashes_exact_tools_without_exporting_host_paths(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tools = tmp_path / "host-tools"
    tools.mkdir()
    adb = tools / "adb"
    adb.write_bytes(b"verified adb executable")
    service = _service(workspace, path_value=str(tools))

    manifest = service.capture(
        (
            ToolStatus(
                "ADB",
                True,
                str(adb),
                f"1.0.41 from {tools}",
                f"Ready at {adb}",
            ),
            ToolStatus("Fastboot", False, detail="Not installed"),
        ),
        required_tools=("ADB",),
        scope="device-pack:popsicle",
    )
    mapping = manifest.to_mapping()
    encoded = json.dumps(mapping)

    assert manifest.complete
    assert manifest.conflict_count == 0
    assert manifest.execution_authority == "none"
    assert not manifest.phone_changed
    assert manifest.tools[0].sha256 == hashlib.sha256(adb.read_bytes()).hexdigest()
    assert manifest.tools[0].integrity_scope == "observed-executable-sha256"
    assert "local-path-omitted" in manifest.tools[0].version
    assert "local-path-omitted" in manifest.tools[0].detail
    assert manifest.tools[1].state == "missing"
    assert str(tmp_path) not in encoded
    assert str(adb) not in encoded


def test_manifest_reports_distinct_path_conflicts_without_exposing_candidates(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "fastboot").write_bytes(b"selected")
    (second / "fastboot").write_bytes(b"shadowing conflict")
    service = _service(workspace, path_value=os.pathsep.join((str(first), str(second))))

    manifest = service.capture(
        (ToolStatus("Fastboot", True, str(first / "fastboot"), "35.0.2", "Ready"),),
    )

    assert manifest.conflict_count == 1
    assert manifest.tools[0].path_candidate_count == 2
    assert manifest.tools[0].path_conflict
    assert str(second) not in json.dumps(manifest.to_mapping())


def test_managed_receipt_binds_official_source_and_executable(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    root = workspace / "tools" / "downloads" / "payload"
    root.mkdir(parents=True)
    executable = root / "payload-dumper-go"
    executable.write_bytes(b"pinned payload dumper")
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    (root / "managed-tool.romverse").write_text(
        json.dumps(
            {
                "format": "romverse.managed-tool",
                "schema_version": 1,
                "name": "Payload Dumper",
                "version": "2.0.2",
                "source": "https://github.com/ssut/payload-dumper-go/releases/download/v2.0.2/tool",
                "sha256": digest,
                "executable": executable.name,
            }
        )
    )
    service = _service(workspace, path_value=str(root))

    manifest = service.capture(
        (ToolStatus("Payload Dumper", True, str(executable), "2.0.2", "Ready"),),
    )

    evidence = manifest.tools[0]
    assert evidence.origin == "romverse-managed"
    assert evidence.integrity_scope == "managed-source-and-executable"
    assert evidence.source.startswith("https://github.com/ssut/")


def test_managed_receipt_does_not_trust_an_arbitrary_https_source(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    root = workspace / "tools" / "downloads" / "unknown"
    root.mkdir(parents=True)
    executable = root / "adb"
    executable.write_bytes(b"untrusted local executable")
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    (root / "managed-tool.romverse").write_text(
        json.dumps(
            {
                "format": "romverse.managed-tool",
                "schema_version": 1,
                "name": "ADB",
                "source": "https://untrusted.example/download/adb",
                "sha256": digest,
                "executable": executable.name,
            }
        )
    )
    service = _service(workspace, path_value=str(root))

    manifest = service.capture(
        (ToolStatus("ADB", True, str(executable), "1.0.41", "Ready"),),
    )

    evidence = manifest.tools[0]
    assert evidence.origin == "romverse-managed"
    assert evidence.integrity_scope == "observed-executable-sha256"
    assert evidence.source == "ROMVERSE managed receipt unavailable"


def test_managed_platform_tools_package_binds_nested_executable_to_receipt(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    package = workspace / "tools" / "downloads" / "platform-tools"
    binaries = package / "platform-tools"
    binaries.mkdir(parents=True)
    adb = binaries / "adb"
    fastboot = binaries / "fastboot"
    adb.write_bytes(b"managed adb")
    fastboot.write_bytes(b"managed fastboot")
    files = {
        "platform-tools/adb": hashlib.sha256(adb.read_bytes()).hexdigest(),
        "platform-tools/fastboot": hashlib.sha256(fastboot.read_bytes()).hexdigest(),
    }
    (package / "managed-package.romverse").write_text(
        json.dumps(
            {
                "format": "romverse.managed-package",
                "schema_version": 1,
                "name": "platform-tools",
                "source": (
                    "https://dl.google.com/android/repository/platform-tools-latest-linux.zip"
                ),
                "archive_sha256": "a" * 64,
                "archive_bytes": 1_024,
                "files": files,
            }
        )
    )
    service = _service(workspace, path_value=str(binaries))

    manifest = service.capture(
        (ToolStatus("ADB", True, str(adb), "1.0.41", "Ready"),),
    )

    evidence = manifest.tools[0]
    assert evidence.origin == "romverse-managed"
    assert evidence.integrity_scope == "managed-source-and-executable"
    assert evidence.source.endswith("platform-tools-latest-linux.zip")


def test_private_manifest_round_trip_rejects_tampering_and_type_confusion(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    executable = tmp_path / "avbtool"
    executable.write_bytes(b"avbtool")
    service = _service(workspace)
    manifest = service.capture(
        (ToolStatus("AVBTool", True, str(executable), "1.3.0", "Ready"),),
    )
    path = service.save_private(manifest)

    assert service.load_private(manifest.manifest_digest) == manifest
    assert path.stat().st_mode & 0o077 == 0

    payload = json.loads(path.read_text())
    payload["execution_authority"] = "flash"
    unsigned = dict(payload)
    unsigned.pop("format")
    unsigned.pop("manifest_digest")
    payload["manifest_digest"] = service._digest(unsigned)
    path.write_text(json.dumps(payload))
    with pytest.raises(ToolchainEvidenceError, match="safety contract"):
        service.load_private(manifest.manifest_digest)

    payload["execution_authority"] = "none"
    payload["schema_version"] = True
    unsigned = dict(payload)
    unsigned.pop("format")
    unsigned.pop("manifest_digest")
    payload["manifest_digest"] = service._digest(unsigned)
    path.write_text(json.dumps(payload))
    with pytest.raises(ToolchainEvidenceError, match="expected an integer"):
        service.load_private(manifest.manifest_digest)


def test_export_requires_a_safe_user_selected_json_destination(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    executable = tmp_path / "java"
    executable.write_bytes(b"java runtime")
    service = _service(workspace)
    manifest = service.capture(
        (ToolStatus("Java", True, str(executable), "21", "Ready"),),
    )
    destination = tmp_path / "exports"
    destination.mkdir()

    exported = service.export(manifest, destination / "forge-toolchain.json")

    assert json.loads(exported.read_text()) == json.loads(json.dumps(manifest.to_mapping()))
    assert service.root.exists() is False
    with pytest.raises(ToolchainEvidenceError, match="JSON destination"):
        service.export(manifest, destination / "forge-toolchain.txt")

    target = tmp_path / "linked-target"
    target.mkdir()
    linked = tmp_path / "linked-exports"
    linked.symlink_to(target, target_is_directory=True)
    with pytest.raises(ToolchainEvidenceError, match="destination is unsafe"):
        service.export(manifest, linked / "manifest.json")


def test_symlinked_workspace_and_unbounded_path_fail_closed(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(workspace, target_is_directory=True)
    with pytest.raises(ToolchainEvidenceError, match="boundary is unsafe"):
        _service(linked)

    executable = tmp_path / "adb"
    executable.write_bytes(b"adb")
    service = _service(workspace, path_value=os.pathsep.join([str(tmp_path)] * 257))
    with pytest.raises(ToolchainEvidenceError, match="too many entries"):
        service.capture((ToolStatus("ADB", True, str(executable), "1", "Ready"),))
