import base64
import hashlib
import io
import json
import os
import zipfile

import pytest

import romverse.infrastructure.android_apk_tools as android_apk_tools
import romverse.ui.toolchain_center as toolchain_center
from romverse.infrastructure.android_apk_tools import (
    AAPT2_PACKAGE_DIRECTORY,
    APK_VERIFIER_PACKAGE_DIRECTORY,
    install_pinned_aapt2,
    install_pinned_apk_verifier,
)
from romverse.ui.toolchain_center import (
    activate_verified_managed_tools,
    install_official_archive,
    install_official_avbtool,
    install_pinned_partition_tools,
    verified_managed_directories,
)


class _Response:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.headers = {"Content-Length": str(len(payload))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, limit: int):
        return self.payload[:limit]


def test_managed_avbtool_install_validates_hashes_and_records_source(tmp_path):
    source = b"#!/usr/bin/env python3\nclass AvbTool:\n    pass\n"
    progress = []

    def opener(_url, timeout):
        assert timeout == 90
        return _Response(base64.b64encode(source))

    executable, digest = install_official_avbtool(
        tmp_path, opener, progress=lambda done, total: progress.append((done, total))
    )

    assert executable.read_bytes() == source
    if os.name != "nt":
        assert executable.stat().st_mode & 0o111
    assert digest == hashlib.sha256(source).hexdigest()
    receipt = json.loads(
        (tmp_path / "avbtool" / "managed-tool.romverse").read_text(encoding="utf-8")
    )
    assert receipt["sha256"] == digest
    assert "android.googlesource.com" in receipt["source"]
    if os.name != "nt":
        assert executable.parent.stat().st_mode & 0o077 == 0
        assert executable.stat().st_mode & 0o077 == 0
        assert (executable.parent / "managed-tool.romverse").stat().st_mode & 0o077 == 0
    assert progress == [(len(base64.b64encode(source)), len(base64.b64encode(source))), (0, 0)]


def test_verified_managed_tool_is_activated_once_and_tamper_fails_closed(
    tmp_path,
    monkeypatch,
):
    source = b"#!/usr/bin/env python3\nclass AvbTool:\n    pass\n"
    executable, _digest = install_official_avbtool(
        tmp_path / "workspace" / "tools" / "downloads",
        lambda _url, timeout: _Response(base64.b64encode(source)),
    )
    monkeypatch.setenv("PATH", "/usr/bin")

    first = activate_verified_managed_tools(tmp_path / "workspace")
    second = activate_verified_managed_tools(tmp_path / "workspace")

    assert first == (executable.parent,)
    assert second == first
    assert os.environ["PATH"].split(os.pathsep).count(str(executable.parent)) == 1

    executable.write_bytes(b"tampered")
    assert activate_verified_managed_tools(tmp_path / "workspace") == ()
    assert str(executable.parent) not in os.environ["PATH"].split(os.pathsep)


def test_managed_avbtool_rejects_unexpected_download(tmp_path):
    def opener(_url, timeout):
        return _Response(base64.b64encode(b"not an avbtool script"))

    with pytest.raises(ValueError, match="structural validation"):
        install_official_avbtool(tmp_path, opener)
    assert not (tmp_path / "avbtool" / "avbtool").exists()


def test_managed_avbtool_rejects_redirected_destination(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace / "downloads").symlink_to(outside, target_is_directory=True)
    source = b"#!/usr/bin/env python3\nclass AvbTool:\n    pass\n"

    with pytest.raises(OSError, match="unsafe or unavailable"):
        install_official_avbtool(
            workspace / "downloads",
            lambda _url, timeout: _Response(base64.b64encode(source)),
            boundary=workspace,
        )

    assert not (outside / "avbtool").exists()


class _StreamingResponse:
    def __init__(self, payload: bytes):
        self.stream = io.BytesIO(payload)
        self.headers = {"Content-Length": str(len(payload))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, limit: int):
        return self.stream.read(limit)


def _platform_tools_zip() -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as package:
        package.writestr("platform-tools/adb", b"verified adb")
        package.writestr("platform-tools/fastboot", b"verified fastboot")
    return stream.getvalue()


