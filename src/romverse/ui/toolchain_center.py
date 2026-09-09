from __future__ import annotations

import base64
import binascii
import hashlib
import os
import re
import shutil
import stat
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from romverse.device.models import AndroidDevice, DeviceState
from romverse.infrastructure.android_apk_tools import (
    AAPT2_ARCHIVE_SHA256,
    AAPT2_PACKAGE_DIRECTORY,
    AAPT2_SOURCE,
    AAPT2_VERSION,
    APK_VERIFIER_LAUNCHER_FILE,
    APK_VERIFIER_PACKAGE_DIRECTORY,
    APK_VERIFIER_SOURCE_FILE,
    APKSIG_ARCHIVE_SHA256,
    APKSIG_JAR,
    APKSIG_SOURCE,
    APKSIG_VERSION,
    MAX_GOOGLE_MAVEN_ARTIFACT_BYTES,
    install_pinned_aapt2,
    install_pinned_apk_verifier,
)
from romverse.infrastructure.host_toolchain_health import (
    HostToolchainHealth,
    ToolHealthState,
    assess_host_toolchain,
)
from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    ensure_private_directory,
    read_json_object,
)
from romverse.infrastructure.payload_dumper import (
    install_payload_dumper_release,
    resolve_latest_payload_dumper,
)
from romverse.infrastructure.process import CommandRunner, SubprocessRunner
from romverse.infrastructure.provisioning import (
    ROM_STUDIO_DEFAULT_REQUIRED_TOOLS,
    ROM_STUDIO_TOOL_CATALOG,
    ProvisionStrategy,
    ToolProvisionItem,
    create_provision_plan,
    install_system_packages,
    source_for,
)
from romverse.infrastructure.toolchain_evidence import (
    ToolchainEvidenceError,
    ToolchainEvidenceManifest,
    ToolchainEvidenceService,
)
from romverse.infrastructure.toolchain_offline import (
    OfflineToolchainBundleService,
    OfflineToolchainError,
    OfflineToolchainImportReceipt,
    OfflineToolchainInspection,
)
from romverse.infrastructure.tools import ToolStatus, ToolVerifier
from romverse.intelligence.action_evidence import (
    ToolchainVerificationStore,
    TypedLocalActionEvidence,
)
from romverse.intelligence.online_remediation import (
    OnlineFixReceipt,
    OnlineRemediationService,
    SourceAuthority,
)
from romverse.platform.host import HostPlatform
from romverse.ui.background import (
    CoalescedProgress,
    ManagedRunnable,
    measured_percent,
    start_background,
)
from romverse.ui.process_progress import ProcessProgressBar

AVBTOOL_SOURCE = "https://android.googlesource.com/platform/external/avb/+/refs/heads/main/avbtool.py?format=TEXT"
MAX_MANAGED_SCRIPT_BYTES = 4 * 1024 * 1024
MAX_MANAGED_ARCHIVE_BYTES = 250 * 1024 * 1024
MAX_MANAGED_EXPANDED_BYTES = 1024 * 1024 * 1024
MAX_MANAGED_ARCHIVE_ENTRIES = 10_000
MAX_PARTITION_TOOL_BYTES = 64 * 1024 * 1024
MAX_MANAGED_RECEIPT_BYTES = 64 * 1024
MAX_MANAGED_PACKAGE_FILES = 64
MAX_MANAGED_PACKAGE_DIRECTORIES = 32
PARTITION_TOOLS_COMMIT = "5e92a5d504de33414318ced8bad5507440bb8c30"
PARTITION_TOOL_HASHES = {
    "linux": {
        "lpmake": "49a41a330e3fee77fa907ad5a7518b631d623c8de8d52cc1aa3736ba96de42b3",
        "lpunpack": "1ea4d7f9da8b9d87a25688639439f4ad6b7582d01e1dffe5617f2be70ceef41b",
        "lpdumps": "3032e45e3e48f90f0fde67a4aa3fc9f1776615ff45ee5ac1c8d4c5c238c303e9",
        "simg2img": "a2228d4927f57256ec47692d4e46e0fd3b2d50d7d1513ac502bf95c458dd8235",
    },
    "windows": {
        "lpmake.exe": "602d59d2670f6dccfef81d854444aafe2cac7995d07e22158271bef65accaf3d",
        "lpunpack.exe": "dc53c92ee00ba5774fa5cc38d98afa979ebc711d398e97de445d941b0b3dc58d",
        "lpdumps.exe": "1dc8385534cd9a849750e42be04ce0af2af1ce0c89074e8b88947cbd36035d23",
        "simg2img.exe": "5d840c8352d3790712b68077ab5e224d190737dd6add80541e6a871b6b205546",
    },
}
DownloadProgress = Callable[[int, int], None]


def install_official_avbtool(
    destination: Path,
    opener=None,
    *,
    boundary: Path | None = None,
    progress: DownloadProgress | None = None,
) -> tuple[Path, str]:
    """Install the official standalone AOSP script into the managed tools directory."""

    open_url = opener or urllib.request.urlopen
    with open_url(AVBTOOL_SOURCE, timeout=90) as response:
        expected_bytes = _response_content_length(response, MAX_MANAGED_SCRIPT_BYTES * 2)
        encoded = response.read(MAX_MANAGED_SCRIPT_BYTES * 2 + 1)
    if progress is not None:
        progress(len(encoded), expected_bytes)
        progress(0, 0)
    if len(encoded) > MAX_MANAGED_SCRIPT_BYTES * 2:
        raise ValueError("AVBTool download exceeds the managed script limit")
    try:
        source = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Official AVBTool response was not valid source data") from exc
    if (
        len(source) > MAX_MANAGED_SCRIPT_BYTES
        or not source.startswith(b"#!/usr/bin/env python3")
        or b"class AvbTool" not in source
    ):
        raise ValueError("Official AVBTool source failed structural validation")
    boundary = _prepare_managed_destination(destination, boundary)
    root = ensure_private_directory(destination / "avbtool", boundary=boundary)
    executable = root / "avbtool"
    descriptor, temporary_name = tempfile.mkstemp(prefix=".avbtool.", suffix=".part", dir=root)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(source)
            stream.flush()
            os.fsync(stream.fileno())
        # Windows has no file-descriptor chmod.  The path form is portable and
        # is applied only after the complete payload has been synced.
        temporary.chmod(0o700)
        os.replace(temporary, executable)
    finally:
        temporary.unlink(missing_ok=True)
    digest = hashlib.sha256(source).hexdigest()
    atomic_write_json(
        root / "managed-tool.romverse",
        {
            "format": "romverse.managed-tool",
            "schema_version": 1,
            "name": "AVBTool",
            "source": AVBTOOL_SOURCE,
            "sha256": digest,
            "executable": "avbtool",
        },
        boundary=boundary,
        maximum_bytes=MAX_MANAGED_RECEIPT_BYTES,
    )
    return executable, digest


