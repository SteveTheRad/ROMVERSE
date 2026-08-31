from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import tarfile
import tempfile
import urllib.parse
import urllib.request
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from romverse.infrastructure.local_store import atomic_write_json, ensure_private_directory


@dataclass(frozen=True, slots=True)
class PayloadDumperRelease:
    version: str
    asset_name: str
    url: str
    archive_sha256: str


LATEST_RELEASE_API = "https://api.github.com/repos/ssut/payload-dumper-go/releases/latest"
MAX_RELEASE_METADATA_BYTES = 2 * 1024 * 1024
MAX_ARCHIVE_BYTES = 250 * 1024 * 1024
MAX_EXPANDED_BYTES = 1024 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 10_000
MAX_EXECUTABLE_BYTES = 250 * 1024 * 1024
DownloadProgress = Callable[[int, int], None]


def resolve_latest_payload_dumper(
    host_name: str,
    *,
    machine: str | None = None,
    opener=None,
) -> PayloadDumperRelease:
    """Resolve a host asset from GitHub's official, digest-bearing release metadata."""

    operating_system = host_name.casefold()
    if operating_system not in {"linux", "windows"}:
        raise ValueError("Payload Dumper automatic setup supports Linux and Windows")
    architecture = (machine or platform.machine()).casefold()
    architecture = {
        "x86_64": "amd64",
        "x64": "amd64",
        "amd64": "amd64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }.get(architecture, "")
    if not architecture:
        raise ValueError("Payload Dumper has no supported release for this CPU architecture")

    open_url = opener or urllib.request.urlopen
    request = urllib.request.Request(
        LATEST_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "ROMVERSE/0.1",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with open_url(request, timeout=30) as response:
        encoded = response.read(MAX_RELEASE_METADATA_BYTES + 1)
    if len(encoded) > MAX_RELEASE_METADATA_BYTES:
        raise ValueError("Payload Dumper release metadata exceeds the safety limit")
    try:
        metadata = json.loads(encoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Payload Dumper release metadata is invalid") from exc
    version = str(metadata.get("tag_name", "")).strip()
    if not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z._-]{0,63}", version):
        raise ValueError("Payload Dumper release version is invalid")
    expected_name = f"payload-dumper-go_{version}_{operating_system}_{architecture}.tar.gz"
    assets = metadata.get("assets")
    if not isinstance(assets, list):
        raise ValueError("Payload Dumper release has no asset list")
    asset = next(
        (
            value
            for value in assets
            if isinstance(value, dict) and value.get("name") == expected_name
        ),
        None,
    )
    if asset is None:
        raise ValueError(f"Official release does not contain {expected_name}")
    url = str(asset.get("browser_download_url", ""))
    parsed = urllib.parse.urlsplit(url)
    expected_prefix = f"/ssut/payload-dumper-go/releases/download/{version}/"
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or not parsed.path.startswith(expected_prefix)
        or PurePosixPath(parsed.path).name != expected_name
    ):
        raise ValueError("Payload Dumper release URL is not an approved official asset")
    digest = str(asset.get("digest", ""))
    if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
        raise ValueError("Official Payload Dumper asset has no valid SHA-256 digest")
    return PayloadDumperRelease(version, expected_name, url, digest.split(":", 1)[1].lower())


def install_payload_dumper_release(
    release: PayloadDumperRelease,
    destination: Path,
    *,
    opener=None,
    boundary: Path | None = None,
    progress: DownloadProgress | None = None,
) -> tuple[Path, str]:
    """Download, verify, safely extract, and atomically activate Payload Dumper."""

    open_url = opener or urllib.request.urlopen
    trust_boundary = Path(os.path.abspath(boundary or destination.parent))
    if boundary is None:
        while not trust_boundary.exists() and trust_boundary != trust_boundary.parent:
            trust_boundary = trust_boundary.parent
    ensure_private_directory(destination, boundary=trust_boundary)
    partial_descriptor, partial_name = tempfile.mkstemp(
        prefix=".payload-dumper-go.", suffix=".tar.gz.part", dir=destination
    )
    partial = Path(partial_name)
    staging = destination / ".payload-dumper-go.extracting"
    target = destination / "payload-dumper-go"
    previous = destination / ".payload-dumper-go.previous"
    digest = hashlib.sha256()
    total = 0
    try:
        with (
            os.fdopen(partial_descriptor, "wb", closefd=True) as output,
            open_url(release.url, timeout=90) as response,
        ):
            expected_bytes = _response_content_length(response)
            if progress is not None:
                progress(0, expected_bytes)
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_ARCHIVE_BYTES:
                    raise ValueError("Payload Dumper archive exceeds the download safety limit")
                digest.update(chunk)
                output.write(chunk)
                if progress is not None:
                    progress(total, expected_bytes)
            output.flush()
            os.fsync(output.fileno())
        if progress is not None:
            progress(0, 0)
        if digest.hexdigest() != release.archive_sha256:
            raise ValueError("Payload Dumper archive SHA-256 does not match GitHub metadata")

        with suppress(OSError):
            shutil.rmtree(staging)
        ensure_private_directory(staging, boundary=trust_boundary)
        with tarfile.open(partial, "r:gz") as archive:
            members = archive.getmembers()
            if len(members) > MAX_ARCHIVE_ENTRIES:
                raise ValueError("Payload Dumper archive contains too many entries")
            expanded = 0
            candidates: list[tarfile.TarInfo] = []
            expected_binary = "payload-dumper-go.exe" if os.name == "nt" else "payload-dumper-go"
            for member in members:
                relative = PurePosixPath(member.name)
                if (
                    not member.name
                    or "\\" in member.name
                    or relative.is_absolute()
                    or ".." in relative.parts
                    or member.issym()
                    or member.islnk()
                    or member.isdev()
                    or not (member.isfile() or member.isdir())
                ):
                    raise ValueError("Payload Dumper archive contains an unsafe member")
                if member.isfile():
                    expanded += member.size
                    if expanded > MAX_EXPANDED_BYTES:
                        raise ValueError("Payload Dumper archive exceeds the expanded-size limit")
                    if relative.name == expected_binary:
                        candidates.append(member)
            if len(candidates) != 1 or candidates[0].size > MAX_EXECUTABLE_BYTES:
                raise ValueError("Payload Dumper archive has no unique bounded executable")
            source = archive.extractfile(candidates[0])
            if source is None:
                raise ValueError("Payload Dumper executable could not be read")
            executable = staging / expected_binary
            binary_digest = hashlib.sha256()
            copied = 0
            with source, executable.open("wb") as output:
                while chunk := source.read(1024 * 1024):
                    copied += len(chunk)
                    if copied > MAX_EXECUTABLE_BYTES:
                        raise ValueError("Payload Dumper executable exceeds the safety limit")
                    binary_digest.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            if copied != candidates[0].size:
                raise ValueError("Payload Dumper executable size is inconsistent")
            executable.chmod(0o700)

        receipt = {
            "format": "romverse.managed-tool",
            "schema_version": 1,
            "name": "Payload Dumper",
            "version": release.version,
            "source": release.url,
            "source_archive_sha256": release.archive_sha256,
            "sha256": binary_digest.hexdigest(),
            "executable": expected_binary,
        }
        atomic_write_json(
            staging / "managed-tool.romverse",
            receipt,
            boundary=trust_boundary,
            maximum_bytes=64 * 1024,
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
        return target / expected_binary, binary_digest.hexdigest()
    finally:
        partial.unlink(missing_ok=True)
        with suppress(OSError):
            shutil.rmtree(staging)


def _response_content_length(response: object) -> int:
    headers = getattr(response, "headers", None)
    if headers is None:
        return 0
    try:
        value = int(headers.get("Content-Length", "0"))
    except (AttributeError, TypeError, ValueError):
        return 0
    return value if 0 < value <= MAX_ARCHIVE_BYTES else 0
