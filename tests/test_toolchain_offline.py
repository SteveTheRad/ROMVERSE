from __future__ import annotations

import hashlib
import json
import os
import stat
import zipfile
from pathlib import Path

import pytest

from romverse.infrastructure.local_store import LocalStoreError
from romverse.infrastructure.toolchain_offline import (
    OfflineToolchainBundleService,
    OfflineToolchainError,
)
from romverse.ui.toolchain_center import verified_managed_directories


def _platform_tools(workspace: Path, payload: bytes = b"source tool") -> Path:
    package = workspace / "tools" / "downloads" / "platform-tools"
    binaries = package / "platform-tools"
    binaries.mkdir(parents=True)
    adb = binaries / "adb"
    fastboot = binaries / "fastboot"
    adb.write_bytes(payload + b" adb")
    fastboot.write_bytes(payload + b" fastboot")
    if os.name != "nt":
        adb.chmod(0o700)
        fastboot.chmod(0o700)
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
                "archive_bytes": 2_048,
                "files": files,
            }
        ),
        encoding="utf-8",
    )
    return package


def _validated(root: Path, packages: tuple[str, ...]) -> bool:
    verified = verified_managed_directories(root, boundary=root)
    try:
        found = {path.resolve().relative_to(root.resolve()).parts[0] for path in verified}
    except (OSError, ValueError, IndexError):
        return False
    return found == set(packages)


def _bundle(source: Path, destination: Path):
    package = _platform_tools(source)
    service = OfflineToolchainBundleService(source, clock=lambda: 1_800_000_000.0)
    progress = []
    inspection = service.create(
        (package,),
        destination,
        validate_packages=_validated,
        progress=lambda done, total: progress.append((done, total)),
    )
    return service, inspection, progress


def test_signed_offline_toolchain_round_trip_is_hash_bound_and_private(tmp_path: Path) -> None:
    source = tmp_path / "source-workspace"
    target = tmp_path / "target-workspace"
    exports = tmp_path / "exports"
    source.mkdir()
    target.mkdir()
    exports.mkdir()
    bundle = exports / "ROMVERSE-Tools.rvtools"
    source_service, inspection, export_progress = _bundle(source, bundle)

    assert source_service.inspect(bundle) == inspection
    assert inspection.packages == ("platform-tools",)
    assert inspection.signer_fingerprint == source_service.signer_fingerprint()
    assert inspection.execution_authority == "none"
    assert not inspection.phone_changed
    assert export_progress[-1][0] == export_progress[-1][1]
    assert stat.S_IMODE(bundle.stat().st_mode) == 0o600
    identity = source / "config" / "toolchain" / "offline-identity"
    key = identity / "offline-transfer-ed25519.key"
    assert stat.S_IMODE(key.stat().st_mode) == 0o600

    target_service = OfflineToolchainBundleService(
        target,
        clock=lambda: 1_800_000_001.0,
    )
    import_progress = []
    receipt = target_service.import_bundle(
        bundle,
        accepted_bundle_sha256=inspection.bundle_sha256,
        accepted_signer_fingerprint=inspection.signer_fingerprint,
        validate_staging=_validated,
        progress=lambda done, total: import_progress.append((done, total)),
    )

    installed = target / "tools" / "downloads" / "platform-tools" / "platform-tools"
    assert (installed / "adb").read_bytes() == b"source tool adb"
    assert (installed / "fastboot").read_bytes() == b"source tool fastboot"
    if os.name != "nt":
        assert stat.S_IMODE((installed / "adb").stat().st_mode) == 0o700
    assert receipt.bundle_sha256 == inspection.bundle_sha256
    assert receipt.source_receipts_validated
    assert receipt.execution_authority == "none"
    assert not receipt.phone_changed
    assert import_progress[-1][0] == import_progress[-1][1]
    receipt_path = (
        target
        / "config"
        / "toolchain"
        / "offline-imports"
        / f"{receipt.receipt_digest}.romverse-offline-import.json"
    )
    assert stat.S_IMODE(receipt_path.stat().st_mode) == 0o600
    assert _validated(target / "tools" / "downloads", ("platform-tools",))


