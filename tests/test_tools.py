import hashlib
import json
from pathlib import Path

from romverse.infrastructure.process import CommandResult
from romverse.infrastructure.tools import ToolVerifier


class Host:
    name = "test"

    def find_tool(self, name):
        return Path("/opt/adb") if name == "adb" else None


class Runner:
    def run(self, args, timeout=10):
        return CommandResult(tuple(args), 0, "Android Debug Bridge version 1.0.41\n", "")


def test_tool_verifier_reads_adb_version():
    statuses = ToolVerifier(Host(), Runner()).verify()
    adb = next(status for status in statuses if status.name == "ADB")
    assert adb.available
    assert adb.version == "1.0.41"


def test_extended_verifier_uses_each_tools_real_version_interface(monkeypatch, tmp_path):
    tools = tmp_path / "tools"
    tools.mkdir()
    for name in (
        "fastboot",
        "adb",
        "git",
        "7z",
        "unzip",
        "lz4",
        "simg2img",
        "debugfs",
        "avbtool",
        "payload-dumper-go",
        "make",
        "java",
        "mkfs.erofs",
        "fsck.erofs",
        "lpmake",
        "lpunpack",
        "lpdumps",
        "fakeroot",
        "aapt2",
        "apksigner",
    ):
        (tools / name).write_text("", encoding="utf-8")
    monkeypatch.setenv("PATH", str(tools))

    class ExtendedHost:
        name = "Linux"

        def find_tool(self, name):
            return tools / name if (tools / name).exists() else None

    class ExtendedRunner:
        def run(self, args, timeout=10):
            command = Path(args[0]).name
            expected = {
                "adb": ("version",),
                "fastboot": ("--version",),
                "git": ("--version",),
                "7z": ("i",),
                "unzip": ("-v",),
                "lz4": ("--version",),
                "simg2img": (),
                "debugfs": ("-V",),
                "avbtool": ("version",),
                "payload-dumper-go": ("-h",),
                "make": ("--version",),
                "java": ("--version",),
                "mkfs.erofs": ("--version",),
                "fsck.erofs": ("--version",),
                "lpmake": ("--help",),
                "lpunpack": (),
                "lpdumps": ("--help",),
                "fakeroot": ("-v",),
                "aapt2": ("version",),
                "apksigner": ("version",),
            }[command]
            assert tuple(args[1:]) == expected
            code = 1 if command == "simg2img" else 64 if command in {"lpmake", "lpunpack"} else 0
            output = (
                "Android Debug Bridge version 1.0.41"
                if command == "adb"
                else f"{command} available"
            )
            return CommandResult(tuple(args), code, output, "")

    statuses = ToolVerifier(ExtendedHost(), ExtendedRunner()).verify_extended()

    assert all(status.available for status in statuses)
    assert next(status for status in statuses if status.name == "7-Zip").version == "7z available"
    assert next(status for status in statuses if status.name == "Payload Dumper").available
    assert next(status for status in statuses if status.name == "EROFS Builder").available
    assert next(status for status in statuses if status.name == "LP Make").available
    assert next(status for status in statuses if status.name == "APK Signer").available


def test_extended_verifier_skips_broken_shadowing_binary(monkeypatch, tmp_path):
    broken = tmp_path / "broken"
    good = tmp_path / "good"
    broken.mkdir()
    good.mkdir()
    for root in (broken, good):
        (root / "simg2img").write_text("", encoding="utf-8")
    monkeypatch.setenv("PATH", f"{broken}:{good}")

    class CandidateHost:
        name = "Linux"

        def find_tool(self, name):
            return broken / name if name == "simg2img" else None

    class CandidateRunner:
        def run(self, args, timeout=10):
            path = Path(args[0])
            if path.parent == broken:
                return CommandResult(tuple(args), 127, "", "missing shared library")
            return CommandResult(tuple(args), 1, "Usage: simg2img input output", "")

    statuses = ToolVerifier(CandidateHost(), CandidateRunner()).verify_extended()
    simg2img = next(status for status in statuses if status.name == "simg2img")

    assert simg2img.available
    assert simg2img.path == str(good / "simg2img")


def test_extended_verifier_uses_hash_bound_managed_version(monkeypatch, tmp_path):
    executable = tmp_path / "payload-dumper-go"
    executable.write_bytes(b"verified payload dumper")
    receipt = {
        "format": "romverse.managed-tool",
        "schema_version": 1,
        "name": "Payload Dumper",
        "version": "2.0.2",
        "executable": executable.name,
        "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
    }
    executable.with_name(executable.name + ".romverse").write_text(
        json.dumps(receipt), encoding="utf-8"
    )
    monkeypatch.setenv("PATH", str(tmp_path))

    class ManagedHost:
        name = "Linux"

        def find_tool(self, name):
            return executable if name == "payload-dumper-go" else None

    class ManagedRunner:
        def run(self, args, timeout=10):
            if Path(args[0]) == executable:
                return CommandResult(tuple(args), 0, "Usage of payload-dumper-go", "")
            return CommandResult(tuple(args), 127, "", "unavailable")

    statuses = ToolVerifier(ManagedHost(), ManagedRunner()).verify_extended()
    payload = next(status for status in statuses if status.name == "Payload Dumper")

    assert payload.available
    assert payload.version == "2.0.2"

    executable.write_bytes(b"tampered")
    statuses = ToolVerifier(ManagedHost(), ManagedRunner()).verify_extended()
    payload = next(status for status in statuses if status.name == "Payload Dumper")
    assert payload.version == "Usage of payload-dumper-go"