def _aapt2_jar() -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as package:
        package.writestr("META-INF/", b"")
        package.writestr("META-INF/MANIFEST.MF", b"Manifest-Version: 1.0\n")
        package.writestr("aapt2", b"\x7fELF verified AAPT2 fixture")
        package.writestr("NOTICE", b"Apache License 2.0 fixture")
    return stream.getvalue()


def _apksig_jar() -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as package:
        package.writestr("LICENSE", b"Apache License 2.0 fixture")
        package.writestr("com/android/apksig/ApkVerifier.class", b"verifier")
        package.writestr("com/android/apksig/ApkVerifier$Builder.class", b"builder")
        package.writestr("com/android/apksig/ApkVerifier$Result.class", b"result")
    return stream.getvalue()


def test_pinned_google_maven_aapt2_install_is_receipted_and_tamper_closes(
    tmp_path,
    monkeypatch,
):
    payload = _aapt2_jar()
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(android_apk_tools, "AAPT2_ARCHIVE_SHA256", digest)
    monkeypatch.setattr(toolchain_center, "AAPT2_ARCHIVE_SHA256", digest)

    executable, archive_digest = install_pinned_aapt2(
        tmp_path,
        lambda _url, timeout: _StreamingResponse(payload),
    )

    installed = tmp_path / AAPT2_PACKAGE_DIRECTORY
    receipt = json.loads((installed / "managed-package.romverse").read_text())
    assert archive_digest == digest
    assert executable.read_bytes().startswith(b"\x7fELF")
    if os.name != "nt":
        assert executable.stat().st_mode & 0o111
    assert receipt["archive_sha256"] == digest
    assert receipt["license"] == "Apache-2.0"
    assert set(receipt["files"]) == {"aapt2", "NOTICE", "aapt2.romverse"}
    assert verified_managed_directories(tmp_path) == (installed,)

    executable.write_bytes(b"tampered")
    assert verified_managed_directories(tmp_path) == ()


def test_pinned_official_apksig_verifier_is_bounded_and_verification_only(
    tmp_path,
    monkeypatch,
):
    payload = _apksig_jar()
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(android_apk_tools, "APKSIG_ARCHIVE_SHA256", digest)
    monkeypatch.setattr(toolchain_center, "APKSIG_ARCHIVE_SHA256", digest)

    launcher, artifact_digest = install_pinned_apk_verifier(
        tmp_path,
        lambda _url, timeout: _StreamingResponse(payload),
    )

    installed = tmp_path / APK_VERIFIER_PACKAGE_DIRECTORY
    receipt = json.loads((installed / "managed-package.romverse").read_text())
    assert artifact_digest == digest
    if os.name != "nt":
        assert launcher.stat().st_mode & 0o111
    assert b"os.execvp" in launcher.read_bytes()
    assert receipt["artifact_sha256"] == digest
    assert receipt["capability"] == "verification-only"
    assert receipt["license"] == "Apache-2.0"
    assert verified_managed_directories(tmp_path) == (installed,)

    (installed / "RomverseApkVerifier.java").write_text("tampered", encoding="utf-8")
    assert verified_managed_directories(tmp_path) == ()


def test_pinned_google_maven_digest_failure_preserves_previous_install(
    tmp_path,
    monkeypatch,
):
    installed = tmp_path / AAPT2_PACKAGE_DIRECTORY
    installed.mkdir()
    (installed / "keep.txt").write_text("known good", encoding="utf-8")
    monkeypatch.setattr(android_apk_tools, "AAPT2_ARCHIVE_SHA256", "0" * 64)

    with pytest.raises(ValueError, match="pinned SHA-256"):
        install_pinned_aapt2(
            tmp_path,
            lambda _url, timeout: _StreamingResponse(_aapt2_jar()),
        )

    assert (installed / "keep.txt").read_text(encoding="utf-8") == "known good"