def install_official_archive(
    name: str,
    source: str,
    destination: Path,
    required_files: tuple[str, ...],
    opener=None,
    *,
    boundary: Path | None = None,
    progress: DownloadProgress | None = None,
) -> tuple[Path, str]:
    """Download, bound, validate, atomically extract, and receipt an official ZIP."""

    open_url = opener or urllib.request.urlopen
    boundary = _prepare_managed_destination(destination, boundary)
    partial_descriptor, partial_name = tempfile.mkstemp(
        prefix=f".{name}.", suffix=".zip.part", dir=destination
    )
    partial = Path(partial_name)
    digest = hashlib.sha256()
    total = 0
    try:
        with (
            os.fdopen(partial_descriptor, "wb", closefd=True) as stream,
            open_url(source, timeout=90) as response,
        ):
            expected_bytes = _response_content_length(response, MAX_MANAGED_ARCHIVE_BYTES)
            if progress is not None:
                progress(0, expected_bytes)
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_MANAGED_ARCHIVE_BYTES:
                    raise ValueError("official package exceeds the managed archive limit")
                digest.update(chunk)
                stream.write(chunk)
                if progress is not None:
                    progress(total, expected_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        if progress is not None:
            progress(0, 0)
        with zipfile.ZipFile(partial) as package:
            members = package.infolist()
            if len(members) > MAX_MANAGED_ARCHIVE_ENTRIES:
                raise ValueError("official package contains too many entries")
            if sum(member.file_size for member in members) > MAX_MANAGED_EXPANDED_BYTES:
                raise ValueError("official package exceeds the expanded-size limit")
            staging = destination / f".{name}.extracting"
            with suppress(OSError):
                shutil.rmtree(staging)
            ensure_private_directory(staging, boundary=boundary)
            root = staging.resolve()
            for member in members:
                target = (staging / member.filename).resolve()
                if root != target and root not in target.parents:
                    raise ValueError("archive contains an unsafe path")
                unix_mode = (member.external_attr >> 16) & 0xF000
                if unix_mode == 0xA000:
                    raise ValueError("archive contains an unsupported symbolic link")
            bad_member = package.testzip()
            if bad_member is not None:
                raise ValueError(f"official package failed CRC validation: {bad_member}")
            package.extractall(staging)
        matched: dict[str, str] = {}
        for required in required_files:
            candidates = [path for path in staging.rglob(required) if path.is_file()]
            if len(candidates) != 1:
                raise ValueError(f"official package must contain one required file: {required}")
            candidate = candidates[0]
            matched[str(candidate.relative_to(staging))] = _file_sha256(candidate)
            if required in {"adb", "fastboot"} and os.name != "nt":
                candidate.chmod(0o700)
        receipt = {
            "format": "romverse.managed-package",
            "schema_version": 1,
            "name": name,
            "source": source,
            "archive_sha256": digest.hexdigest(),
            "archive_bytes": total,
            "files": matched,
        }
        atomic_write_json(
            staging / "managed-package.romverse",
            receipt,
            boundary=boundary,
            maximum_bytes=MAX_MANAGED_RECEIPT_BYTES,
        )
        target = destination / name
        previous = destination / f".{name}.previous"
        with suppress(OSError):
            shutil.rmtree(previous)
        if target.exists():
            os.replace(target, previous)
        try:
            os.replace(staging, target)
        except OSError:
            if previous.exists() and not target.exists():
                os.replace(previous, target)
            raise
        with suppress(OSError):
            shutil.rmtree(previous)
        return target, digest.hexdigest()
    finally:
        partial.unlink(missing_ok=True)
        staging = destination / f".{name}.extracting"
        with suppress(OSError):
            shutil.rmtree(staging)


def install_pinned_partition_tools(
    host_name: str,
    destination: Path,
    opener=None,
    *,
    commit: str = PARTITION_TOOLS_COMMIT,
    expected_files: dict[str, str] | None = None,
    boundary: Path | None = None,
    progress: DownloadProgress | None = None,
) -> tuple[Path, dict[str, str]]:
    """Install the exact hash-pinned AOSP 15 reference binaries used by ROMVERSE testing."""

    platform_name = "windows" if host_name.casefold() == "windows" else "linux"
    folder = "windows_x86" if platform_name == "windows" else "linux_glibc_x86_64"
    expected = expected_files or PARTITION_TOOL_HASHES[platform_name]
    if not expected or any("/" in name or "\\" in name for name in expected):
        raise ValueError("partition tool manifest contains an unsafe filename")
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
        raise ValueError("partition tool source must be pinned to a full commit")
    open_url = opener or urllib.request.urlopen
    boundary = _prepare_managed_destination(destination, boundary)
    staging = destination / ".aosp-partition-tools.extracting"
    target = destination / "aosp-partition-tools"
    previous = destination / ".aosp-partition-tools.previous"
    with suppress(OSError):
        shutil.rmtree(staging)
    ensure_private_directory(staging, boundary=boundary)
    hashes: dict[str, str] = {}
    try:
        ordered = tuple(sorted(expected.items()))
        if progress is not None:
            progress(0, len(ordered))
        for index, (filename, expected_digest) in enumerate(ordered, start=1):
            url = (
                "https://raw.githubusercontent.com/Rprop/aosp15_partition_tools/"
                f"{commit}/{folder}/{filename}"
            )
            digest = hashlib.sha256()
            total = 0
            path = staging / filename
            with open_url(url, timeout=90) as response, path.open("wb") as stream:
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_PARTITION_TOOL_BYTES:
                        raise ValueError(f"{filename} exceeds the managed binary limit")
                    digest.update(chunk)
                    stream.write(chunk)
                stream.flush()
                os.fsync(stream.fileno())
            actual = digest.hexdigest()
            if actual != expected_digest:
                raise ValueError(f"{filename} does not match ROMVERSE's pinned SHA-256")
            if os.name != "nt":
                path.chmod(0o700)
            hashes[filename] = actual
            if progress is not None:
                progress(index, len(ordered))
        atomic_write_json(
            staging / "managed-package.romverse",
            {
                "format": "romverse.managed-package",
                "schema_version": 1,
                "name": "AOSP Partition Tools",
                "source": "https://github.com/Rprop/aosp15_partition_tools",
                "commit": commit,
                "provenance": "reference binaries built from android-15.0.0_r25; third-party publisher; exact hashes pinned",
                "files": hashes,
            },
            boundary=boundary,
            maximum_bytes=MAX_MANAGED_RECEIPT_BYTES,
        )
        with suppress(OSError):
            shutil.rmtree(previous)
        if target.exists():
            os.replace(target, previous)
        try:
            os.replace(staging, target)
        except OSError:
            if previous.exists() and not target.exists():
                os.replace(previous, target)
            raise
        with suppress(OSError):
            shutil.rmtree(previous)
        return target, hashes
    finally:
        with suppress(OSError):
            shutil.rmtree(staging)


def verified_managed_directories(
    root: Path,
    *,
    boundary: Path | None = None,
) -> tuple[Path, ...]:
    """Return only managed executable directories whose receipt hashes still match."""

    directories: set[Path] = set()
    if not _directory_within_boundary_is_unlinked(root, boundary or root.parent):
        return ()
    try:
        details = root.lstat()
    except OSError:
        return ()
    if not stat.S_ISDIR(details.st_mode) or root.is_symlink():
        return ()
    try:
        children = sorted(
            (Path(entry.path) for entry in os.scandir(root) if entry.is_dir(follow_symlinks=False)),
            key=lambda path: path.name,
        )
    except OSError:
        return ()
    if len(children) > MAX_MANAGED_PACKAGE_DIRECTORIES:
        return ()
    for directory in children:
        receipt_path = directory / "managed-tool.romverse"
        try:
            receipt = read_json_object(
                receipt_path,
                boundary=root,
                maximum_bytes=MAX_MANAGED_RECEIPT_BYTES,
            )
            executable = _validate_managed_tool_receipt(directory, receipt)
            directories.add(executable.parent)
        except (LocalStoreError, OSError, KeyError, TypeError, ValueError):
            pass
        receipt_path = directory / "managed-package.romverse"
        try:
            receipt = read_json_object(
                receipt_path,
                boundary=root,
                maximum_bytes=MAX_MANAGED_RECEIPT_BYTES,
            )
            directories.update(_validate_managed_package_receipt(directory, receipt))
        except (LocalStoreError, OSError, KeyError, TypeError, ValueError):
            pass
    return tuple(sorted(directories))


def verified_managed_package_roots(workspace: Path) -> tuple[Path, ...]:
    """Return exact first-level packages accepted by the production receipt verifier."""

    root = workspace / "tools" / "downloads"
    directories = verified_managed_directories(root, boundary=workspace)
    try:
        resolved_root = root.resolve(strict=True)
        names = {
            directory.resolve(strict=True).relative_to(resolved_root).parts[0]
            for directory in directories
        }
        packages = tuple(resolved_root / name for name in sorted(names))
    except (OSError, ValueError, IndexError):
        return ()
    return tuple(
        package
        for package in packages
        if package.is_dir() and not package.is_symlink() and package.parent == resolved_root
    )


def validate_offline_managed_packages(root: Path, packages: tuple[str, ...]) -> bool:
    """Require every declared offline package to pass the normal managed receipt gate."""

    if not packages or len(packages) != len(set(packages)):
        return False
    directories = verified_managed_directories(root, boundary=root)
    try:
        resolved_root = root.resolve(strict=True)
        verified = {
            directory.resolve(strict=True).relative_to(resolved_root).parts[0]
            for directory in directories
        }
    except (OSError, ValueError, IndexError):
        return False
    return verified == set(packages)


def _contained_receipt_file(directory: Path, relative: str) -> Path:
    """Resolve a receipt entry only when it is a real file inside its package."""

    path = Path(relative)
    if not relative or path.is_absolute() or "\\" in relative or ".." in path.parts:
        raise ValueError("managed receipt references a file outside its package")
    root = directory.resolve(strict=True)
    candidate = directory
    for index, part in enumerate(path.parts):
        candidate /= part
        details = candidate.lstat()
        is_junction = bool(getattr(candidate, "is_junction", lambda: False)())
        if candidate.is_symlink() or is_junction:
            raise ValueError("managed receipt references a linked path")
        final = index == len(path.parts) - 1
        if final and not stat.S_ISREG(details.st_mode):
            raise ValueError("managed receipt does not reference a regular file")
        if not final and not stat.S_ISDIR(details.st_mode):
            raise ValueError("managed receipt path is invalid")
    resolved = candidate.resolve(strict=True)
    if root != resolved and root not in resolved.parents:
        raise ValueError("managed receipt references a file outside its package")
    return resolved


def activate_verified_managed_tools(workspace: Path) -> tuple[Path, ...]:
    """Expose hash-verified managed tools without duplicating PATH entries."""

    managed_root = Path(os.path.abspath(workspace / "tools" / "downloads"))
    directories = verified_managed_directories(managed_root, boundary=workspace)
    current = [
        entry
        for entry in os.environ.get("PATH", "").split(os.pathsep)
        if not _path_entry_is_within(entry, managed_root)
    ]
    additions = [str(directory) for directory in directories]
    os.environ["PATH"] = os.pathsep.join((*additions, *current))
    return directories


def _prepare_managed_destination(destination: Path, boundary: Path | None) -> Path:
    trust_boundary = Path(os.path.abspath(boundary or destination.parent))
    if boundary is None:
        while not trust_boundary.exists() and trust_boundary != trust_boundary.parent:
            trust_boundary = trust_boundary.parent
    ensure_private_directory(destination, boundary=trust_boundary)
    return trust_boundary


def _directory_within_boundary_is_unlinked(directory: Path, boundary: Path) -> bool:
    try:
        root = boundary.resolve(strict=True)
        candidate = Path(os.path.abspath(directory))
        relative = candidate.relative_to(root)
        current = root
        for part in relative.parts:
            current /= part
            details = current.lstat()
            is_junction = bool(getattr(current, "is_junction", lambda: False)())
            if not stat.S_ISDIR(details.st_mode) or current.is_symlink() or is_junction:
                return False
    except (OSError, ValueError):
        return False
    return True


def _validate_managed_tool_receipt(directory: Path, receipt: dict[str, object]) -> Path:
    name = receipt.get("name")
    if name == "AVBTool":
        expected_keys = {
            "format",
            "schema_version",
            "name",
            "source",
            "sha256",
            "executable",
        }
        expected_directory = "avbtool"
        expected_executable = "avbtool"
        source_valid = receipt.get("source") == AVBTOOL_SOURCE
    elif name == "Payload Dumper":
        expected_keys = {
            "format",
            "schema_version",
            "name",
            "version",
            "source",
            "source_archive_sha256",
            "sha256",
            "executable",
        }
        expected_directory = "payload-dumper-go"
        expected_executable = "payload-dumper-go.exe" if os.name == "nt" else "payload-dumper-go"
        source = receipt.get("source")
        version = receipt.get("version")
        source_valid = (
            isinstance(source, str)
            and isinstance(version, str)
            and re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z._-]{0,63}", version) is not None
            and _is_official_payload_dumper_source(source, version)
            and _is_sha256(receipt.get("source_archive_sha256"))
        )
    else:
        raise ValueError("managed tool identity is not approved")
    if (
        set(receipt) != expected_keys
        or receipt.get("format") != "romverse.managed-tool"
        or type(receipt.get("schema_version")) is not int
        or receipt.get("schema_version") != 1
        or directory.name != expected_directory
        or receipt.get("executable") != expected_executable
        or not source_valid
        or not _is_sha256(receipt.get("sha256"))
    ):
        raise ValueError("managed tool receipt is invalid")
    executable = _contained_receipt_file(directory, expected_executable)
    if _file_sha256(executable) != receipt["sha256"]:
        raise ValueError("managed tool hash mismatch")
    return executable


def _validate_managed_package_receipt(
    directory: Path,
    receipt: dict[str, object],
) -> tuple[Path, ...]:
    package = directory.name
    if package in {"platform-tools", "google-usb-driver"}:
        expected_keys = {
            "format",
            "schema_version",
            "name",
            "source",
            "archive_sha256",
            "archive_bytes",
            "files",
        }
        expected_name = package
        expected_sources = {
            "platform-tools": {
                "https://dl.google.com/android/repository/platform-tools-latest-linux.zip",
                "https://dl.google.com/android/repository/platform-tools-latest-windows.zip",
            },
            "google-usb-driver": {
                "https://dl.google.com/android/repository/latest_usb_driver_windows.zip"
            },
        }[package]
        archive_bytes = receipt.get("archive_bytes")
        shape_valid = (
            receipt.get("source") in expected_sources
            and _is_sha256(receipt.get("archive_sha256"))
            and type(archive_bytes) is int
            and 0 < archive_bytes <= MAX_MANAGED_ARCHIVE_BYTES
        )
    elif package == "aosp-partition-tools":
        expected_keys = {
            "format",
            "schema_version",
            "name",
            "source",
            "commit",
            "provenance",
            "files",
        }
        expected_name = "AOSP Partition Tools"
        commit = receipt.get("commit")
        shape_valid = (
            receipt.get("source") == "https://github.com/Rprop/aosp15_partition_tools"
            and receipt.get("provenance")
            == "reference binaries built from android-15.0.0_r25; third-party publisher; exact hashes pinned"
            and isinstance(commit, str)
            and re.fullmatch(r"[0-9a-f]{40}", commit) is not None
        )
    elif package == AAPT2_PACKAGE_DIRECTORY:
        expected_keys = {
            "format",
            "schema_version",
            "name",
            "version",
            "source",
            "license",
            "archive_sha256",
            "archive_bytes",
            "files",
        }
        expected_name = "Android AAPT2"
        archive_bytes = receipt.get("archive_bytes")
        shape_valid = (
            receipt.get("version") == AAPT2_VERSION
            and receipt.get("source") == AAPT2_SOURCE
            and receipt.get("license") == "Apache-2.0"
            and receipt.get("archive_sha256") == AAPT2_ARCHIVE_SHA256
            and type(archive_bytes) is int
            and 0 < archive_bytes <= MAX_GOOGLE_MAVEN_ARTIFACT_BYTES
        )
    elif package == APK_VERIFIER_PACKAGE_DIRECTORY:
        expected_keys = {
            "format",
            "schema_version",
            "name",
            "version",
            "source",
            "capability",
            "license",
            "artifact_sha256",
            "artifact_bytes",
            "files",
        }
        expected_name = "Android APK Signature Verifier"
        artifact_bytes = receipt.get("artifact_bytes")
        shape_valid = (
            receipt.get("version") == APKSIG_VERSION
            and receipt.get("source") == APKSIG_SOURCE
            and receipt.get("capability") == "verification-only"
            and receipt.get("license") == "Apache-2.0"
            and receipt.get("artifact_sha256") == APKSIG_ARCHIVE_SHA256
            and type(artifact_bytes) is int
            and 0 < artifact_bytes <= MAX_GOOGLE_MAVEN_ARTIFACT_BYTES
        )
    else:
        raise ValueError("managed package identity is not approved")
    files = receipt.get("files")
    if (
        set(receipt) != expected_keys
        or receipt.get("format") != "romverse.managed-package"
        or type(receipt.get("schema_version")) is not int
        or receipt.get("schema_version") != 1
        or receipt.get("name") != expected_name
        or not shape_valid
        or not isinstance(files, dict)
        or not 0 < len(files) <= MAX_MANAGED_PACKAGE_FILES
    ):
        raise ValueError("managed package receipt is invalid")
    verified: list[Path] = []
    for relative, expected in files.items():
        if not isinstance(relative, str) or not _is_sha256(expected):
            raise ValueError("managed package file manifest is invalid")
        path = _contained_receipt_file(directory, relative)
        if _file_sha256(path) != expected:
            raise ValueError("managed file hash mismatch")
        verified.append(path.parent)
    basenames = {Path(str(relative)).name for relative in files}
    allowed_basenames = {
        "platform-tools": ({"adb", "fastboot"}, {"adb.exe", "fastboot.exe"}),
        "google-usb-driver": ({"android_winusb.inf"},),
        "aosp-partition-tools": (
            {"lpmake", "lpunpack", "lpdumps", "simg2img"},
            {"lpmake.exe", "lpunpack.exe", "lpdumps.exe", "simg2img.exe"},
        ),
        AAPT2_PACKAGE_DIRECTORY: ({"aapt2", "NOTICE", "aapt2.romverse"},),
        APK_VERIFIER_PACKAGE_DIRECTORY: (
            {
                APKSIG_JAR,
                "LICENSE.apksig",
                APK_VERIFIER_SOURCE_FILE,
                APK_VERIFIER_LAUNCHER_FILE,
                "apksigner.romverse",
            },
        ),
    }[package]
    if basenames not in allowed_basenames:
        raise ValueError("managed package file set is invalid")
    return tuple(verified)


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _is_official_payload_dumper_source(source: str, version: str) -> bool:
    parsed = urllib.parse.urlsplit(source)
    expected_prefix = f"/ssut/payload-dumper-go/releases/download/{version}/"
    filename = Path(parsed.path).name
    return (
        parsed.scheme == "https"
        and parsed.hostname == "github.com"
        and parsed.path.startswith(expected_prefix)
        and filename.startswith(f"payload-dumper-go_{version}_")
        and filename.endswith(".tar.gz")
    )


