from __future__ import annotations

import hashlib
import io
import json
import os
import tarfile
from pathlib import Path

import pytest

from romverse.infrastructure.payload_dumper import (
    PayloadDumperRelease,
    install_payload_dumper_release,
    resolve_latest_payload_dumper,
)
from romverse.ui.toolchain_center import verified_managed_directories


class _Response:
    def __init__(self, payload: bytes) -> None:
        self.stream = io.BytesIO(payload)
        self.headers = {"Content-Length": str(len(payload))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, limit: int) -> bytes:
        return self.stream.read(limit)


def _release_metadata(archive_digest: str, *, url: str | None = None) -> bytes:
    name = "payload-dumper-go_2.0.2_linux_amd64.tar.gz"
    return json.dumps(
        {
            "tag_name": "2.0.2",
            "assets": [
                {
                    "name": name,
                    "browser_download_url": url
                    or f"https://github.com/ssut/payload-dumper-go/releases/download/2.0.2/{name}",
                    "digest": f"sha256:{archive_digest}",
                }
            ],
        }
    ).encode()


def _archive(*, unsafe_name: str | None = None, symlink: bool = False) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        name = unsafe_name or ("payload-dumper-go.exe" if os.name == "nt" else "payload-dumper-go")
        info = tarfile.TarInfo(name)
        if symlink:
            info.type = tarfile.SYMTYPE
            info.linkname = "/tmp/evil"
            archive.addfile(info)
        else:
            payload = b"payload dumper executable"
            info.mode = 0o755
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
        readme = tarfile.TarInfo("README.md")
        readme_payload = b"official release"
        readme.size = len(readme_payload)
        archive.addfile(readme, io.BytesIO(readme_payload))
    return output.getvalue()


def test_resolver_selects_official_digest_bound_linux_asset() -> None:
    archive = _archive()
    digest = hashlib.sha256(archive).hexdigest()

    release = resolve_latest_payload_dumper(
        "Linux",
        machine="x86_64",
        opener=lambda _request, timeout: _Response(_release_metadata(digest)),
    )

    assert release.version == "2.0.2"
    assert release.asset_name == "payload-dumper-go_2.0.2_linux_amd64.tar.gz"
    assert release.archive_sha256 == digest


def test_resolver_rejects_non_official_asset_url() -> None:
    digest = "a" * 64
    with pytest.raises(ValueError, match="approved official asset"):
        resolve_latest_payload_dumper(
            "Linux",
            machine="amd64",
            opener=lambda _request, timeout: _Response(
                _release_metadata(digest, url="https://example.com/payload.tar.gz")
            ),
        )


def test_installer_hashes_extracts_and_activates_managed_tool(tmp_path: Path) -> None:
    archive = _archive()
    digest = hashlib.sha256(archive).hexdigest()
    release = PayloadDumperRelease(
        "2.0.2",
        "payload-dumper-go_2.0.2_linux_amd64.tar.gz",
        "https://github.com/ssut/payload-dumper-go/releases/download/2.0.2/payload-dumper-go_2.0.2_linux_amd64.tar.gz",
        digest,
    )
    progress = []

    executable, binary_digest = install_payload_dumper_release(
        release,
        tmp_path,
        opener=lambda _url, timeout: _Response(archive),
        progress=lambda done, total: progress.append((done, total)),
    )

    assert executable.read_bytes() == b"payload dumper executable"
    if os.name != "nt":
        assert executable.stat().st_mode & 0o111
    receipt = json.loads((executable.parent / "managed-tool.romverse").read_text())
    assert receipt["version"] == "2.0.2"
    assert receipt["sha256"] == binary_digest
    if os.name != "nt":
        assert executable.parent.stat().st_mode & 0o077 == 0
        assert executable.stat().st_mode & 0o077 == 0
        assert (executable.parent / "managed-tool.romverse").stat().st_mode & 0o077 == 0
    assert verified_managed_directories(tmp_path) == (executable.parent,)
    assert progress == [(0, len(archive)), (len(archive), len(archive)), (0, 0)]


@pytest.mark.parametrize(
    ("unsafe_name", "symlink"),
    (("../payload-dumper-go", False), (None, True)),
)
def test_installer_rejects_unsafe_archive_members(
    tmp_path: Path, unsafe_name: str | None, symlink: bool
) -> None:
    archive = _archive(unsafe_name=unsafe_name, symlink=symlink)
    release = PayloadDumperRelease(
        "2.0.2",
        "payload-dumper-go_2.0.2_linux_amd64.tar.gz",
        "https://github.com/ssut/payload-dumper-go/releases/download/2.0.2/payload-dumper-go_2.0.2_linux_amd64.tar.gz",
        hashlib.sha256(archive).hexdigest(),
    )

    with pytest.raises(ValueError, match="unsafe member"):
        install_payload_dumper_release(
            release, tmp_path, opener=lambda _url, timeout: _Response(archive)
        )
    assert not (tmp_path / "payload-dumper-go").exists()


def test_installer_preserves_existing_tool_on_digest_failure(tmp_path: Path) -> None:
    existing = tmp_path / "payload-dumper-go"
    existing.mkdir()
    (existing / "keep.txt").write_text("preserved", encoding="utf-8")
    archive = _archive()
    release = PayloadDumperRelease(
        "2.0.2",
        "payload-dumper-go_2.0.2_linux_amd64.tar.gz",
        "https://github.com/ssut/payload-dumper-go/releases/download/2.0.2/payload-dumper-go_2.0.2_linux_amd64.tar.gz",
        "0" * 64,
    )

    with pytest.raises(ValueError, match="does not match"):
        install_payload_dumper_release(
            release, tmp_path, opener=lambda _url, timeout: _Response(archive)
        )
    assert (existing / "keep.txt").read_text(encoding="utf-8") == "preserved"