def test_official_archive_is_content_addressed_and_only_activates_while_unchanged(tmp_path):
    payload = _platform_tools_zip()
    progress = []

    def opener(_url, timeout):
        assert timeout == 90
        return _StreamingResponse(payload)

    installed, digest = install_official_archive(
        "platform-tools",
        "https://dl.google.com/android/repository/platform-tools-latest-linux.zip",
        tmp_path,
        ("adb", "fastboot"),
        opener,
        progress=lambda done, total: progress.append((done, total)),
    )

    assert digest == hashlib.sha256(payload).hexdigest()
    receipt = json.loads((installed / "managed-package.romverse").read_text())
    assert receipt["archive_sha256"] == digest
    assert verified_managed_directories(tmp_path) == (installed / "platform-tools",)
    if os.name != "nt":
        assert installed.stat().st_mode & 0o077 == 0
        assert (installed / "managed-package.romverse").stat().st_mode & 0o077 == 0
    assert progress == [(0, len(payload)), (len(payload), len(payload)), (0, 0)]

    (installed / "platform-tools" / "adb").write_bytes(b"tampered")
    assert verified_managed_directories(tmp_path) == ()


def test_official_archive_rejects_path_traversal_without_replacing_existing(tmp_path):
    existing = tmp_path / "platform-tools"
    existing.mkdir()
    (existing / "keep.txt").write_text("preserve me")
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as package:
        package.writestr("../escape", b"unsafe")

    with pytest.raises(ValueError, match="unsafe path"):
        install_official_archive(
            "platform-tools",
            "https://dl.google.com/android/repository/platform-tools.zip",
            tmp_path,
            ("adb", "fastboot"),
            lambda _url, timeout: _StreamingResponse(stream.getvalue()),
        )

    assert (existing / "keep.txt").read_text() == "preserve me"
    assert not (tmp_path / "escape").exists()


def test_official_archive_rejects_ambiguous_required_binary(tmp_path):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as package:
        package.writestr("platform-tools/adb", b"first adb")
        package.writestr("platform-tools/nested/adb", b"second adb")
        package.writestr("platform-tools/fastboot", b"fastboot")

    with pytest.raises(ValueError, match="one required file: adb"):
        install_official_archive(
            "platform-tools",
            "https://dl.google.com/android/repository/platform-tools-latest-linux.zip",
            tmp_path,
            ("adb", "fastboot"),
            lambda _url, timeout: _StreamingResponse(stream.getvalue()),
        )

    assert not (tmp_path / "platform-tools").exists()


def test_partition_tools_install_is_commit_and_hash_pinned(tmp_path):
    payloads = {
        "lpmake": b"pinned lpmake",
        "lpunpack": b"pinned lpunpack",
        "lpdumps": b"pinned lpdumps",
        "simg2img": b"pinned simg2img",
    }
    expected = {name: hashlib.sha256(value).hexdigest() for name, value in payloads.items()}
    progress = []

    def opener(url, timeout):
        assert timeout == 90
        assert "/0123456789abcdef0123456789abcdef01234567/linux_glibc_x86_64/" in url
        return _StreamingResponse(payloads[url.rsplit("/", 1)[-1]])

    installed, hashes = install_pinned_partition_tools(
        "Linux",
        tmp_path,
        opener,
        commit="0123456789abcdef0123456789abcdef01234567",
        expected_files=expected,
        progress=lambda done, total: progress.append((done, total)),
    )

    assert hashes == expected
    receipt = json.loads((installed / "managed-package.romverse").read_text())
    assert receipt["commit"] == "0123456789abcdef0123456789abcdef01234567"
    assert "third-party publisher" in receipt["provenance"]
    assert verified_managed_directories(tmp_path) == (installed,)
    assert progress == [(index, 4) for index in range(5)]

    (installed / "lpmake").write_bytes(b"tampered")
    assert verified_managed_directories(tmp_path) == ()


def test_partition_tools_digest_failure_preserves_previous_install(tmp_path):
    existing = tmp_path / "aosp-partition-tools"
    existing.mkdir()
    (existing / "keep.txt").write_text("known good", encoding="utf-8")

    with pytest.raises(ValueError, match="pinned SHA-256"):
        install_pinned_partition_tools(
            "Linux",
            tmp_path,
            lambda _url, timeout: _StreamingResponse(b"unexpected"),
            commit="0123456789abcdef0123456789abcdef01234567",
            expected_files={"lpmake": "0" * 64},
        )

    assert (existing / "keep.txt").read_text(encoding="utf-8") == "known good"