def _path_entry_is_within(entry: str, root: Path) -> bool:
    if not entry:
        return False
    try:
        Path(os.path.abspath(entry)).relative_to(root)
    except ValueError:
        return False
    return True


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _response_content_length(response: object, maximum: int) -> int:
    headers = getattr(response, "headers", None)
    if headers is None:
        return 0
    try:
        value = int(headers.get("Content-Length", "0"))
    except (AttributeError, TypeError, ValueError):
        return 0
    return value if 0 < value <= maximum else 0


@dataclass(frozen=True, slots=True)
class DevicePackToolchainContext:
    """Immutable Device Atlas evidence carried into the read-only Forge inventory."""

    report_digest: str
    pack_id: str
    pack_sha256: str
    pack_name: str
    model: str
    codename: str
    required_tools: tuple[str, ...]
    build_contract_ready: bool
    flash_contract_ready: bool


@dataclass(frozen=True, slots=True)
class StudioProjectToolchainContext:
    """Immutable ROM Studio project/source evidence carried into Forge Arsenal."""

    context_digest: str
    project_id: str
    project_name: str
    source_sha256: str
    device_pack_id: str
    pack_sha256: str
    inspection_digest: str
    required_tools: tuple[str, ...]
    build_contract_bound: bool
    source_kind: str = ""
    source_blueprint_digest: str = ""
    source_plan_digest: str = ""


@dataclass(frozen=True, slots=True)
class RepairToolchainContext:
    """Immutable Smart Solution evidence for a host-only Platform Tools review."""

    action_id: str
    fingerprint_id: str
    receipt_digest: str
    source_id: str
    receipt: OnlineFixReceipt
    required_tools: tuple[str, ...] = ("ADB", "Fastboot")


class _ToolchainManifestSignals(QObject):
    complete = Signal(object)
    failed = Signal(str)


class _ToolchainManifestWorker(ManagedRunnable):
    def __init__(
        self,
        service: ToolchainEvidenceService,
        statuses: tuple[ToolStatus, ...],
        required_tools: tuple[str, ...],
        scope: str,
        destination: Path,
    ) -> None:
        super().__init__()
        self.service = service
        self.statuses = statuses
        self.required_tools = required_tools
        self.scope = scope
        self.destination = destination
        self.signals = _ToolchainManifestSignals()

    @Slot()
    def execute(self) -> None:
        try:
            manifest = self.service.capture(
                self.statuses,
                required_tools=self.required_tools,
                scope=self.scope,
            )
            self.service.save_private(manifest)
            self.service.export(manifest, self.destination)
        except (OSError, ValueError, ToolchainEvidenceError) as exc:
            self.signals.failed.emit(str(exc)[:800])
            return
        self.signals.complete.emit(manifest)


class _OfflineToolchainSignals(QObject):
    complete = Signal(object)
    failed = Signal(str)
    progress = Signal(int)


class _OfflineToolchainWorker(ManagedRunnable):
    def __init__(
        self,
        service: OfflineToolchainBundleService,
        operation: str,
        bundle: Path,
        *,
        package_roots: tuple[Path, ...] = (),
        accepted_bundle_sha256: str = "",
        accepted_signer_fingerprint: str = "",
    ) -> None:
        super().__init__()
        self.service = service
        self.operation = operation
        self.bundle = bundle
        self.package_roots = package_roots
        self.accepted_bundle_sha256 = accepted_bundle_sha256
        self.accepted_signer_fingerprint = accepted_signer_fingerprint
        self.signals = _OfflineToolchainSignals()

    @Slot()
    def execute(self) -> None:
        publish = CoalescedProgress(self.signals.progress.emit)

        def progress(done: int, total: int) -> None:
            percent = measured_percent(done, total)
            if percent is not None:
                publish(percent)

        try:
            if self.operation == "export":
                result = self.service.create(
                    self.package_roots,
                    self.bundle,
                    validate_packages=validate_offline_managed_packages,
                    progress=progress,
                )
            elif self.operation == "inspect":
                result = self.service.inspect(self.bundle)
            elif self.operation == "import":
                result = self.service.import_bundle(
                    self.bundle,
                    accepted_bundle_sha256=self.accepted_bundle_sha256,
                    accepted_signer_fingerprint=self.accepted_signer_fingerprint,
                    validate_staging=validate_offline_managed_packages,
                    progress=progress,
                )
            else:
                raise OfflineToolchainError("The offline toolchain operation is unsupported")
        except (OSError, ValueError, OfflineToolchainError) as exc:
            self.signals.failed.emit(str(exc)[:800])
            return
        self.signals.complete.emit(result)


