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
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

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
from romverse.infrastructure.tools import ToolStatus, ToolVerifier
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
            os.fchmod(stream.fileno(), 0o700)
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
        self.body = QScrollArea()
        self.body.setWidgetResizable(True)
        self.content = QWidget()
        self.layout = QVBoxLayout(self.content)
        self.layout.setSpacing(10)
        self.body.setWidget(self.content)
        page.addWidget(self.body, 1)
        self._render()

    def refresh(self) -> None:
        self._verify_local_tools(emit=True)

    def _verify_local_tools(self, *, emit: bool) -> None:
        self._activate_managed_tools()
        self.statuses = ToolVerifier(self.host, self.runner).verify_extended()
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

    def open_device_pack_context(self, context: DevicePackToolchainContext) -> bool:
        """Open a validated, zero-authority view of one Pack's exact host requirements."""

        if not self._valid_device_pack_context(context):
            return False
        self._studio_project_context = None
        self._studio_project_context_stale = False
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
        self._studio_project_context = context
        self._studio_project_context_stale = False
        self.device_pack_handoff.setVisible(True)
        self._verify_local_tools(emit=False)
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
            and (
                not context.build_contract_bound
                or bool(context.device_pack_id and context.pack_sha256)
            )
        )

    def _render_studio_project_context(self) -> None:
        context = self._studio_project_context
        if context is None:
            return
        self.device_pack_handoff.setVisible(True)
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
        pack_copy = (
            f"Pack {context.device_pack_id} • SHA-256 {context.pack_sha256[:16]}… • exact build contract"
            if context.build_contract_bound
            else "No source-matched Device Pack build contract • structural/default tools only"
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
            if self._studio_project_context is None:
                self.device_pack_handoff.setVisible(False)
            return
        self.device_pack_handoff.setVisible(True)
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
        context = self._studio_project_context or self._device_pack_context
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
        summary = QLabel(f"{ready} of {len(ordered_statuses)} tools verified on {self.host.name}")
        summary.setObjectName("Good" if ready == len(ordered_statuses) else "Warning")
        self.layout.addWidget(summary)
        for status in ordered_statuses:
            card = QFrame()
            card.setObjectName("Card")
            row = QVBoxLayout(card)
            row.setContentsMargins(16, 12, 16, 12)
            top = QVBoxLayout()
            name_row = QHBoxLayout()
            name = QLabel(status.name)
            name.setObjectName("SectionTitle")
            name_row.addWidget(name)
            if status.name in required:
                required_badge = QLabel(
                    "EXACT PROJECT REQUIREMENT"
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
        if self._studio_project_context is not None:
            self._render_studio_project_context()
        else:
            self._render_device_pack_context()

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
        if self.host.name.lower() == "windows" and "Google USB Driver" in self.selected:
            packages["google-usb-driver"] = (
                "https://dl.google.com/android/repository/latest_usb_driver_windows.zip",
                ("android_winusb.inf",),
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