def test_tampered_receipt_cannot_activate_a_file_outside_its_package(tmp_path):
    outside = tmp_path / "outside-tool"
    outside.write_bytes(b"real file, wrong trust boundary")
    package = tmp_path / "managed"
    package.mkdir()
    (package / "managed-package.romverse").write_text(
        json.dumps(
            {
                "format": "romverse.managed-package",
                "files": {"../outside-tool": hashlib.sha256(outside.read_bytes()).hexdigest()},
            }
        ),
        encoding="utf-8",
    )

    assert verified_managed_directories(tmp_path) == ()


@pytest.mark.parametrize(
    "mutation",
    (
        lambda receipt: receipt.update({"unexpected": "field"}),
        lambda receipt: receipt.update({"schema_version": True}),
        lambda receipt: receipt.update({"source": "https://example.com/avbtool"}),
    ),
)
def test_managed_tool_receipt_rejects_noncanonical_shape(tmp_path, mutation):
    source = b"#!/usr/bin/env python3\nclass AvbTool:\n    pass\n"
    executable, _digest = install_official_avbtool(
        tmp_path,
        lambda _url, timeout: _Response(base64.b64encode(source)),
    )
    receipt_path = executable.parent / "managed-tool.romverse"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    mutation(receipt)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    assert verified_managed_directories(tmp_path) == ()


def test_managed_tool_receipt_is_bound_to_its_canonical_directory(tmp_path):
    source = b"#!/usr/bin/env python3\nclass AvbTool:\n    pass\n"
    executable, _digest = install_official_avbtool(
        tmp_path,
        lambda _url, timeout: _Response(base64.b64encode(source)),
    )
    executable.parent.rename(tmp_path / "renamed-tool")

    assert verified_managed_directories(tmp_path) == ()


def test_managed_activation_rejects_redirected_downloads_directory(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    (workspace / "tools").mkdir(parents=True)
    outside = tmp_path / "outside"
    source = b"#!/usr/bin/env python3\nclass AvbTool:\n    pass\n"
    install_official_avbtool(
        outside,
        lambda _url, timeout: _Response(base64.b64encode(source)),
    )
    (workspace / "tools" / "downloads").symlink_to(outside, target_is_directory=True)
    monkeypatch.setenv("PATH", "/usr/bin")

    assert activate_verified_managed_tools(workspace) == ()
    assert __import__("os").environ["PATH"] == "/usr/bin"


def test_managed_activation_rejects_linked_package_directory(tmp_path):
    outside = tmp_path / "outside"
    source = b"#!/usr/bin/env python3\nclass AvbTool:\n    pass\n"
    executable, _digest = install_official_avbtool(
        outside,
        lambda _url, timeout: _Response(base64.b64encode(source)),
    )
    root = tmp_path / "managed-root"
    root.mkdir()
    (root / "avbtool").symlink_to(executable.parent, target_is_directory=True)

    assert verified_managed_directories(root) == ()


def test_managed_activation_fails_closed_on_candidate_flood(tmp_path):
    source = b"#!/usr/bin/env python3\nclass AvbTool:\n    pass\n"
    install_official_avbtool(
        tmp_path,
        lambda _url, timeout: _Response(base64.b64encode(source)),
    )
    for index in range(32):
        (tmp_path / f"decoy-{index:02d}").mkdir()

    assert verified_managed_directories(tmp_path) == ()


def test_resealed_package_cannot_activate_unapproved_file_set(tmp_path):
    package = tmp_path / "platform-tools"
    package.mkdir()
    executable = package / "unexpected-tool"
    executable.write_bytes(b"unexpected")
    receipt = {
        "format": "romverse.managed-package",
        "schema_version": 1,
        "name": "platform-tools",
        "source": "https://dl.google.com/android/repository/platform-tools-latest-linux.zip",
        "archive_sha256": "a" * 64,
        "archive_bytes": 10,
        "files": {executable.name: hashlib.sha256(executable.read_bytes()).hexdigest()},
    }
    (package / "managed-package.romverse").write_text(json.dumps(receipt), encoding="utf-8")

    assert verified_managed_directories(tmp_path) == ()