def test_offline_toolchain_rejects_manifest_tampering(tmp_path: Path) -> None:
    source = tmp_path / "workspace"
    exports = tmp_path / "exports"
    source.mkdir()
    exports.mkdir()
    bundle = exports / "tools.rvtools"
    service, _inspection, _progress = _bundle(source, bundle)
    tampered = exports / "tampered.rvtools"
    with zipfile.ZipFile(bundle) as archive:
        members = [(info, archive.read(info)) for info in archive.infolist()]
    manifest = json.loads(members[0][1])
    manifest["safety"]["phone_changed"] = True
    with zipfile.ZipFile(tampered, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(members[0][0].filename, json.dumps(manifest).encode())
        for info, payload in members[1:]:
            archive.writestr(info.filename, payload)

    with pytest.raises(OfflineToolchainError, match="manifest contract"):
        service.inspect(tampered)


def test_offline_toolchain_requires_the_exact_confirmed_identity(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    exports = tmp_path / "exports"
    source.mkdir()
    target.mkdir()
    exports.mkdir()
    bundle = exports / "tools.rvtools"
    _service, inspection, _progress = _bundle(source, bundle)
    target_service = OfflineToolchainBundleService(target)

    with pytest.raises(OfflineToolchainError, match="accepted offline kit identity"):
        target_service.import_bundle(
            bundle,
            accepted_bundle_sha256="0" * 64,
            accepted_signer_fingerprint=inspection.signer_fingerprint,
            validate_staging=_validated,
        )

    assert not (target / "tools" / "downloads").exists()


def test_offline_toolchain_validation_failure_preserves_existing_package(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    exports = tmp_path / "exports"
    source.mkdir()
    target.mkdir()
    exports.mkdir()
    bundle = exports / "tools.rvtools"
    _service, inspection, _progress = _bundle(source, bundle)
    existing = _platform_tools(target, b"existing target")
    old_adb = existing / "platform-tools" / "adb"
    before = old_adb.read_bytes()
    target_service = OfflineToolchainBundleService(target)

    with pytest.raises(OfflineToolchainError, match="source receipts"):
        target_service.import_bundle(
            bundle,
            accepted_bundle_sha256=inspection.bundle_sha256,
            accepted_signer_fingerprint=inspection.signer_fingerprint,
            validate_staging=lambda _root, _packages: False,
        )

    assert old_adb.read_bytes() == before


def test_offline_toolchain_receipt_failure_rolls_back_installed_packages(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    exports = tmp_path / "exports"
    source.mkdir()
    target.mkdir()
    exports.mkdir()
    bundle = exports / "tools.rvtools"
    _service, inspection, _progress = _bundle(source, bundle)
    existing = _platform_tools(target, b"existing target")
    old_adb = existing / "platform-tools" / "adb"
    before = old_adb.read_bytes()
    target_service = OfflineToolchainBundleService(target)
    monkeypatch.setattr(
        target_service,
        "_save_import_receipt",
        lambda _receipt: (_ for _ in ()).throw(LocalStoreError("disk failure")),
    )

    with pytest.raises(OfflineToolchainError, match="Offline package transaction failed"):
        target_service.import_bundle(
            bundle,
            accepted_bundle_sha256=inspection.bundle_sha256,
            accepted_signer_fingerprint=inspection.signer_fingerprint,
            validate_staging=_validated,
        )

    assert old_adb.read_bytes() == before
    assert _validated(target / "tools" / "downloads", ("platform-tools",))


def test_offline_toolchain_rejects_linked_package_and_bundle_paths(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    exports = tmp_path / "exports"
    workspace.mkdir()
    exports.mkdir()
    package = _platform_tools(workspace)
    outside = tmp_path / "outside"
    outside.mkdir()
    linked_package = workspace / "tools" / "downloads" / "linked-package"
    linked_package.symlink_to(outside, target_is_directory=True)
    service = OfflineToolchainBundleService(workspace)

    with pytest.raises(OfflineToolchainError, match="exact boundary"):
        service.create(
            (linked_package,),
            exports / "linked.rvtools",
            validate_packages=lambda _root, _packages: True,
        )

    bundle = exports / "valid.rvtools"
    service.create((package,), bundle, validate_packages=_validated)
    linked_bundle = exports / "linked.rvtools"
    linked_bundle.symlink_to(bundle)
    with pytest.raises(OfflineToolchainError, match="unsafe or too large"):
        service.inspect(linked_bundle)
