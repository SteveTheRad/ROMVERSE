#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path

APP_PACKAGE = "com.radforge.romverse.companion"
TEST_PACKAGE = f"{APP_PACKAGE}.test"
RUNNER = f"{TEST_PACKAGE}/androidx.test.runner.AndroidJUnitRunner"
TEST_CLASS = "com.radforge.romverse.companion.CompanionUpgradeContinuityInstrumentedTest"
MAXIMUM_APK_BYTES = 256 * 1024 * 1024


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify a ROMVERSE Companion APK update preserves private app state. "
            "This runner refuses every non-emulator Android target."
        ),
    )
    parser.add_argument("--adb", required=True, type=Path)
    parser.add_argument("--previous-apk", required=True, type=Path)
    parser.add_argument("--current-apk", required=True, type=Path)
    parser.add_argument("--test-apk", required=True, type=Path)
    args = parser.parse_args()

    adb = regular_file(args.adb, "ADB", maximum_bytes=128 * 1024 * 1024)
    previous = regular_file(args.previous_apk, "previous APK")
    current = regular_file(args.current_apk, "current APK")
    test_apk = regular_file(args.test_apk, "instrumentation APK")
    previous_digest = sha256(previous)
    current_digest = sha256(current)
    if previous_digest == current_digest:
        raise SystemExit("Previous and current APKs are identical; no update was exercised")

    serial = require_single_emulator(adb)
    # Clearing package data is acceptable only after the qemu/emulator checks above. The runner
    # never accepts a physical device serial and never issues a phone command.
    run(adb, serial, "uninstall", TEST_PACKAGE, check=False)
    run(adb, serial, "uninstall", APP_PACKAGE, check=False)
    install(adb, serial, previous, replace=False)
    install(adb, serial, test_apk, replace=True)
    instrument(adb, serial, "seed")
    install(adb, serial, current, replace=True)
    instrument(adb, serial, "verify")

    print(
        "Companion update continuity passed on "
        f"{serial}: settings, activity, Galaxy, health history, pairing vault, and "
        "Lifeline evidence remained readable"
    )
    print(f"previous_sha256={previous_digest}")
    print(f"current_sha256={current_digest}")
    print("execution_authority=none")
    return 0


def regular_file(
    path: Path,
    label: str,
    *,
    maximum_bytes: int = MAXIMUM_APK_BYTES,
) -> Path:
    if path.is_symlink() or not path.is_file():
        raise SystemExit(f"{label} must be a regular non-linked file")
    size = path.stat().st_size
    if not 0 < size <= maximum_bytes:
        raise SystemExit(f"{label} is outside the accepted size boundary")
    return path.resolve()


def require_single_emulator(adb: Path) -> str:
    output = subprocess.run(
        [str(adb), "devices"],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    ).stdout
    devices = [
        line.split()[0]
        for line in output.splitlines()[1:]
        if len(line.split()) >= 2 and line.split()[1] == "device"
    ]
    if len(devices) != 1 or not devices[0].startswith("emulator-"):
        raise SystemExit(
            "Update continuity requires exactly one authorized Android emulator and refuses phones"
        )
    serial = devices[0]
    qemu = run(adb, serial, "shell", "getprop", "ro.kernel.qemu").strip()
    if qemu != "1":
        raise SystemExit("Android target did not prove qemu identity; refusing to continue")
    return serial


def install(adb: Path, serial: str, apk: Path, *, replace: bool) -> None:
    arguments = ["install", "-t"]
    if replace:
        arguments.append("-r")
    arguments.append(str(apk))
    output = run(adb, serial, *arguments, timeout=120)
    if "Success" not in output:
        raise SystemExit(f"Android did not confirm installation of {apk.name}")


def instrument(adb: Path, serial: str, phase: str) -> None:
    output = run(
        adb,
        serial,
        "shell",
        "am",
        "instrument",
        "-w",
        "-e",
        "class",
        TEST_CLASS,
        "-e",
        "romverseUpgradePhase",
        phase,
        RUNNER,
        timeout=90,
    )
    if "OK (1 test)" not in output or "FAILURES!!!" in output:
        raise SystemExit(f"Companion update {phase} phase did not pass\n{output}")


def run(
    adb: Path,
    serial: str,
    *arguments: str,
    timeout: int = 30,
    check: bool = True,
) -> str:
    completed = subprocess.run(
        [str(adb), "-s", serial, *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    output = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
    )
    if check and completed.returncode != 0:
        raise SystemExit(
            f"ADB command failed with status {completed.returncode}: {' '.join(arguments)}\n{output}"
        )
    return output


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