class ToolchainCenter(QWidget):
    """Inventory and guidance for the local ROM and diagnostics toolchain."""

    statuses_changed = Signal(object)
    device_pack_setup_requested = Signal(str, str, str)
    device_pack_continue_requested = Signal(str, str, str)
    device_atlas_requested = Signal(str, str, str)
    studio_project_setup_requested = Signal(str, str)
    studio_project_continue_requested = Signal(str, str)
    knowledge_article_requested = Signal(str)

    def __init__(
        self,
        host: HostPlatform,
        runner: CommandRunner,
        baseline: tuple[ToolStatus, ...] = (),
        workspace: Path | None = None,
    ) -> None:
        super().__init__()
        self.host = host
        self.runner = runner
        self.workspace = workspace
        self._device_pack_context: DevicePackToolchainContext | None = None
        self._device_pack_context_stale = False
        self._studio_project_context: StudioProjectToolchainContext | None = None
        self._studio_project_context_stale = False
        self._repair_solution_context: RepairToolchainContext | None = None
        self._repair_solution_outcome_saved = False
        self._repair_solution_outcome_error = ""
        self._communication_devices: tuple[AndroidDevice, ...] = ()
        self._observed_communication_devices: tuple[AndroidDevice, ...] = ()
        self._communication_error = ""
        self.host_health: HostToolchainHealth | None = None
        self._manifest_worker: _ToolchainManifestWorker | None = None
        self._manifest_error = ""
        self._offline_worker: _OfflineToolchainWorker | None = None
        self._offline_operation = ""
        self._offline_bundle = Path()
        self.manifest_service: ToolchainEvidenceService | None = None
        self.offline_service: OfflineToolchainBundleService | None = None
        if workspace is not None:
            try:
                self.manifest_service = ToolchainEvidenceService(
                    workspace,
                    host.name,
                    getattr(host, "distribution_id", ""),
                )
                self.offline_service = OfflineToolchainBundleService(workspace)
            except ToolchainEvidenceError as exc:
                self._manifest_error = str(exc)
            except OfflineToolchainError as exc:
                self._manifest_error = str(exc)
        self._activate_managed_tools()
        self.statuses = ToolVerifier(host, runner).verify_extended()
        if baseline:
            known = {status.name for status in self.statuses}
            self.statuses = tuple(self.statuses) + tuple(
                status for status in baseline if status.name not in known
            )
        page = QVBoxLayout(self)
        page.setContentsMargins(30, 26, 30, 30)
        page.setSpacing(14)
        eyebrow = QLabel("FORGE ARSENAL  •  BUILD + DIAGNOSTICS TOOLCHAIN")
        eyebrow.setObjectName("Eyebrow")
        title = QLabel("Forge Arsenal")
        title.setObjectName("Title")
        subtitle = QLabel(
            "Verify and provision tools for extraction, payload handling, ROM builds, signing, and diagnostics. Managed tools are integrity-receipted; approved system packages use the operating system's visible authorization prompt."
        )
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        page.addWidget(eyebrow)
        page.addWidget(title)
        page.addWidget(subtitle)

        self.device_pack_handoff = QFrame()
        self.device_pack_handoff.setObjectName("DiagnosticHandoffBar")
        handoff_layout = QVBoxLayout(self.device_pack_handoff)
        handoff_layout.setContentsMargins(20, 15, 20, 15)
        handoff_layout.setSpacing(10)
        handoff_top = QHBoxLayout()
        handoff_copy = QVBoxLayout()
        self.device_pack_handoff_eyebrow = QLabel("DEVICE ATLAS HANDOFF  •  EXACT BUILD CONTRACT")
        self.device_pack_handoff_eyebrow.setObjectName("Eyebrow")
        self.device_pack_handoff_title = QLabel("No exact Device Pack context")
        self.device_pack_handoff_title.setObjectName("SectionTitle")
        self.device_pack_handoff_detail = QLabel("")
        self.device_pack_handoff_detail.setObjectName("Muted")
        self.device_pack_handoff_detail.setWordWrap(True)
        handoff_copy.addWidget(self.device_pack_handoff_eyebrow)
        handoff_copy.addWidget(self.device_pack_handoff_title)
        handoff_copy.addWidget(self.device_pack_handoff_detail)
        handoff_top.addLayout(handoff_copy, 1)
        self.device_pack_handoff_badge = QLabel("ZERO AUTHORITY")
        self.device_pack_handoff_badge.setObjectName("Warning")
        handoff_top.addWidget(self.device_pack_handoff_badge)
        handoff_layout.addLayout(handoff_top)
        handoff_actions = QHBoxLayout()
        self.context_refresh_button = QPushButton("Re-check exact tools")
        self.context_refresh_button.clicked.connect(self.refresh)
        self.context_setup_button = QPushButton("Set up missing requirements")
        self.context_setup_button.setObjectName("Primary")
        self.context_setup_button.clicked.connect(self._request_device_pack_setup)
        self.context_continue_button = QPushButton("Continue to ROM Studio")
        self.context_continue_button.clicked.connect(self._request_device_pack_continue)
        self.context_guide_button = QPushButton("Open verified guide")
        self.context_guide_button.clicked.connect(self._request_context_guide)
        self.context_return_button = QPushButton("Return to Device Atlas")
        self.context_return_button.clicked.connect(self._request_device_atlas_return)
        handoff_actions.addWidget(self.context_refresh_button)
        handoff_actions.addWidget(self.context_setup_button)
        handoff_actions.addWidget(self.context_continue_button)
        handoff_actions.addWidget(self.context_guide_button)
        handoff_actions.addStretch()
        handoff_actions.addWidget(self.context_return_button)
        handoff_layout.addLayout(handoff_actions)
        self.device_pack_handoff_feedback = QLabel("")
        self.device_pack_handoff_feedback.setObjectName("Muted")
        self.device_pack_handoff_feedback.setWordWrap(True)
        handoff_layout.addWidget(self.device_pack_handoff_feedback)
        self.device_pack_handoff.setVisible(False)
        page.addWidget(self.device_pack_handoff)

        refresh = QPushButton("Re-scan toolchain")
        refresh.setObjectName("Primary")
        refresh.clicked.connect(self.refresh)
        guided = QPushButton("General ROM Studio setup")
        guided.setToolTip(
            "Choose the default ROM Studio requirements when no exact Device Pack context is active."
        )
        guided.clicked.connect(self._guided_setup)
        self.android_sdk_guide_button = QPushButton("AAPT2 and APK tools guide")
        self.android_sdk_guide_button.setToolTip(
            "Open the verified Archives guide for ROMVERSE-managed AAPT2, official apksig "
            "verification, and complete Android SDK Build Tools discovery."
        )
        self.android_sdk_guide_button.clicked.connect(
            lambda: self.knowledge_article_requested.emit("android-sdk-build-tools-not-discovered")
        )
        general_actions = QHBoxLayout()
        general_actions.addWidget(refresh)
        general_actions.addWidget(guided)
        general_actions.addWidget(self.android_sdk_guide_button)
        general_actions.addStretch()
        page.addLayout(general_actions)

        manifest_card = QFrame()
        manifest_card.setObjectName("ToolchainManifestCard")
        manifest_layout = QVBoxLayout(manifest_card)
        manifest_layout.setContentsMargins(18, 15, 18, 15)
        manifest_layout.setSpacing(8)
        manifest_eyebrow = QLabel("ENVIRONMENT PROOF  •  REPRODUCIBLE TOOLCHAIN MANIFEST")
        manifest_eyebrow.setObjectName("Eyebrow")
        manifest_title = QLabel("Fingerprint the exact equipment bay")
        manifest_title.setObjectName("SectionTitle")
        manifest_copy = QLabel(
            "Hash every active executable, record its version and source scope, detect distinct "
            "PATH candidates, and export a path-private manifest. This runs no phone command and "
            "grants no build, install, or flash authority."
        )
        manifest_copy.setObjectName("Muted")
        manifest_copy.setWordWrap(True)
        self.manifest_status = QLabel(
            self._manifest_error
            or "Ready to produce exact local tool evidence. No manifest has been exported yet."
        )
        self.manifest_status.setObjectName(
            "Warning" if self._manifest_error else "ToolchainManifestStatus"
        )
        self.manifest_status.setWordWrap(True)
        self.manifest_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.manifest_button = QPushButton("Export reproducible manifest")
        self.manifest_button.setObjectName("Primary")
        self.manifest_button.setMinimumHeight(38)
        self.manifest_button.setEnabled(self.manifest_service is not None)
        self.manifest_button.clicked.connect(self.export_toolchain_manifest)
        offline_title = QLabel("Signed offline equipment kit")
        offline_title.setObjectName("SectionTitle")
        offline_copy = QLabel(
            "Move only receipt-verified ROMVERSE-managed tools between offline computers. Each kit "
            "is hash-bound and signed by this workspace's local transfer identity; compare the full "
            "signer fingerprint before importing. This is not a ROMVERSE release signature."
        )
        offline_copy.setObjectName("Muted")
        offline_copy.setWordWrap(True)
        self.offline_status = QLabel(
            "No offline kit operation has run. A local transfer identity is created only on export."
        )
        self.offline_status.setObjectName("ToolchainManifestStatus")
        self.offline_status.setWordWrap(True)
        self.offline_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.offline_progress = ProcessProgressBar()
        offline_actions = QHBoxLayout()
        self.offline_export_button = QPushButton("Export verified offline kit")
        self.offline_export_button.setEnabled(
            self.offline_service is not None
            and workspace is not None
            and bool(verified_managed_package_roots(workspace))
        )
        self.offline_export_button.clicked.connect(self.export_offline_toolchain)
        self.offline_import_button = QPushButton("Inspect offline kit")
        self.offline_import_button.setEnabled(self.offline_service is not None)
        self.offline_import_button.clicked.connect(self.inspect_offline_toolchain)
        offline_actions.addWidget(self.offline_export_button)
        offline_actions.addWidget(self.offline_import_button)
        offline_actions.addStretch()
        manifest_layout.addWidget(manifest_eyebrow)
        manifest_layout.addWidget(manifest_title)
        manifest_layout.addWidget(manifest_copy)
        manifest_layout.addWidget(self.manifest_status)
        manifest_layout.addWidget(self.manifest_button, 0, Qt.AlignmentFlag.AlignLeft)
        manifest_layout.addSpacing(5)
        manifest_layout.addWidget(offline_title)
        manifest_layout.addWidget(offline_copy)
        manifest_layout.addWidget(self.offline_status)
        manifest_layout.addWidget(self.offline_progress)
        manifest_layout.addLayout(offline_actions)
        self.body = QScrollArea()
        self.body.setWidgetResizable(True)
        self.content = QWidget()
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 8, 0)
        content_layout.setSpacing(14)
        content_layout.addWidget(manifest_card)
        inventory = QWidget()
        self.layout = QVBoxLayout(inventory)
        self.layout.setContentsMargins(8, 0, 0, 0)
        self.layout.setSpacing(10)
        content_layout.addWidget(inventory)
        self.body.setWidget(self.content)
        page.addWidget(self.body, 1)
        self._render()

    def refresh(self) -> None:
        self._verify_local_tools(emit=True)
        self._record_repair_solution_outcome()

    def set_device_communication_evidence(
        self,
        devices: list[AndroidDevice],
        *,
        observed_devices: list[AndroidDevice] | None = None,
        scan_error: str = "",
    ) -> None:
        """Render the latest Guardian-routed Device Engine communication evidence."""

        if any(not isinstance(device, AndroidDevice) for device in devices):
            return
        observed = list(devices) if observed_devices is None else observed_devices
        if any(not isinstance(device, AndroidDevice) for device in observed):
            return
        self._communication_devices = tuple(devices[:1])
        self._observed_communication_devices = tuple(observed[:16])
        self._communication_error = " ".join(scan_error.split())[:400]
        self._render()

    @Slot()
    def export_toolchain_manifest(self) -> None:
        service = self.manifest_service
        if service is None or self._manifest_worker is not None or self.workspace is None:
            return
        required, scope = self._manifest_scope()
        filename, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export reproducible ROMVERSE toolchain manifest",
            str(self.workspace / "ROMVERSE-Toolchain-Manifest.json"),
            "JSON manifest (*.json)",
        )
        if not filename:
            return
        self.manifest_button.setEnabled(False)
        self._set_manifest_status(
            "Fingerprinting the exact active executables and auditing PATH candidates…",
            "ToolchainManifestStatus",
        )
        worker = _ToolchainManifestWorker(
            service,
            tuple(self.statuses),
            required,
            scope,
            Path(filename),
        )
        self._manifest_worker = worker
        worker.signals.complete.connect(self._manifest_complete)
        worker.signals.failed.connect(self._manifest_failed)
        start_background(worker)

    @Slot(object)
    def _manifest_complete(self, value: object) -> None:
        self._manifest_worker = None
        self.manifest_button.setEnabled(self.manifest_service is not None)
        if not isinstance(value, ToolchainEvidenceManifest):
            self._manifest_failed("ROMVERSE returned an invalid toolchain manifest")
            return
        state = "COMPLETE" if value.complete else "INCOMPLETE"
        conflicts = (
            "no PATH conflicts"
            if value.conflict_count == 0
            else f"{value.conflict_count} PATH conflict(s) recorded"
        )
        self._set_manifest_status(
            f"{state}  •  {len(value.tools)} tool slots  •  {conflicts}  •  "
            f"SHA-256 {value.manifest_digest}\n"
            "Saved privately and exported without absolute host paths. Authority remains none.",
            "Good" if value.complete and value.conflict_count == 0 else "Warning",
        )

    @Slot(str)
    def _manifest_failed(self, message: str) -> None:
        self._manifest_worker = None
        self.manifest_button.setEnabled(self.manifest_service is not None)
        self._set_manifest_status(
            f"Manifest stopped safely: {message}",
            "Danger",
        )

    def _manifest_scope(self) -> tuple[tuple[str, ...], str]:
        context = (
            self._repair_solution_context
            or self._studio_project_context
            or self._device_pack_context
        )
        if context is None:
            return (), "full-inventory"
        if self._repair_solution_context is not None:
            return context.required_tools, "recovery-toolchain"
        if self._studio_project_context is not None:
            return context.required_tools, "rom-studio-project"
        return context.required_tools, "device-pack-build"

    def _set_manifest_status(self, message: str, state: str) -> None:
        self.manifest_status.setText(message)
        self.manifest_status.setObjectName(state)
        self._repolish(self.manifest_status)

    @Slot()
    def export_offline_toolchain(self) -> None:
        service = self.offline_service
        if service is None or self.workspace is None or self._offline_worker is not None:
            return
        packages = verified_managed_package_roots(self.workspace)
        if not packages:
            self._set_offline_status(
                "No receipt-verified ROMVERSE-managed packages are available to export.",
                "Warning",
            )
            return
        filename, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export signed ROMVERSE offline equipment kit",
            str(self.workspace / "ROMVERSE-Offline-Toolchain.rvtools"),
            "ROMVERSE offline toolchain (*.rvtools)",
        )
        if not filename:
            return
        if not filename.casefold().endswith(".rvtools"):
            filename += ".rvtools"
        self._start_offline_worker(
            _OfflineToolchainWorker(
                service,
                "export",
                Path(filename),
                package_roots=packages,
            ),
            "export",
            "Hashing, signing and packaging the verified managed equipment…",
            determinate=True,
        )

    @Slot()
    def inspect_offline_toolchain(self) -> None:
        service = self.offline_service
        if service is None or self.workspace is None or self._offline_worker is not None:
            return
        filename, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Inspect a ROMVERSE offline equipment kit",
            str(self.workspace),
            "ROMVERSE offline toolchain (*.rvtools)",
        )
        if not filename:
            return
        self._offline_bundle = Path(filename)
        self._start_offline_worker(
            _OfflineToolchainWorker(service, "inspect", self._offline_bundle),
            "inspect",
            "Verifying every kit member and its local Ed25519 transfer signature…",
            determinate=False,
        )

    def _start_offline_worker(
        self,
        worker: _OfflineToolchainWorker,
        operation: str,
        message: str,
        *,
        determinate: bool,
    ) -> None:
        self._offline_worker = worker
        self._offline_operation = operation
        self._set_offline_busy(True)
        self._set_offline_status(message, "ToolchainManifestStatus")
        self.offline_progress.begin(determinate=determinate)
        worker.signals.progress.connect(self.offline_progress.report)
        worker.signals.complete.connect(self._offline_complete)
        worker.signals.failed.connect(self._offline_failed)
        start_background(worker)

    @Slot(object)
    def _offline_complete(self, value: object) -> None:
        operation = self._offline_operation
        self._offline_worker = None
        self._offline_operation = ""
        self._set_offline_busy(False)
        self.offline_progress.finish()
        if operation == "inspect":
            if not isinstance(value, OfflineToolchainInspection):
                self._offline_failed("ROMVERSE returned invalid offline kit evidence")
                return
            package_copy = ", ".join(value.packages)
            self._set_offline_status(
                f"SIGNED KIT VERIFIED  •  {len(value.files)} file(s)  •  {package_copy}\n"
                f"Signer {value.signer_fingerprint}  •  Kit SHA-256 {value.bundle_sha256}\n"
                "Not imported. Compare the full signer fingerprint with the exporting computer.",
                "Good",
            )
            answer = QMessageBox.question(
                self,
                "Trust this offline equipment signer?",
                "The kit's file hashes and local Ed25519 transfer signature are valid.\n\n"
                f"Packages: {package_copy}\n"
                f"Signer fingerprint:\n{value.signer_fingerprint}\n\n"
                f"Kit SHA-256:\n{value.bundle_sha256}\n\n"
                "Import only if the complete signer fingerprint matches the value shown on the "
                "trusted exporting computer. This local transfer signature is not an official "
                "ROMVERSE release signature. Import replaces only the named managed packages, "
                "then Forge Arsenal verifies them again. No phone command will run.\n\n"
                "Import this exact kit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self._set_offline_status(
                    "Kit verified but not imported. No managed package or phone was changed.",
                    "Warning",
                )
                return
            service = self.offline_service
            if service is None:
                self._offline_failed("The offline toolchain service is unavailable")
                return
            self._start_offline_worker(
                _OfflineToolchainWorker(
                    service,
                    "import",
                    self._offline_bundle,
                    accepted_bundle_sha256=value.bundle_sha256,
                    accepted_signer_fingerprint=value.signer_fingerprint,
                ),
                "import",
                "Installing the exact confirmed kit with rollback protection…",
                determinate=True,
            )
            return
        if operation == "export" and isinstance(value, OfflineToolchainInspection):
            self._set_offline_status(
                f"OFFLINE KIT EXPORTED  •  {len(value.files)} file(s)  •  "
                f"{len(value.packages)} package(s)\n"
                f"Signer {value.signer_fingerprint}  •  Kit SHA-256 {value.bundle_sha256}\n"
                "Record the full signer fingerprint separately for the importing computer. "
                "Phone changed: no. Authority: none.",
                "Good",
            )
            return
        if operation == "import" and isinstance(value, OfflineToolchainImportReceipt):
            self._activate_managed_tools()
            self._verify_local_tools(emit=True)
            self._set_offline_status(
                f"OFFLINE KIT IMPORTED  •  {value.file_count} file(s)  •  "
                f"{len(value.packages)} package(s)  •  receipt {value.receipt_digest}\n"
                "Managed receipts and current executables were rechecked. Phone changed: no. "
                "Authority: none.",
                "Good",
            )
            return
        self._offline_failed("ROMVERSE returned an invalid offline toolchain result")

    @Slot(str)
    def _offline_failed(self, message: str) -> None:
        self._offline_worker = None
        self._offline_operation = ""
        self._set_offline_busy(False)
        self.offline_progress.stop()
        self._set_offline_status(f"Offline kit stopped safely: {message}", "Danger")

    def _set_offline_busy(self, busy: bool) -> None:
        enabled = self.offline_service is not None and not busy
        self.offline_import_button.setEnabled(enabled)
        self.offline_export_button.setEnabled(
            enabled
            and self.workspace is not None
            and bool(verified_managed_package_roots(self.workspace))
        )

    def _set_offline_status(self, message: str, state: str) -> None:
        self.offline_status.setText(message)
        self.offline_status.setObjectName(state)
        self._repolish(self.offline_status)

    def _verify_local_tools(self, *, emit: bool) -> None:
        self._activate_managed_tools()
        self.statuses = ToolVerifier(self.host, self.runner).verify_extended()
        if hasattr(self, "offline_export_button"):
            self._set_offline_busy(self._offline_worker is not None)
        self._render()
        if emit:
            self.statuses_changed.emit(self.statuses)

    def _activate_managed_tools(self) -> None:
        if self.workspace is None:
            return
        activate_verified_managed_tools(self.workspace)

    def _guided_setup(self) -> None:
        dialog = ToolchainSetupDialog(
            self.host,
            self.statuses,
            self.workspace,
            self,
            required_names=ROM_STUDIO_DEFAULT_REQUIRED_TOOLS,
        )
        dialog.exec()
        self.refresh()

    def _repair_platform_tools(self) -> None:
        health = self.host_health or self._assess_host_health()
        if not health.needs_platform_tools_repair or self.workspace is None:
            return
        repair_statuses = tuple(
            ToolStatus(
                status.name,
                False,
                status.path,
                status.version,
                "Replace ADB and Fastboot together with the current official Platform Tools pair",
            )
            if status.name in {"ADB", "Fastboot"}
            else status
            for status in self.statuses
        )
        dialog = ToolchainSetupDialog(
            self.host,
            repair_statuses,
            self.workspace,
            self,
            required_names=("ADB", "Fastboot"),
        )
        dialog.setWindowTitle("ROMVERSE • Repair Android Platform Tools pair")
        dialog.status.setText(
            "This replaces only ROMVERSE's managed ADB and Fastboot pair after your explicit "
            "confirmation, then verifies both again. No phone command or driver change runs."
        )
        dialog.exec()
        self.refresh()

    def open_device_pack_context(self, context: DevicePackToolchainContext) -> bool:
        """Open a validated, zero-authority view of one Pack's exact host requirements."""

        if not self._valid_device_pack_context(context):
            return False
        self._studio_project_context = None
        self._studio_project_context_stale = False
        self._repair_solution_context = None
        self._repair_solution_outcome_saved = False
        self._repair_solution_outcome_error = ""
        self._device_pack_context = context
        self._device_pack_context_stale = False
        self.device_pack_handoff.setVisible(True)
        # Opening an evidence view performs a fresh host-only verification but does
        # not announce a runtime change or trigger Device Engine to scan the phone.
        self._verify_local_tools(emit=False)
        return True

    def clear_device_pack_context(self) -> None:
        self._device_pack_context = None
        self._device_pack_context_stale = False
        if self._studio_project_context is None:
            self.device_pack_handoff.setVisible(False)

    def open_studio_project_context(self, context: StudioProjectToolchainContext) -> bool:
        """Open one exact Studio project as a source-bound, host-only Forge view."""

        if not self._valid_studio_project_context(context):
            return False
        self._device_pack_context = None
        self._device_pack_context_stale = False
        self._repair_solution_context = None
        self._repair_solution_outcome_saved = False
        self._repair_solution_outcome_error = ""
        self._studio_project_context = context
        self._studio_project_context_stale = False
        self.device_pack_handoff.setVisible(True)
        self._verify_local_tools(emit=False)
        return True

    def open_repair_solution_context(self, context: RepairToolchainContext) -> bool:
        """Show an exact research-bound host-tool review without running verification."""

        if not self._valid_repair_solution_context(context):
            return False
        self._device_pack_context = None
        self._device_pack_context_stale = False
        self._studio_project_context = None
        self._studio_project_context_stale = False
        self._repair_solution_context = context
        self._repair_solution_outcome_saved = False
        self._repair_solution_outcome_error = ""
        self._render()
        self.context_refresh_button.setFocus(Qt.FocusReason.OtherFocusReason)
        return True

    def clear_studio_project_context(self) -> None:
        self._studio_project_context = None
        self._studio_project_context_stale = False
        if self._device_pack_context is None:
            self.device_pack_handoff.setVisible(False)

    def open_studio_project_setup(self, context: StudioProjectToolchainContext) -> bool:
        """Open setup only after MainWindow re-derives the same exact project context."""

        if context != self._studio_project_context or not self._valid_studio_project_context(
            context
        ):
            self.studio_project_context_changed(
                "The setup request no longer matches the current exact ROM Studio project"
            )
            return False
        dialog = ToolchainSetupDialog(
            self.host,
            self.statuses,
            self.workspace,
            self,
            required_names=context.required_tools,
        )
        dialog.setWindowTitle(f"ROMVERSE • {context.project_name} exact tool setup")
        dialog.status.setText(
            f"Exact project {context.project_id} • {len(context.required_tools)} source-bound "
            "requirements • no build or phone action starts here."
        )
        dialog.exec()
        self.refresh()
        return True

    def open_device_pack_setup(self, context: DevicePackToolchainContext) -> bool:
        """Open setup only when MainWindow has freshly revalidated the same context."""

        if context != self._device_pack_context or not self._valid_device_pack_context(context):
            self.device_pack_context_changed(
                "The setup request no longer matches the current exact Device Pack context"
            )
            return False
        dialog = ToolchainSetupDialog(
            self.host,
            self.statuses,
            self.workspace,
            self,
            required_names=context.required_tools,
        )
        dialog.setWindowTitle(f"ROMVERSE • {context.pack_name} exact tool setup")
        dialog.status.setText(
            f"Exact Pack {context.pack_id} • {len(context.required_tools)} declared build "
            "requirements • no build or phone action starts here."
        )
        dialog.exec()
        self.refresh()
        return True

    def device_pack_handoff_stopped(self, reason: str) -> None:
        self.device_pack_handoff_feedback.setText(
            f"DEVICE PACK HANDOFF STOPPED  •  {reason}  •  NO INSTALL, BUILD, OR PHONE ACTION STARTED"
        )
        self.device_pack_handoff_feedback.setObjectName("Danger")
        self._repolish(self.device_pack_handoff_feedback)

    def device_pack_requirements_ready(self) -> bool:
        context = self._device_pack_context
        if context is None or self._device_pack_context_stale:
            return False
        statuses = {status.name: status for status in self.statuses}
        return all(
            statuses.get(name) is not None and statuses[name].available
            for name in context.required_tools
        )

    def device_pack_context_matches(self, context: DevicePackToolchainContext) -> bool:
        return (
            not self._device_pack_context_stale
            and context == self._device_pack_context
            and self._valid_device_pack_context(context)
        )

    def device_pack_context_identity(self) -> tuple[str, str, str, str] | None:
        context = self._device_pack_context
        if context is None:
            return None
        return (
            context.pack_id,
            context.pack_sha256,
            context.model,
            context.codename,
        )

    def rebind_device_pack_context(self, context: DevicePackToolchainContext) -> bool:
        """Refresh a retained Forge card after the same exact device report is reissued."""

        if not self._valid_device_pack_context(context):
            return False
        expected = self.device_pack_context_identity()
        received = (
            context.pack_id,
            context.pack_sha256,
            context.model,
            context.codename,
        )
        if expected != received:
            return False
        self._device_pack_context = context
        self._device_pack_context_stale = False
        self._render_device_pack_context()
        return True

    def device_pack_context_changed(
        self,
        reason: str = "Device Atlas now reports a different phone or exact Device Pack",
    ) -> None:
        """Disable retained actions immediately when Device Atlas selects other evidence."""

        if self._device_pack_context is None:
            return
        self._device_pack_context_stale = True
        self.context_setup_button.setEnabled(False)
        self.context_continue_button.setEnabled(False)
        self.device_pack_handoff_stopped(reason)

    def studio_project_context_matches(self, context: StudioProjectToolchainContext) -> bool:
        return (
            not self._studio_project_context_stale
            and context == self._studio_project_context
            and self._valid_studio_project_context(context)
        )

    def studio_project_context_changed(self, reason: str) -> None:
        """Disable retained Studio actions when project, source, or derived tools change."""

        if self._studio_project_context is None:
            return
        self._studio_project_context_stale = True
        self.context_setup_button.setEnabled(False)
        self.context_continue_button.setEnabled(False)
        self.device_pack_handoff_feedback.setText(
            f"ROM STUDIO HANDOFF STOPPED  •  {reason}  •  "
            "NO INSTALL, PROJECT WORKER, BUILD, ROOT, FLASH, OR PHONE ACTION STARTED"
        )
        self.device_pack_handoff_feedback.setObjectName("Danger")
        self._repolish(self.device_pack_handoff_feedback)
        self._render_studio_project_context()

    def _request_device_pack_setup(self) -> None:
        repair_context = self._repair_solution_context
        if repair_context is not None:
            self._open_repair_solution_setup(repair_context)
            return
        studio_context = self._studio_project_context
        if studio_context is not None:
            self.studio_project_setup_requested.emit(
                studio_context.project_id,
                studio_context.context_digest,
            )
            return
        context = self._device_pack_context
        if context is not None:
            self.device_pack_setup_requested.emit(
                context.pack_id,
                context.pack_sha256,
                context.report_digest,
            )

    def _open_repair_solution_setup(self, context: RepairToolchainContext) -> None:
        if context != self._repair_solution_context or not self._valid_repair_solution_context(
            context
        ):
            return
        dialog = ToolchainSetupDialog(
            self.host,
            self.statuses,
            self.workspace,
            self,
            required_names=context.required_tools,
        )
        dialog.setWindowTitle("ROMVERSE • Verify official Android Platform Tools")
        dialog.status.setText(
            "Install or select only ADB and Fastboot from the official Platform Tools route. "
            "This changes host tooling only; no phone command, project worker, or flash starts."
        )
        dialog.exec()
        self.refresh()

    def _request_device_pack_continue(self) -> None:
        studio_context = self._studio_project_context
        if studio_context is not None:
            self.studio_project_continue_requested.emit(
                studio_context.project_id,
                studio_context.context_digest,
            )
            return
        context = self._device_pack_context
        if context is not None:
            self.device_pack_continue_requested.emit(
                context.pack_id,
                context.pack_sha256,
                context.report_digest,
            )

    def _request_device_atlas_return(self) -> None:
        context = self._device_pack_context
        if context is not None and not self._device_pack_context_stale:
            self.device_atlas_requested.emit(
                context.pack_id,
                context.pack_sha256,
                context.report_digest,
            )

    def _request_context_guide(self) -> None:
        if self._repair_solution_context is not None:
            self.knowledge_article_requested.emit("android-platform-tools-verification")
            return
        key = (
            "rom-studio-project-toolchain"
            if self._studio_project_context is not None
            else "device-pack-build-toolchain"
        )
        self.knowledge_article_requested.emit(key)

    @staticmethod
    def _valid_device_pack_context(context: DevicePackToolchainContext) -> bool:
        return bool(
            re.fullmatch(r"[0-9a-f]{64}", context.report_digest)
            and re.fullmatch(r"[0-9a-f]{64}", context.pack_sha256)
            and context.pack_id.strip()
            and context.pack_name.strip()
            and context.model.strip()
            and context.codename.strip()
            and context.required_tools
            and len(context.required_tools) == len(set(context.required_tools))
            and all(name in ROM_STUDIO_TOOL_CATALOG for name in context.required_tools)
        )

    @staticmethod
    def _valid_studio_project_context(context: StudioProjectToolchainContext) -> bool:
        source_blueprint_valid = bool(
            context.source_kind
            and context.source_kind in {"ota-payload", "fastboot-super", "partition-bundle"}
            and re.fullmatch(r"[0-9a-f]{64}", context.source_blueprint_digest)
            and re.fullmatch(r"[0-9a-f]{64}", context.source_plan_digest)
        )
        source_blueprint_empty = not any(
            (
                context.source_kind,
                context.source_blueprint_digest,
                context.source_plan_digest,
            )
        )
        return bool(
            re.fullmatch(r"[0-9a-f]{64}", context.context_digest)
            and re.fullmatch(r"[0-9a-f]{64}", context.source_sha256)
            and (not context.pack_sha256 or re.fullmatch(r"[0-9a-f]{64}", context.pack_sha256))
            and (
                not context.inspection_digest
                or re.fullmatch(r"[0-9a-f]{64}", context.inspection_digest)
            )
            and context.project_id.strip()
            and context.project_name.strip()
            and context.required_tools
            and len(context.required_tools) == len(set(context.required_tools))
            and all(name in ROM_STUDIO_TOOL_CATALOG for name in context.required_tools)
            and (source_blueprint_valid or source_blueprint_empty)
            and (
                not context.build_contract_bound
                or bool(context.device_pack_id and context.pack_sha256)
            )
        )

    @staticmethod
    def _valid_repair_solution_context(context: RepairToolchainContext) -> bool:
        receipt = context.receipt
        lead = receipt.candidates[0] if receipt.candidates else None
        return bool(
            context.action_id == "verify-platform-tools"
            and re.fullmatch(r"[0-9a-f]{64}", context.fingerprint_id)
            and re.fullmatch(r"[0-9a-f]{64}", context.receipt_digest)
            and re.fullmatch(r"[A-Za-z0-9._:-]{1,120}", context.source_id)
            and context.required_tools == ("ADB", "Fastboot")
            and receipt.fingerprint.fingerprint_id == context.fingerprint_id
            and receipt.receipt_digest == context.receipt_digest
            and lead is not None
            and lead.local_action_id == context.action_id
            and lead.source_id == context.source_id
            and lead.authority in {SourceAuthority.OFFICIAL, SourceAuthority.MAINTAINER}
        )

    def _render_repair_solution_context(self) -> None:
        context = self._repair_solution_context
        if context is None:
            return
        statuses = {status.name: status for status in self.statuses}
        missing = tuple(
            name
            for name in context.required_tools
            if name not in statuses or not statuses[name].available
        )
        ready = len(context.required_tools) - len(missing)
        self.device_pack_handoff.setVisible(True)
        self.device_pack_handoff_eyebrow.setText(
            "RECOVERY BAY SMART SOLUTION  •  SAVED OFFICIAL EVIDENCE"
        )
        self.device_pack_handoff_title.setText("Review Android Platform Tools on this computer")
        self.device_pack_handoff_detail.setText(
            f"Research fingerprint {context.fingerprint_id[:16]}… • receipt "
            f"{context.receipt_digest[:16]}… • source {context.source_id}\n"
            f"{ready} of {len(context.required_tools)} required host tools currently verify. "
            "Choose Re-check exact tools for a host-only version/path check, or explicitly set "
            "up the missing official package. This evidence grants no ADB target, project-worker, "
            "build, flash, wipe, relock, or phone authority."
        )
        self.device_pack_handoff_badge.setText(
            f"{ready}/{len(context.required_tools)} PLATFORM TOOLS  •  PHONE AUTHORITY: NONE"
        )
        self.device_pack_handoff_badge.setObjectName("Good" if not missing else "Warning")
        self._repolish(self.device_pack_handoff_badge)
        self.context_refresh_button.setVisible(True)
        self.context_refresh_button.setText("Re-check exact tools")
        self.context_setup_button.setVisible(True)
        self.context_setup_button.setEnabled(bool(missing))
        self.context_setup_button.setText(
            "Set up ADB + Fastboot" if missing else "Platform Tools verified"
        )
        self.context_continue_button.setVisible(False)
        self.context_return_button.setVisible(False)
        self.context_guide_button.setVisible(True)
        self.context_guide_button.setText("Open verified Platform Tools guide")
        self.device_pack_handoff_feedback.setText(
            "SMART SOLUTION OUTCOME VERIFIED AND SAVED  •  PHONE CHANGED: NO"
            if self._repair_solution_outcome_saved
            else f"SMART SOLUTION OUTCOME NOT SAVED  •  {self._repair_solution_outcome_error}  •  PHONE CHANGED: NO"
            if self._repair_solution_outcome_error
            else "MISSING HOST REQUIREMENTS  •  "
            + (" • ".join(missing) if missing else "none")
            + "  •  RECOMMENDATION REVIEW ONLY"
        )
        self.device_pack_handoff_feedback.setObjectName(
            "Good"
            if self._repair_solution_outcome_saved
            else "Warning"
            if self._repair_solution_outcome_error or missing
            else "Good"
        )
        self._repolish(self.device_pack_handoff_feedback)

    def _record_repair_solution_outcome(self) -> None:
        context = self._repair_solution_context
        if (
            context is None
            or self.workspace is None
            or not self._valid_repair_solution_context(context)
        ):
            return
        statuses = {status.name: status for status in self.statuses}
        if any(
            name not in statuses or not statuses[name].available or not statuses[name].path
            for name in context.required_tools
        ):
            self._repair_solution_outcome_saved = False
            self._repair_solution_outcome_error = ""
            self._render_repair_solution_context()
            return
        lead = context.receipt.candidates[0]
        remediation = OnlineRemediationService(self.workspace)
        try:
            decision = remediation.synthesize(context.receipt)
            if lead.source_id in decision.locally_verified_source_ids:
                self._repair_solution_outcome_saved = True
                self._repair_solution_outcome_error = ""
                self._render_repair_solution_context()
                return
            evidence = ToolchainVerificationStore(self.workspace).record(
                self.statuses,
                context.required_tools,
            )
            remediation.record_verified_outcome(
                context.receipt.fingerprint,
                lead,
                TypedLocalActionEvidence(
                    context.action_id,
                    evidence.receipt_digest,
                    evidence.evidence_ref,
                    ToolchainVerificationStore.FORMAT,
                ),
                "Forge Arsenal verified the exact ADB and Fastboot paths, versions, and executable hashes without targeting a phone.",
            )
        except (OSError, TypeError, ValueError):
            self._repair_solution_outcome_saved = False
            self._repair_solution_outcome_error = (
                "The research or exact host-tool receipt failed revalidation"
            )
            self._render_repair_solution_context()
            return
        self._repair_solution_outcome_saved = True
        self._repair_solution_outcome_error = ""
        self._render_repair_solution_context()

    def _render_studio_project_context(self) -> None:
        context = self._studio_project_context
        if context is None:
            return
        self.device_pack_handoff.setVisible(True)
        self.context_refresh_button.setVisible(True)
        self.context_refresh_button.setText("Re-check exact tools")
        self.context_setup_button.setVisible(True)
        self.context_continue_button.setVisible(True)
        self.context_guide_button.setVisible(True)
        self.context_guide_button.setText("Open verified guide")
        self.device_pack_handoff_eyebrow.setText(
            "ROM STUDIO HANDOFF  •  EXACT PROJECT / SOURCE-BOUND TOOL EVIDENCE"
        )
        self.device_pack_handoff_title.setText(f"{context.project_name} • exact host toolchain")
        statuses = {status.name: status for status in self.statuses}
        missing = tuple(
            name
            for name in context.required_tools
            if name not in statuses or not statuses[name].available
        )
        ready = len(context.required_tools) - len(missing)
        if context.build_contract_bound:
            pack_copy = (
                f"Pack {context.device_pack_id} • SHA-256 {context.pack_sha256[:16]}… • "
                "exact build contract"
            )
        elif context.source_blueprint_digest:
            pack_copy = (
                f"Project-local {context.source_kind} blueprint "
                f"{context.source_blueprint_digest[:16]}… • source plan "
                f"{context.source_plan_digest[:16]}… • no source-matched flash contract"
            )
        else:
            pack_copy = (
                "No source-matched Device Pack build contract • structural/default tools only"
            )
        inspection_copy = (
            f"inspection {context.inspection_digest[:16]}…"
            if context.inspection_digest
            else "inspection evidence unavailable"
        )
        self.device_pack_handoff_detail.setText(
            f"Project {context.project_id} • protected source {context.source_sha256[:16]}…\n"
            f"{pack_copy} • {inspection_copy}\nRequired in derived order: "
            + " • ".join(context.required_tools)
            + f"\n{ready} of {len(context.required_tools)} host requirements verified. "
            "This view verifies or sets up local host tools only; it grants no project-worker, "
            "build, root, approval, flash, wipe, relock, or phone authority."
        )
        self.device_pack_handoff_badge.setText(
            f"{ready}/{len(context.required_tools)} TOOLS  •  "
            + ("SOURCE CONTRACT BOUND" if context.build_contract_bound else "HOST EVIDENCE ONLY")
        )
        self.device_pack_handoff_badge.setObjectName("Good" if not missing else "Warning")
        self._repolish(self.device_pack_handoff_badge)
        self.context_return_button.setVisible(False)
        self.context_continue_button.setText("Return to exact ROM project")
        self.context_continue_button.setEnabled(not self._studio_project_context_stale)
        self.context_continue_button.setToolTip(
            "Return the freshly verified host-tool evidence to this exact project. No build starts."
        )
        self.context_setup_button.setEnabled(
            bool(missing) and not self._studio_project_context_stale
        )
        self.context_setup_button.setText(
            "Set up missing requirements" if missing else "Exact requirements verified"
        )
        if self._studio_project_context_stale:
            self.device_pack_handoff_badge.setText(
                "STALE PROJECT CONTEXT  •  REOPEN FROM ROM STUDIO  •  ZERO AUTHORITY"
            )
            self.device_pack_handoff_badge.setObjectName("Danger")
            self._repolish(self.device_pack_handoff_badge)
            return
        missing_copy = " • ".join(missing) if missing else "none"
        self.device_pack_handoff_feedback.setText(
            f"MISSING HOST REQUIREMENTS  •  {missing_copy}  •  BUILD / PHONE AUTHORITY: NONE"
        )
        self.device_pack_handoff_feedback.setObjectName("Warning" if missing else "Good")
        self._repolish(self.device_pack_handoff_feedback)

    def _render_device_pack_context(self) -> None:
        context = self._device_pack_context
        if context is None:
            if self._studio_project_context is None and self._repair_solution_context is None:
                self.device_pack_handoff.setVisible(False)
            return
        self.device_pack_handoff.setVisible(True)
        self.context_refresh_button.setVisible(True)
        self.context_refresh_button.setText("Re-check exact tools")
        self.context_setup_button.setVisible(True)
        self.context_continue_button.setVisible(True)
        self.context_guide_button.setVisible(True)
        self.context_guide_button.setText("Open verified guide")
        self.device_pack_handoff_eyebrow.setText("DEVICE ATLAS HANDOFF  •  EXACT BUILD CONTRACT")
        self.context_return_button.setVisible(True)
        self.context_return_button.setText("Return to Device Atlas")
        self.context_continue_button.setText("Continue to ROM Studio")
        statuses = {status.name: status for status in self.statuses}
        missing = tuple(
            name
            for name in context.required_tools
            if name not in statuses or not statuses[name].available
        )
        ready = len(context.required_tools) - len(missing)
        build_state = "BUILD CONTRACT READY" if context.build_contract_ready else "BUILD LOCKED"
        flash_state = "FLASH CONTRACT READY" if context.flash_contract_ready else "FLASH LOCKED"
        self.device_pack_handoff_title.setText(f"{context.pack_name} • exact host toolchain")
        self.device_pack_handoff_detail.setText(
            f"{context.model} / {context.codename}  •  Pack {context.pack_id}  •  "
            f"SHA-256 {context.pack_sha256[:16]}…\nRequired in declared order: "
            + " • ".join(context.required_tools)
            + f"\n{ready} of {len(context.required_tools)} host requirements verified. "
            "Host tools enable local inspection/build stages only; they do not change Device "
            "Atlas evidence, approve a build, or grant flash authority."
        )
        self.device_pack_handoff_badge.setText(
            f"{ready}/{len(context.required_tools)} TOOLS  •  {build_state}  •  {flash_state}"
        )
        self.device_pack_handoff_badge.setObjectName(
            "Good"
            if not missing and context.build_contract_ready
            else "Warning"
            if context.build_contract_ready
            else "Danger"
        )
        self._repolish(self.device_pack_handoff_badge)
        if self._device_pack_context_stale:
            self.device_pack_handoff_badge.setText(
                "STALE CONTEXT  •  REOPEN FROM DEVICE ATLAS  •  ZERO AUTHORITY"
            )
            self.device_pack_handoff_badge.setObjectName("Danger")
            self._repolish(self.device_pack_handoff_badge)
            self.context_setup_button.setEnabled(False)
            self.context_continue_button.setEnabled(False)
            return
        self.context_setup_button.setEnabled(bool(missing))
        self.context_setup_button.setText(
            "Set up missing requirements" if missing else "Exact requirements verified"
        )
        can_continue = not missing and context.build_contract_ready
        self.context_continue_button.setEnabled(can_continue)
        self.context_continue_button.setToolTip(
            "Open ROM Studio with the current exact build context. Flash remains an independent "
            "Device Atlas and Guardian decision."
            if can_continue
            else "Every exact host requirement and the Device Pack build contract must verify first."
        )
        missing_copy = " • ".join(missing) if missing else "none"
        self.device_pack_handoff_feedback.setText(
            f"MISSING HOST REQUIREMENTS  •  {missing_copy}  •  FLASH AUTHORITY: NONE"
        )
        self.device_pack_handoff_feedback.setObjectName("Warning" if missing else "Good")
        self._repolish(self.device_pack_handoff_feedback)

    def _render(self) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()
                item.widget().deleteLater()
        context = (
            self._repair_solution_context
            or self._studio_project_context
            or self._device_pack_context
        )
        required = context.required_tools if context is not None else ()
        required_set = set(required)
        status_by_name = {status.name: status for status in self.statuses}
        ordered_statuses = tuple(
            status_by_name.get(
                name,
                ToolStatus(name, False, detail="Tool verification result is unavailable"),
            )
            for name in required
        ) + tuple(status for status in self.statuses if status.name not in required_set)
        ready = sum(status.available for status in ordered_statuses)
        self.android_sdk_guide_button.setVisible(
            any(
                not status.available and status.name in {"AAPT2", "APK Signer"}
                for status in ordered_statuses
            )
        )
        communication = QFrame()
        communication.setObjectName("ToolCommunicationCard")
        communication_layout = QVBoxLayout(communication)
        communication_layout.setContentsMargins(16, 13, 16, 13)
        communication_layout.setSpacing(5)
        communication_eyebrow = QLabel("DEVICE COMMUNICATION  •  GUARDIAN-ROUTED EVIDENCE")
        communication_eyebrow.setObjectName("Eyebrow")
        communication_title, communication_detail, communication_state = self._communication_copy()
        communication_heading = QLabel(communication_title)
        communication_heading.setObjectName("SectionTitle")
        communication_body = QLabel(communication_detail)
        communication_body.setObjectName(communication_state)
        communication_body.setWordWrap(True)
        communication_layout.addWidget(communication_eyebrow)
        communication_layout.addWidget(communication_heading)
        communication_layout.addWidget(communication_body)
        self.layout.addWidget(communication)
        self.host_health = self._assess_host_health()
        doctor = QFrame()
        doctor.setObjectName("ToolHostDoctorCard")
        doctor_layout = QVBoxLayout(doctor)
        doctor_layout.setContentsMargins(16, 13, 16, 13)
        doctor_layout.setSpacing(7)
        doctor_top = QHBoxLayout()
        doctor_copy = QVBoxLayout()
        doctor_eyebrow = QLabel("HOST CONNECTION DOCTOR  •  READ-ONLY ASSESSMENT")
        doctor_eyebrow.setObjectName("Eyebrow")
        doctor_title = QLabel(self.host_health.platform_tools_title)
        doctor_title.setObjectName("SectionTitle")
        doctor_copy.addWidget(doctor_eyebrow)
        doctor_copy.addWidget(doctor_title)
        doctor_top.addLayout(doctor_copy, 1)
        doctor_badge = QLabel(self.host_health.overall_state.value.upper())
        doctor_badge.setObjectName(
            "Good"
            if self.host_health.overall_state is ToolHealthState.VERIFIED
            else "Danger"
            if self.host_health.overall_state in {ToolHealthState.MISSING, ToolHealthState.CONFLICT}
            else "Warning"
        )
        doctor_top.addWidget(doctor_badge)
        doctor_layout.addLayout(doctor_top)
        platform_detail = QLabel(self.host_health.platform_tools_detail)
        platform_detail.setObjectName(
            "Good"
            if self.host_health.platform_tools_state is ToolHealthState.VERIFIED
            else "Warning"
        )
        platform_detail.setWordWrap(True)
        doctor_layout.addWidget(platform_detail)
        version_copy = "  •  ".join(
            f"{check.name} {check.detected} (floor {check.minimum}) — {check.state.value}"
            for check in self.host_health.version_checks
        )
        versions = QLabel(version_copy)
        versions.setObjectName("Muted")
        versions.setWordWrap(True)
        doctor_layout.addWidget(versions)
        usb_title = QLabel(self.host_health.usb.title)
        usb_title.setObjectName(
            "Good" if self.host_health.usb.state is ToolHealthState.VERIFIED else "Warning"
        )
        usb_detail = QLabel(self.host_health.usb.detail)
        usb_detail.setObjectName("Muted")
        usb_detail.setWordWrap(True)
        doctor_layout.addWidget(usb_title)
        doctor_layout.addWidget(usb_detail)
        doctor_actions = QHBoxLayout()
        self.platform_tools_repair_button = QPushButton("Install one verified Platform Tools pair")
        self.platform_tools_repair_button.setObjectName("Primary")
        self.platform_tools_repair_button.setVisible(self.host_health.needs_platform_tools_repair)
        self.platform_tools_repair_button.setEnabled(
            self.host_health.needs_platform_tools_repair and self.workspace is not None
        )
        self.platform_tools_repair_button.setToolTip(
            "Open an explicit host-only setup. No phone or driver command runs."
        )
        self.platform_tools_repair_button.clicked.connect(self._repair_platform_tools)
        self.host_usb_guide_button = QPushButton(
            "Open exact OEM driver guide"
            if self.host.name.casefold() == "windows"
            else "Open Linux USB permission guide"
            if self.host.name.casefold() == "linux"
            else "Open Android USB guide"
        )
        guide_article = self.host_health.usb.guide_article_id
        self.host_usb_guide_button.clicked.connect(
            lambda _checked=False, article=guide_article: self.knowledge_article_requested.emit(
                article
            )
        )
        doctor_actions.addWidget(self.platform_tools_repair_button)
        doctor_actions.addWidget(self.host_usb_guide_button)
        doctor_actions.addStretch()
        doctor_layout.addLayout(doctor_actions)
        authority = QLabel(
            "HOST CHECK ONLY  •  DRIVER INSTALLATION REMAINS OPERATING-SYSTEM CONTROLLED  •  "
            "PHONE AUTHORITY: NONE"
        )
        authority.setObjectName("Muted")
        authority.setWordWrap(True)
        doctor_layout.addWidget(authority)
        self.layout.addWidget(doctor)
        summary = QLabel(
            f"EQUIPMENT BAY  •  {ready} of {len(ordered_statuses)} slots verified on {self.host.name}"
        )
        summary.setObjectName("Good" if ready == len(ordered_statuses) else "Warning")
        self.layout.addWidget(summary)
        for index, status in enumerate(ordered_statuses, start=1):
            card = QFrame()
            card.setObjectName("ToolBaySlot")
            row = QVBoxLayout(card)
            row.setContentsMargins(16, 12, 16, 12)
            top = QVBoxLayout()
            slot_state = "VERIFIED" if status.available else "NEEDS ATTENTION"
            slot = QLabel(f"SLOT {index:02d}  •  {slot_state}")
            slot.setObjectName("Eyebrow")
            top.addWidget(slot)
            name_row = QHBoxLayout()
            name = QLabel(status.name)
            name.setObjectName("SectionTitle")
            name_row.addWidget(name)
            if status.name in required:
                required_badge = QLabel(
                    "SMART SOLUTION REQUIREMENT"
                    if self._repair_solution_context is not None
                    else "EXACT PROJECT REQUIREMENT"
                    if self._studio_project_context is not None
                    else "EXACT PACK REQUIREMENT"
                )
                required_badge.setObjectName("Good" if status.available else "Warning")
                name_row.addStretch()
                name_row.addWidget(required_badge)
            state = QLabel(
                f"✓ Ready  •  {status.version}"
                if status.available
                else f"! Not ready  •  {status.detail}"
            )
            state.setObjectName("Good" if status.available else "Warning")
            top.addLayout(name_row)
            top.addWidget(state)
            if status.path:
                path = QLabel(status.path)
                path.setObjectName("Muted")
                path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                top.addWidget(path)
            row.addLayout(top)
            self.layout.addWidget(card)
        self.layout.addStretch()
        if self._repair_solution_context is not None:
            self._render_repair_solution_context()
        elif self._studio_project_context is not None:
            self._render_studio_project_context()
        else:
            self._render_device_pack_context()

    def _assess_host_health(self) -> HostToolchainHealth:
        selected = self._communication_devices
        observed = self._observed_communication_devices
        communication_verified = any(
            device.state in {DeviceState.DEVICE, DeviceState.RECOVERY, DeviceState.SIDELOAD}
            or device.is_fastboot
            for device in selected
        )
        return assess_host_toolchain(
            self.host,
            tuple(self.statuses),
            communication_verified=communication_verified,
            transport_visible=bool(selected or observed),
            scan_failed=bool(self._communication_error),
        )

    def _communication_copy(self) -> tuple[str, str, str]:
        if self._communication_error:
            return (
                "Communication test needs attention",
                f"The latest bounded Device Engine scan failed: {self._communication_error}. "
                "Forge Arsenal did not change the phone. Recheck the verified tool, cable, host "
                "driver or Linux USB permission before trying again.",
                "Danger",
            )
        selected = self._communication_devices
        observed = self._observed_communication_devices
        if not selected and len(observed) > 1:
            return (
                "Choose the target in Command Deck",
                f"{len(observed)} Android transports are visible. ROMVERSE will not bind a "
                "communication result until one is selected. No additional command was run.",
                "Warning",
            )
        if not selected:
            return (
                "No Android transport currently visible",
                "Connect a phone when you want a genuine communication check. The equipment-bay "
                "inventory remains useful offline; this state is not a failed driver claim.",
                "Muted",
            )
        device = selected[0]
        if device.state is DeviceState.DEVICE:
            label = "ADB Android communication verified"
            detail = (
                f"Device Engine completed the Guardian-approved ADB discovery and identity path "
                f"for {device.display_name}."
            )
            state = "Good" if not device.errors else "Warning"
        elif device.state is DeviceState.RECOVERY:
            label = "ADB recovery communication verified"
            detail = "The latest Guardian-routed ADB discovery genuinely observed recovery mode."
            state = "Good"
        elif device.state is DeviceState.SIDELOAD:
            label = "ADB sideload communication verified"
            detail = "The latest Guardian-routed ADB discovery genuinely observed sideload mode."
            state = "Good"
        elif device.is_fastboot:
            mode = "fastbootd" if device.state is DeviceState.FASTBOOTD else "bootloader Fastboot"
            label = f"{mode} communication verified"
            detail = (
                "Device Engine completed Guardian-approved Fastboot discovery and bounded identity "
                "reads. No reboot, unlock, erase, flash, or write command was available."
            )
            state = "Good" if not device.errors else "Warning"
        elif device.state is DeviceState.UNAUTHORIZED:
            label = "ADB interface found • owner confirmation required"
            detail = (
                "The host can see the ADB interface, but the phone has not authorized this computer. "
                "Unlock the phone and accept only the RSA fingerprint you recognise."
            )
            state = "Warning"
        elif device.state is DeviceState.OFFLINE:
            label = "ADB transport found but not communicating"
            detail = (
                "Check the data cable, USB mode, current Platform Tools, and host driver or Linux "
                "permission. ROMVERSE will not report a successful communication test."
            )
            state = "Danger"
        else:
            label = "Android transport state is unconfirmed"
            detail = "The latest scan did not provide enough evidence to name a working mode."
            state = "Warning"
        if device.errors:
            detail += (
                f" {len(device.errors)} bounded probe warning(s) remain visible in Device Portal."
            )
        return label, detail + " Phone-change authority: none.", state

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)


