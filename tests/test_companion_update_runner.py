from types import SimpleNamespace

import pytest

from scripts import verify_companion_update as update_runner


def _result(stdout: str, returncode: int = 0) -> SimpleNamespace:
    return SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)


def test_update_runner_refuses_a_physical_android_target(monkeypatch, tmp_path) -> None:
    adb = tmp_path / "adb"
    adb.write_bytes(b"bounded test executable")
    monkeypatch.setattr(
        update_runner.subprocess,
        "run",
        lambda *_args, **_kwargs: _result(
            "List of devices attached\nphysical-phone\tdevice\n",
        ),
    )

    with pytest.raises(SystemExit, match="refuses phones"):
        update_runner.require_single_emulator(adb)


def test_update_runner_requires_qemu_identity_after_emulator_serial(monkeypatch, tmp_path) -> None:
    adb = tmp_path / "adb"
    adb.write_bytes(b"bounded test executable")
    responses = iter(
        (
            _result("List of devices attached\nemulator-5554\tdevice\n"),
            _result("0\n"),
        )
    )
    monkeypatch.setattr(
        update_runner.subprocess,
        "run",
        lambda *_args, **_kwargs: next(responses),
    )

    with pytest.raises(SystemExit, match="did not prove qemu identity"):
        update_runner.require_single_emulator(adb)


def test_update_runner_rejects_linked_artifact_input(tmp_path) -> None:
    artifact = tmp_path / "candidate.apk"
    artifact.write_bytes(b"candidate")
    linked = tmp_path / "linked.apk"
    linked.symlink_to(artifact)

    with pytest.raises(SystemExit, match="regular non-linked file"):
        update_runner.regular_file(linked, "candidate APK")
