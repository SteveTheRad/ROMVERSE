from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from romverse.infrastructure.process import CommandRunner
from romverse.platform.host import HostPlatform


@dataclass(frozen=True, slots=True)
class ToolStatus:
    name: str
    available: bool
    path: str = ""
    version: str = ""
    detail: str = ""


class ToolVerifier:
    MAXIMUM_SDK_ROOTS = 8
    MAXIMUM_BUILD_TOOL_REVISIONS = 128

    def __init__(
        self,
        host: HostPlatform,
        runner: CommandRunner,
        *,
        sdk_roots: tuple[Path, ...] | None = None,
    ) -> None:
        self.host = host
        self.runner = runner
        self.sdk_roots = sdk_roots

    def verify(self) -> tuple[ToolStatus, ...]:
        python = ToolStatus("Python", True, sys.executable, sys.version.split()[0], "Ready")
        adb_path = self.host.find_tool("adb")
        if adb_path is None:
            adb = ToolStatus(
                "ADB", False, detail="Install Android SDK Platform Tools and add adb to PATH"
            )
        else:
            result = self.runner.run((str(adb_path), "version"), timeout=5)
            output = result.stdout + "\n" + result.stderr
            release = re.search(
                r"(?im)^\s*Version\s+(\d+(?:\.\d+){2,3}(?:[-+][\w.\-]+)?)",
                output,
            )
            protocol = re.search(
                r"Android Debug Bridge version\s+([\w.\-]+)",
                output,
                re.IGNORECASE,
            )
            version = (
                f"{release.group(1)} (ADB protocol {protocol.group(1)})"
                if release is not None and protocol is not None
                else release.group(1)
                if release is not None
                else protocol.group(1)
                if protocol is not None
                else "unknown"
            )
            adb = ToolStatus(
                "ADB",
                result.ok,
                str(adb_path),
                version,
                "Ready" if result.ok else "ADB did not start correctly",
            )
        return python, adb

    def verify_extended(self) -> tuple[ToolStatus, ...]:
        """Verify the optional ROM/diagnostic toolchain without installing anything."""
        statuses = list(self.verify())
        requirements = (
            (
                "Fastboot",
                "fastboot",
                ("--version",),
                frozenset({0}),
                "Install Android SDK Platform Tools",
            ),
            ("Git", "git", ("--version",), frozenset({0}), "Install Git"),
            ("7-Zip", "7z", ("i",), frozenset({0}), "Install 7-Zip or p7zip"),
            ("Unzip", "unzip", ("-v",), frozenset({0}), "Install unzip"),
            ("LZ4", "lz4", ("--version",), frozenset({0}), "Install lz4"),
            ("simg2img", "simg2img", (), frozenset({0, 1}), "Install android-tools-fsutils"),
            (
                "EXT4 Browser",
                "debugfs",
                ("-V",),
                frozenset({0}),
                "Install e2fsprogs",
            ),
            (
                "AVBTool",
                "avbtool",
                ("version",),
                frozenset({0}),
                "Install the Android platform external/avb tool",
            ),
            (
                "Payload Dumper",
                "payload-dumper-go",
                ("-h",),
                frozenset({0}),
                "Install payload-dumper-go",
            ),
            ("Make", "make", ("--version",), frozenset({0}), "Install build-essential / GNU Make"),
            ("Java", "java", ("--version",), frozenset({0}), "Install a supported JDK"),
            (
                "EROFS Builder",
                "mkfs.erofs",
                ("--version",),
                frozenset({0}),
                "Install erofs-utils",
            ),
            (
                "EROFS Verifier",
                "fsck.erofs",
                ("--version",),
                frozenset({0}),
                "Install erofs-utils",
            ),
            (
                "LP Make",
                "lpmake",
                ("--help",),
                frozenset({0, 64}),
                "Install verified Android logical-partition tools",
            ),
            (
                "LP Unpack",
                "lpunpack",
                (),
                frozenset({0, 64}),
                "Install verified Android logical-partition tools",
            ),
            (
                "LP Dump",
                "lpdumps|lpdump",
                ("--help",),
                frozenset({0}),
                "Install verified Android logical-partition tools",
            ),
            ("Fakeroot", "fakeroot", ("-v",), frozenset({0}), "Install fakeroot"),
            (
                "AAPT2",
                "aapt2",
                ("version",),
                frozenset({0}),
                "Use Forge Arsenal's pinned official AAPT2 or install Android SDK Build Tools 26.0.2+; ROMVERSE checks Android Studio SDK folders automatically",
            ),
            (
                "APK Signer",
                "apksigner",
                ("version",),
                frozenset({0}),
                "Use Forge Arsenal's official apksig verification capability, or install Android SDK Build Tools 24.0.3+ when APK signing is required",
            ),
        )
        if self.host.name.lower() == "windows":
            requirements += (
                (
                    "OEM USB Driver",
                    "androidwinusb.inf",
                    (),
                    frozenset({0}),
                    "Install the signed USB driver for the exact phone maker",
                ),
            )
        for name, executable, arguments, accepted_codes, hint in requirements:
            statuses.append(
                self._verify_extended_tool(name, executable, arguments, accepted_codes, hint)
            )
        return tuple(statuses)

    def _verify_extended_tool(
        self,
        name: str,
        executable: str,
        arguments: tuple[str, ...],
        accepted_codes: frozenset[int],
        hint: str,
    ) -> ToolStatus:
        failed_path = ""
        failed_detail = ""
        for path in self._tool_candidates(executable):
            result = self.runner.run((str(path), *arguments), timeout=5)
            lines = [
                line.strip()
                for line in (result.stdout + "\n" + result.stderr).splitlines()
                if line.strip()
            ]
            if not result.timed_out and result.returncode in accepted_codes:
                managed_version = self._managed_version(path, name)
                return ToolStatus(
                    name,
                    True,
                    str(path),
                    managed_version or (lines[0][:80] if lines else "available"),
                    (
                        "Ready for cryptographic APK verification; full SDK Build Tools remain required for signing"
                        if name == "APK Signer" and "verification-only" in managed_version
                        else "Ready"
                    ),
                )
            failed_path = str(path)
            failed_detail = lines[-1][:120] if lines else f"exit code {result.returncode}"
        if failed_path:
            return ToolStatus(
                name,
                False,
                failed_path,
                failed_detail,
                f"Found, but could not start correctly; {hint}",
            )
        return ToolStatus(name, False, detail=hint)

    @staticmethod
    def _managed_version(executable: Path, name: str) -> str:
        """Trust a managed version only while its sidecar still matches the executable."""

        candidates = (
            executable.with_name(executable.name + ".romverse"),
            executable.parent / "managed-tool.romverse",
        )
        for receipt_path in candidates:
            try:
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                if (
                    receipt.get("format") != "romverse.managed-tool"
                    or receipt.get("name") != name
                    or receipt.get("executable", executable.name) != executable.name
                ):
                    continue
                digest = hashlib.sha256()
                with executable.open("rb") as stream:
                    while chunk := stream.read(1024 * 1024):
                        digest.update(chunk)
                if digest.hexdigest() != receipt.get("sha256"):
                    continue
                version = str(receipt.get("version", "")).strip()
                if version:
                    return version[:80]
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
        return ""

    def _tool_candidates(self, executable: str) -> tuple[Path, ...]:
        candidates: list[Path] = []
        names = tuple(name for name in executable.split("|") if name)
        for name in names:
            configured = self.host.find_tool(name)
            if configured is not None and configured not in candidates:
                candidates.append(configured)
        suffixes = ("", ".exe") if self.host.name.lower() == "windows" else ("",)
        for directory in os.environ.get("PATH", "").split(os.pathsep):
            if not directory:
                continue
            for name in names:
                for suffix in suffixes:
                    path = Path(directory) / f"{name}{suffix}"
                    if path.is_file() and path not in candidates:
                        candidates.append(path)
        for name in names:
            if name not in {"aapt2", "apksigner"}:
                continue
            for path in self._android_sdk_tool_candidates(name):
                if path not in candidates:
                    candidates.append(path)
        return tuple(candidates)

    def _android_sdk_tool_candidates(self, executable: str) -> tuple[Path, ...]:
        """Find complete Android Studio Build Tools pairs without requiring PATH edits."""

        roots = self.sdk_roots
        if roots is None:
            roots = self._default_android_sdk_roots()
        candidates: list[tuple[tuple[object, ...], Path]] = []
        suffix = ".exe" if self.host.name.casefold() == "windows" else ""
        signer_names = (
            ("apksigner.bat", "apksigner.exe")
            if self.host.name.casefold() == "windows"
            else ("apksigner",)
        )
        for root_index, root in enumerate(roots[: self.MAXIMUM_SDK_ROOTS]):
            try:
                build_tools = (root / "build-tools").resolve(strict=True)
                revisions = tuple(build_tools.iterdir())
            except (OSError, RuntimeError):
                continue
            if len(revisions) > self.MAXIMUM_BUILD_TOOL_REVISIONS:
                continue
            for revision in revisions:
                if (
                    not revision.is_dir()
                    or revision.is_symlink()
                    or re.fullmatch(
                        r"[0-9]+(?:\.[0-9]+){1,3}(?:[-_.][A-Za-z0-9]+)*",
                        revision.name,
                    )
                    is None
                ):
                    continue
                try:
                    resolved = revision.resolve(strict=True)
                    resolved.relative_to(build_tools)
                except (OSError, RuntimeError, ValueError):
                    continue
                aapt = resolved / f"aapt2{suffix}"
                signer = next(
                    (resolved / name for name in signer_names if (resolved / name).is_file()),
                    None,
                )
                signer_jar = resolved / "lib" / "apksigner.jar"
                if (
                    not aapt.is_file()
                    or aapt.is_symlink()
                    or signer is None
                    or signer.is_symlink()
                    or not signer_jar.is_file()
                    or signer_jar.is_symlink()
                ):
                    continue
                selected = aapt if executable == "aapt2" else signer
                candidates.append(
                    (self._android_build_tools_revision_key(revision.name, root_index), selected)
                )
        candidates.sort(key=lambda item: item[0], reverse=True)
        return tuple(path for _key, path in candidates)

    def _default_android_sdk_roots(self) -> tuple[Path, ...]:
        roots: list[Path] = []
        for name in ("ANDROID_SDK_ROOT", "ANDROID_HOME"):
            raw = os.environ.get(name, "").strip()
            if raw and "\x00" not in raw:
                path = Path(raw).expanduser()
                if path.is_absolute() and path not in roots:
                    roots.append(path)
        if self.host.name.casefold() == "windows":
            local = os.environ.get("LOCALAPPDATA", "").strip()
            if local and "\x00" not in local:
                path = Path(local) / "Android" / "Sdk"
                if path not in roots:
                    roots.append(path)
            common = Path.home() / "AppData" / "Local" / "Android" / "Sdk"
        else:
            common = Path.home() / "Android" / "Sdk"
        if common not in roots:
            roots.append(common)
        return tuple(roots[: self.MAXIMUM_SDK_ROOTS])

    @staticmethod
    def _android_build_tools_revision_key(
        revision: str,
        root_index: int,
    ) -> tuple[object, ...]:
        numbers = tuple(int(value) for value in re.findall(r"[0-9]+", revision)[:4])
        stable = re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}", revision) is not None
        return stable, numbers, -root_index, revision