class DownloadSignals(QObject):
    complete = Signal(str)
    failed = Signal(str)
    progress = Signal(int)
    phase = Signal(str, bool)


class ToolchainDownloadWorker(ManagedRunnable):
    def __init__(
        self,
        host: HostPlatform,
        selected: list[str],
        destination: Path,
        runner: CommandRunner | None = None,
        plan_items: tuple[ToolProvisionItem, ...] = (),
        boundary: Path | None = None,
    ) -> None:
        super().__init__()
        self.host = host
        self.selected = selected
        self.destination = destination
        self.runner = runner or SubprocessRunner()
        self.plan_items = plan_items
        self.boundary = boundary
        self.signals = DownloadSignals()

    @Slot()
    def execute(self) -> None:
        def measured_progress(label: str) -> DownloadProgress:
            publish = CoalescedProgress(self.signals.progress.emit)
            determinate = False

            def report(done: int, total: int) -> None:
                nonlocal determinate
                if total <= 0:
                    if determinate:
                        determinate = False
                        self.signals.phase.emit(label, False)
                    return
                if not determinate:
                    determinate = True
                    self.signals.phase.emit(label, True)
                percent = measured_percent(done, total)
                if percent is not None:
                    publish(percent)

            return report

        self.signals.phase.emit("Preparing the approved tool plan…", False)
        packages: dict[str, tuple[str, tuple[str, ...]]] = {}
        if "ADB" in self.selected or "Fastboot" in self.selected:
            platform_name = "windows" if self.host.name.lower() == "windows" else "linux"
            executables = (
                ("adb.exe", "fastboot.exe") if platform_name == "windows" else ("adb", "fastboot")
            )
            packages["platform-tools"] = (
                f"https://dl.google.com/android/repository/platform-tools-latest-{platform_name}.zip",
                executables,
            )
        managed: list[str] = []
        partition_names = {"simg2img", "LP Make", "LP Unpack", "LP Dump"}
        if partition_names.intersection(self.selected):
            try:
                label = "Downloading and verifying pinned Android partition tools…"
                self.signals.phase.emit(label, False)
                _path, hashes = install_pinned_partition_tools(
                    self.host.name,
                    self.destination,
                    boundary=self.boundary,
                    progress=measured_progress(label),
                )
                fingerprint = hashlib.sha256(
                    "".join(hashes[name] for name in sorted(hashes)).encode()
                ).hexdigest()
                managed.append(f"AOSP Partition Tools ({fingerprint[:12]}…)")
            except (OSError, ValueError) as exc:
                self.signals.failed.emit(f"Partition Tools download failed: {exc}")
                return
        if "Payload Dumper" in self.selected:
            try:
                self.signals.phase.emit("Resolving the official Payload Dumper release…", False)
                release = resolve_latest_payload_dumper(self.host.name)
                label = f"Downloading and verifying Payload Dumper {release.version}…"
                self.signals.phase.emit(label, False)
                _path, digest = install_payload_dumper_release(
                    release,
                    self.destination,
                    boundary=self.boundary,
                    progress=measured_progress(label),
                )
                managed.append(f"Payload Dumper {release.version} ({digest[:12]}…)")
            except (OSError, ValueError, tarfile.TarError) as exc:
                self.signals.failed.emit(f"Payload Dumper download failed: {exc}")
                return
        if "AVBTool" in self.selected:
            try:
                label = "Downloading and verifying official AOSP AVBTool…"
                self.signals.phase.emit(label, False)
                _path, digest = install_official_avbtool(
                    self.destination,
                    boundary=self.boundary,
                    progress=measured_progress(label),
                )
                managed.append(f"AVBTool ({digest[:12]}…)")
            except (OSError, ValueError) as exc:
                self.signals.failed.emit(f"AVBTool download failed: {exc}")
                return
        if "AAPT2" in self.selected:
            try:
                label = f"Downloading and verifying official AAPT2 {AAPT2_VERSION}…"
                self.signals.phase.emit(label, False)
                _path, digest = install_pinned_aapt2(
                    self.destination,
                    boundary=self.boundary,
                    progress=measured_progress(label),
                )
                managed.append(f"AAPT2 {AAPT2_VERSION} ({digest[:12]}…)")
            except (OSError, ValueError, zipfile.BadZipFile) as exc:
                self.signals.failed.emit(f"AAPT2 download failed: {exc}")
                return
        if "APK Signer" in self.selected:
            try:
                label = f"Downloading and verifying official apksig {APKSIG_VERSION}…"
                self.signals.phase.emit(label, False)
                _path, digest = install_pinned_apk_verifier(
                    self.destination,
                    boundary=self.boundary,
                    progress=measured_progress(label),
                )
                managed.append(
                    f"APK signature verifier {APKSIG_VERSION} ({digest[:12]}…; verification-only)"
                )
            except (OSError, ValueError, zipfile.BadZipFile) as exc:
                self.signals.failed.emit(f"APK signature verifier download failed: {exc}")
                return
        system_items = tuple(
            item
            for item in self.plan_items
            if item.name in self.selected and item.strategy is ProvisionStrategy.SYSTEM
        )
        if system_items:
            self.signals.phase.emit(
                "Waiting for the operating system to install and verify approved system packages…",
                False,
            )
            installed, detail = install_system_packages(system_items, self.host, self.runner)
            if not installed:
                self.signals.failed.emit(detail)
                return
            managed.append(detail)
        if not packages and not managed:
            self.signals.complete.emit(
                "No automatic package is available for the selected tools. The plan was recorded for manual installation."
            )
            return
        self.destination.mkdir(parents=True, exist_ok=True)
        downloaded: list[str] = []
        for name, (url, required_files) in packages.items():
            try:
                label = f"Downloading and verifying official {name}…"
                self.signals.phase.emit(label, False)
                _path, digest = install_official_archive(
                    name,
                    url,
                    self.destination,
                    required_files,
                    boundary=self.boundary,
                    progress=measured_progress(label),
                )
                downloaded.append(f"{name} ({digest[:12]}…)")
            except (OSError, ValueError, zipfile.BadZipFile) as exc:
                self.signals.failed.emit(f"Download failed for {name}: {exc}")
                return
        completed = downloaded + managed
        self.signals.complete.emit("Downloaded and prepared: " + ", ".join(completed))


class ToolchainSetupDialog(QDialog):
    completed = Signal(bool, str)

    def __init__(
        self,
        host: HostPlatform,
        statuses: tuple[ToolStatus, ...],
        workspace: Path | None,
        parent: QWidget | None = None,
        *,
        required_names: tuple[str, ...] | None = None,
        auto_start: bool = False,
        auto_close: bool = False,
    ) -> None:
        super().__init__(parent)
        self.host = host
        self.workspace = workspace
        self.required_names = required_names
        self.provision_plan = create_provision_plan(host, statuses, required_names)
        self.items_by_name = {item.name: item for item in self.provision_plan.missing}
        self._worker: ToolchainDownloadWorker | None = None
        self.auto_close = auto_close
        self.last_success: bool | None = None
        self.last_message = ""
        self.setWindowTitle("ROMVERSE • Forge Arsenal Setup")
        self.setMinimumSize(650, 560)
        layout = QVBoxLayout(self)
        title = QLabel("Forge Arsenal Setup")
        title.setObjectName("Title")
        layout.addWidget(title)
        intro = QLabel(
            "ROMVERSE selected only the missing dependencies required by the active Desktop workflow. Managed downloads are bounded and receipt-verified; Ubuntu or Fedora shows its normal administrator prompt only for approved system packages. Full Android SDK license acceptance remains user-controlled."
        )
        intro.setObjectName("Muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.checks: dict[str, QCheckBox] = {}
        scroll = QScrollArea()
        content = QWidget()
        content_layout = QVBoxLayout(content)
        status_by_name = {status.name: status for status in statuses}
        for item in self.provision_plan.missing:
            status = status_by_name.get(
                item.name,
                ToolStatus(
                    item.name,
                    False,
                    detail="Tool verification result is unavailable",
                ),
            )
            method = {
                ProvisionStrategy.MANAGED: "ROMVERSE managed download",
                ProvisionStrategy.SYSTEM: "operating-system authorized install",
                ProvisionStrategy.MANUAL: "manual action required",
            }[item.strategy]
            card = QFrame()
            card.setObjectName("Card")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 11, 14, 11)
            heading = QHBoxLayout()
            check = QCheckBox(f"{status.name}  —  {status.detail}")
            check.setChecked(item.strategy is not ProvisionStrategy.MANUAL)
            check.setEnabled(item.strategy is not ProvisionStrategy.MANUAL)
            check.setAccessibleDescription(item.explanation)
            check.setToolTip(
                f"{item.explanation}\n\nOfficial source:\n"
                f"{item.source or 'Official vendor documentation'}"
            )
            heading.addWidget(check, 1)
            method_badge = QLabel(method.upper())
            method_badge.setObjectName(
                "Good"
                if item.strategy is ProvisionStrategy.MANAGED
                else "Warning"
                if item.strategy is ProvisionStrategy.SYSTEM
                else "Muted"
            )
            heading.addWidget(method_badge)
            card_layout.addLayout(heading)
            explanation = QLabel(item.explanation)
            explanation.setObjectName("Muted")
            explanation.setWordWrap(True)
            card_layout.addWidget(explanation)
            self.checks[status.name] = check
            content_layout.addWidget(card)
        if not self.checks:
            ready = QLabel("All currently supported tools are verified.")
            ready.setObjectName("Good")
            content_layout.addWidget(ready)
        content_layout.addStretch()
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll, 1)
        actions = QHBoxLayout()
        open_sources = QPushButton("Open manual sources")
        open_sources.clicked.connect(self._open_sources)
        self.install_button = QPushButton("Install and verify requirements")
        self.install_button.setObjectName("Primary")
        self.install_button.clicked.connect(self._create_plan)
        actions.addWidget(open_sources)
        actions.addWidget(self.install_button)
        layout.addLayout(actions)
        self.status = QLabel("")
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = ProcessProgressBar()
        layout.addWidget(self.progress)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        if auto_start and self.provision_plan.missing:
            QTimer.singleShot(0, self._create_plan)
        elif auto_start and auto_close:
            # Automatic callers must never strand the user in an empty setup dialog.
            # The authoritative inventory already proves that every scoped requirement
            # is available, so this is a successful no-op rather than an installation.
            self.last_success = True
            self.last_message = "Every required Forge Arsenal tool is already verified."
            self.status.setText(self.last_message)
            self.status.setObjectName("Good")
            QTimer.singleShot(0, self.accept)

    def reject(self) -> None:
        if self._worker is not None:
            self.status.setText(
                "Installation is still running. Finish or cancel the visible operating-system authorization prompt first."
            )
            return
        super().reject()

    def closeEvent(self, event) -> None:
        if self._worker is not None:
            event.ignore()
            self.status.setText(
                "Installation is still running. Finish or cancel the visible operating-system authorization prompt first."
            )
            return
        super().closeEvent(event)

    def _selected(self) -> list[str]:
        return [name for name, check in self.checks.items() if check.isChecked()]

    def _open_sources(self) -> None:
        manual = tuple(item for item in self.provision_plan.manual if item.source)
        for item in manual:
            source = item.source
            if source:
                QDesktopServices.openUrl(QUrl(source))

    def _create_plan(self) -> None:
        if self._worker is not None:
            return
        selected = self._selected()
        plan = {
            "schema_version": 1,
            "host": self.host.name,
            "selected_tools": selected,
            "required_tools": list(self.required_names or ()),
            "sources": {name: source_for(name) for name in selected},
            "manual_requirements": [item.name for item in self.provision_plan.manual],
            "install_policy": "contract-scoped; user-approved; managed downloads plus visible OS authorization",
        }
        if self.workspace is not None:
            try:
                destination = self.workspace / "logs" / "toolchain-install-plan.json"
                atomic_write_json(
                    destination,
                    plan,
                    boundary=self.workspace,
                    maximum_bytes=MAX_MANAGED_RECEIPT_BYTES,
                )
            except OSError:
                pass
        if not selected:
            self.status.setText("Select at least one missing component.")
            return
        if self.workspace is None:
            self.status.setText(
                "Workspace is unavailable; cannot create a managed tools directory."
            )
            return
        self.status.setText(
            "Preparing verified requirements; approve the operating-system prompt if it appears …"
        )
        self.status.setObjectName("Muted")
        self.install_button.setEnabled(False)
        self.install_button.setText("Installing, please wait …")
        self.progress.begin()
        close_button = self.buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_button is not None:
            close_button.setEnabled(False)
        for check in self.checks.values():
            check.setEnabled(False)
        self._worker = ToolchainDownloadWorker(
            self.host,
            selected,
            self.workspace / "tools" / "downloads",
            plan_items=self.provision_plan.missing,
            boundary=self.workspace,
        )
        self._worker.signals.complete.connect(self._download_complete)
        self._worker.signals.failed.connect(self._download_failed)
        self._worker.signals.progress.connect(self.progress.report)
        self._worker.signals.phase.connect(self._download_phase)
        start_background(self._worker)

    @Slot(str, bool)
    def _download_phase(self, message: str, determinate: bool) -> None:
        self.status.setText(message)
        self.status.setObjectName("Muted")
        self.progress.begin(determinate=determinate)

    @Slot(str)
    def _download_complete(self, message: str) -> None:
        manual = ", ".join(item.name for item in self.provision_plan.manual)
        suffix = (
            f"\nManual requirements still need attention: {manual}."
            if manual
            else "\nROMVERSE refreshed the tool inventory automatically."
        )
        self.status.setText(message + suffix)
        self.status.setObjectName("Good")
        self._worker = None
        self.progress.finish()
        self.install_button.setEnabled(True)
        self.install_button.setText("Install and verify requirements")
        close_button = self.buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_button is not None:
            close_button.setEnabled(True)
        for name, check in self.checks.items():
            check.setEnabled(self.items_by_name[name].strategy is not ProvisionStrategy.MANUAL)
        parent = self.parentWidget()
        if isinstance(parent, ToolchainCenter):
            parent.refresh()
        self.last_success = True
        self.last_message = message + suffix
        self.completed.emit(True, self.last_message)
        if self.auto_close:
            self.accept()

    @Slot(str)
    def _download_failed(self, message: str) -> None:
        self.status.setText(message)
        self.status.setObjectName("Danger")
        self.progress.stop()
        self._worker = None
        self.install_button.setEnabled(True)
        self.install_button.setText("Install and verify requirements")
        close_button = self.buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_button is not None:
            close_button.setEnabled(True)
        for name, check in self.checks.items():
            check.setEnabled(self.items_by_name[name].strategy is not ProvisionStrategy.MANUAL)
        self.last_success = False
        self.last_message = message
        self.completed.emit(False, message)
