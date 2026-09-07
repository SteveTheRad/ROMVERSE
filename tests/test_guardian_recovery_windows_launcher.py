from __future__ import annotations

import inspect
import io
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from romverse.device_packs.models import DeviceRecoveryOperation
from romverse.guardian.recovery_adapter_package import (
    GuardianRecoveryAdapterReleaseTrustRoot,
    RecoveryAdapterTrustScope,
    build_guardian_recovery_adapter_manifest,
    create_signed_guardian_recovery_adapter_package,
    resolve_radforge_production_recovery_adapter_package,
    verify_guardian_recovery_adapter_package,
)
from romverse.guardian.recovery_adapter_runner import GuardianRecoveryAdapterRequest
from romverse.guardian.recovery_execution import RecoveryStepOutcome
from romverse.guardian.recovery_runtime_adapter import (
    GuardianTrustedRecoveryProcessAdapter,
    RecoveryAdapterProcessResult,
    RecoveryRuntimeAdapterError,
    SubprocessRecoveryAdapterProcessRunner,
    WindowsSubprocessRecoveryAdapterProcessRunner,
)

ADAPTER_ID = "romverse.fixture.windows-recovery"
ACTION_ID = f"{ADAPTER_ID}.restore-stock"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _windows_package(directory: Path, *, production: bool = False):
    directory.mkdir(parents=True, exist_ok=True)
    artifact = directory / "ROMVERSE-Recovery-Adapter.exe"
    artifact.write_bytes(b"MZ\x00ROMVERSE-INERT-WINDOWS-ADAPTER")
    private_key = Ed25519PrivateKey.generate()
    scope = (
        RecoveryAdapterTrustScope.RADFORGE_PRODUCTION
        if production
        else RecoveryAdapterTrustScope.TEST_ONLY
    )
    key_id = (
        "radforge.recovery-adapter.release-2026" if production else "test.windows-recovery-adapter"
    )
    trust = GuardianRecoveryAdapterReleaseTrustRoot.from_public_key(
        key_id=key_id,
        public_key=private_key.public_key(),
        scope=scope,
    )
    manifest = build_guardian_recovery_adapter_manifest(
        package_id="romverse.recovery-adapter.windows-test",
        package_version="0.1.0-test.1",
        created_at="2026-09-07T00:00:00Z",
        platform="windows-x86_64",
        artifact_path=artifact,
        adapter_id=ADAPTER_ID,
        adapter_version=1,
        supported_action_ids=(ACTION_ID,),
    )
    envelope = create_signed_guardian_recovery_adapter_package(
        manifest,
        private_key,
        trust.key_id,
    )
    resolver = (
        resolve_radforge_production_recovery_adapter_package
        if production
        else verify_guardian_recovery_adapter_package
    )
    package = resolver(
        envelope=envelope,
        trust_root=trust,
        package_directory=directory,
        expected_platform="windows-x86_64",
    )
    return package, artifact


def _request(tmp_path: Path, *, action_id: str = ACTION_ID) -> GuardianRecoveryAdapterRequest:
    stock = tmp_path / "stock.zip"
    stock.write_bytes(b"inert-stock-fixture")
    return GuardianRecoveryAdapterRequest(
        claim_id="1" * 32,
        incident_id="2" * 32,
        preparation_digest="3" * 64,
        device_key="4" * 64,
        adapter_id=ADAPTER_ID,
        adapter_action_id=action_id,
        operation=DeviceRecoveryOperation.RESTORE_STOCK_PACKAGE,
        step_order=1,
        expected_from_mode="bootloader",
        expected_to_mode="bootloader",
        target_slot="a",
        stock_package_path=stock,
        stock_package_sha256="5" * 64,
        timeout_seconds=30,
        may_wipe_user_data=False,
        target_serial="inert-private-serial",
    )


def _pretend_windows(monkeypatch) -> None:
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(sys, "platform", "win32")


def _fake_pinned_launcher(monkeypatch, package, *, path_matches: bool = True):
    descriptor = os.open(package.artifact_path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    monkeypatch.setattr(
        WindowsSubprocessRecoveryAdapterProcessRunner,
        "_pinned_executable",
        staticmethod(lambda _package: (descriptor, (1, 2, 1, 3, 4, 5))),
    )
    monkeypatch.setattr(
        WindowsSubprocessRecoveryAdapterProcessRunner,
        "_path_matches_descriptor",
        staticmethod(lambda *_args: path_matches),
    )
    monkeypatch.setattr(
        WindowsSubprocessRecoveryAdapterProcessRunner,
        "_windows_directory",
        staticmethod(lambda: r"C:\Windows"),
    )
    return descriptor


def test_exact_package_artifact_fixed_protocol_and_environment_are_bound(
    tmp_path,
    monkeypatch,
) -> None:
    package, _artifact = _windows_package(tmp_path / "package")
    _pretend_windows(monkeypatch)
    descriptor = _fake_pinned_launcher(monkeypatch, package)
    calls = []

    class FakeProcess:
        returncode = 0

    def fake_popen(argv, **kwargs):
        calls.append((argv, kwargs))
        return FakeProcess()

    monkeypatch.setattr("romverse.guardian.recovery_runtime_adapter.subprocess.Popen", fake_popen)
    monkeypatch.setattr(
        WindowsSubprocessRecoveryAdapterProcessRunner,
        "_bounded_communication",
        classmethod(lambda _cls, _process, _request, _timeout: (b"{}", b"", False, False)),
    )

    result = WindowsSubprocessRecoveryAdapterProcessRunner().run(package, b"{}", 30)

    assert result.started
    assert result.returncode == 0
    assert len(calls) == 1
    argv, options = calls[0]
    assert argv == (
        str(package.artifact_path),
        "--romverse-recovery-protocol",
        "1",
    )
    assert options["shell"] is False
    assert options["cwd"] == r"C:\Windows"
    assert options["env"] == {
        "SystemRoot": r"C:\Windows",
        "WINDIR": r"C:\Windows",
        "LANG": "C",
        "LC_ALL": "C",
    }
    with pytest.raises(OSError):
        os.fstat(descriptor)


@pytest.mark.parametrize("drift", ("size", "hash"))
def test_hash_or_size_drift_fails_before_dispatch(tmp_path, monkeypatch, drift) -> None:
    package, artifact = _windows_package(tmp_path / "package")
    original = artifact.read_bytes()
    replacement = original[:-1] if drift == "size" else bytes([original[0] ^ 1]) + original[1:]
    assert (len(replacement) == len(original)) is (drift == "hash")
    artifact.write_bytes(replacement)
    _pretend_windows(monkeypatch)
    dispatched = []
    monkeypatch.setattr(
        "romverse.guardian.recovery_runtime_adapter.subprocess.Popen",
        lambda *_args, **_kwargs: dispatched.append(True),
    )

    with pytest.raises(RecoveryRuntimeAdapterError, match="could not be pinned"):
        WindowsSubprocessRecoveryAdapterProcessRunner().run(package, b"{}", 30)

    assert dispatched == []


@pytest.mark.parametrize(
    "changed_package",
    (
        lambda package: replace(package, package_sha256="0" * 64),
        lambda package: replace(package, release_key_id="test.substituted-signer"),
    ),
    ids=("package-identity", "signer-identity"),
)
def test_package_and_signer_identity_drift_fail_before_dispatch(
    tmp_path,
    monkeypatch,
    changed_package,
) -> None:
    package, _artifact = _windows_package(tmp_path / "package")
    _pretend_windows(monkeypatch)
    pinned = []
    monkeypatch.setattr(
        WindowsSubprocessRecoveryAdapterProcessRunner,
        "_pinned_executable",
        staticmethod(lambda *_args: pinned.append(True)),
    )

    with pytest.raises(RecoveryRuntimeAdapterError, match="could not be pinned"):
        WindowsSubprocessRecoveryAdapterProcessRunner().run(
            changed_package(package),
            b"{}",
            30,
        )

    assert pinned == []


def test_reparse_and_symlink_style_paths_fail_closed() -> None:
    reparse = SimpleNamespace(st_file_attributes=0x400)
    ordinary = SimpleNamespace(st_file_attributes=0)

    assert WindowsSubprocessRecoveryAdapterProcessRunner._is_reparse(reparse)
    assert not WindowsSubprocessRecoveryAdapterProcessRunner._is_reparse(ordinary)

    class ReparsePath:
        def lstat(self):
            return reparse

        @property
        def parent(self):
            return self

    with pytest.raises(RecoveryRuntimeAdapterError, match="reparse point"):
        WindowsSubprocessRecoveryAdapterProcessRunner._reject_reparse_path(ReparsePath())


def test_path_replacement_identity_race_stops_before_popen(tmp_path, monkeypatch) -> None:
    package, _artifact = _windows_package(tmp_path / "package")
    _pretend_windows(monkeypatch)
    descriptor = _fake_pinned_launcher(monkeypatch, package, path_matches=False)
    dispatched = []
    monkeypatch.setattr(
        "romverse.guardian.recovery_runtime_adapter.subprocess.Popen",
        lambda *_args, **_kwargs: dispatched.append(True),
    )

    with pytest.raises(RecoveryRuntimeAdapterError, match="path identity changed"):
        WindowsSubprocessRecoveryAdapterProcessRunner().run(package, b"{}", 30)

    assert dispatched == []
    with pytest.raises(OSError):
        os.fstat(descriptor)


@pytest.mark.skipif(os.name != "nt", reason="Windows handle identity is host-specific")
def test_hard_link_alias_is_rejected_before_launch(tmp_path) -> None:
    package, artifact = _windows_package(tmp_path / "package")
    os.link(artifact, tmp_path / "adapter-alias.exe")

    with pytest.raises(RecoveryRuntimeAdapterError, match="unlinked"):
        WindowsSubprocessRecoveryAdapterProcessRunner._pinned_executable(package)


@pytest.mark.skipif(os.name != "nt", reason="Windows sharing lock is host-specific")
def test_verified_handle_blocks_write_delete_and_path_replacement_until_closed(tmp_path) -> None:
    package, artifact = _windows_package(tmp_path / "package")
    replacement = tmp_path / "replacement.exe"
    replacement.write_bytes(b"MZ\x00SUBSTITUTED-INERT-ADAPTER")

    descriptor, identity = WindowsSubprocessRecoveryAdapterProcessRunner._pinned_executable(package)
    try:
        with pytest.raises(OSError):
            artifact.write_bytes(b"MZ\x00DRIFT")
        with pytest.raises(OSError):
            os.replace(replacement, artifact)
        assert WindowsSubprocessRecoveryAdapterProcessRunner._path_matches_descriptor(
            artifact,
            descriptor,
            identity,
        )
    finally:
        os.close(descriptor)


def test_wrong_platform_is_rejected_before_handle_or_process(tmp_path, monkeypatch) -> None:
    package, _artifact = _windows_package(tmp_path / "package")
    wrong = replace(package, manifest=replace(package.manifest, platform="linux-x86_64"))
    _pretend_windows(monkeypatch)
    pinned = []
    monkeypatch.setattr(
        WindowsSubprocessRecoveryAdapterProcessRunner,
        "_pinned_executable",
        staticmethod(lambda *_args: pinned.append(True)),
    )

    with pytest.raises(RecoveryRuntimeAdapterError, match="could not be pinned"):
        WindowsSubprocessRecoveryAdapterProcessRunner().run(wrong, b"{}", 30)

    assert pinned == []


def test_production_package_requires_the_exact_platform_launcher(tmp_path) -> None:
    package, _artifact = _windows_package(tmp_path / "package", production=True)

    with pytest.raises(RecoveryRuntimeAdapterError, match="sealed fixed launcher"):
        GuardianTrustedRecoveryProcessAdapter(
            package,
            SubprocessRecoveryAdapterProcessRunner(),
        )
    adapter = GuardianTrustedRecoveryProcessAdapter(
        package,
        WindowsSubprocessRecoveryAdapterProcessRunner(),
    )
    assert adapter.verified_package == package


@pytest.mark.parametrize(
    "request_bytes,timeout",
    ((b"", 30), (b"x" * 65537, 30), (b"{}", 0), (b"{}", 3601)),
    ids=("empty-request", "oversized-request", "zero-timeout", "oversized-timeout"),
)
def test_request_and_timeout_bounds_stop_before_dispatch(
    tmp_path,
    monkeypatch,
    request_bytes,
    timeout,
) -> None:
    package, _artifact = _windows_package(tmp_path / "package")
    _pretend_windows(monkeypatch)
    pinned = []
    monkeypatch.setattr(
        WindowsSubprocessRecoveryAdapterProcessRunner,
        "_pinned_executable",
        staticmethod(lambda *_args: pinned.append(True)),
    )

    with pytest.raises(RecoveryRuntimeAdapterError, match="unavailable"):
        WindowsSubprocessRecoveryAdapterProcessRunner().run(package, request_bytes, timeout)

    assert pinned == []


def test_output_is_bounded_and_timeout_is_uncertain() -> None:
    class TimedOutProcess:
        def __init__(self) -> None:
            self.stdin = io.BytesIO()
            self.stdout = io.BytesIO(b"o" * 70000)
            self.stderr = io.BytesIO(b"e" * 70000)
            self.returncode = None
            self.pid = 123
            self.waits = 0
            self.kills = 0

        def wait(self, timeout):
            self.waits += 1
            if self.waits == 1:
                raise subprocess.TimeoutExpired("fixture", timeout)
            self.returncode = 1
            return 1

        def kill(self):
            self.kills += 1

        def terminate(self):
            raise AssertionError("kill completed; terminate must not be needed")

    process = TimedOutProcess()
    stdout, stderr, timed_out, truncated = (
        WindowsSubprocessRecoveryAdapterProcessRunner._bounded_communication(
            process,
            b"{}",
            1,
        )
    )

    assert len(stdout) == 65536
    assert len(stderr) == 65536
    assert timed_out
    assert truncated
    assert process.kills == 1


class _ProtocolProcess:
    def __init__(self, body: bytes | None = None) -> None:
        self.body = body
        self.calls = 0

    def run(self, package, request_bytes, _timeout):
        self.calls += 1
        request = json.loads(request_bytes)
        response = {
            "schema_version": 1,
            "protocol_version": 1,
            "request_digest": request["request_digest"],
            "package_sha256": package.package_sha256,
            "adapter_id": request["adapter_id"],
            "adapter_version": package.manifest.adapter_version,
            "adapter_action_id": request["adapter_action_id"],
            "step_order": request["step_order"],
            "outcome": "succeeded",
            "dispatch_started": True,
            "timed_out": False,
            "evidence_sha256": "a" * 64,
        }
        return RecoveryAdapterProcessResult(
            True,
            0,
            self.body if self.body is not None else _canonical(response),
            b"",
            False,
            False,
        )


@pytest.mark.parametrize("body", (b"SUCCESS", b"{}", b'{"outcome":"succeeded"}'))
def test_malformed_or_ambiguous_results_become_unknown(tmp_path, body) -> None:
    package, _artifact = _windows_package(tmp_path / "package")
    process = _ProtocolProcess(body)
    adapter = GuardianTrustedRecoveryProcessAdapter(package, process)

    observation = adapter.invoke(_request(tmp_path))

    assert observation.outcome is RecoveryStepOutcome.UNKNOWN
    assert observation.dispatch_started
    assert process.calls == 1


def test_process_start_failure_has_no_automatic_retry(tmp_path, monkeypatch) -> None:
    package, _artifact = _windows_package(tmp_path / "package")
    _pretend_windows(monkeypatch)
    descriptor = _fake_pinned_launcher(monkeypatch, package)
    attempts = []

    def unavailable(*_args, **_kwargs):
        attempts.append(True)
        raise OSError("inert fixture launch failure")

    monkeypatch.setattr("romverse.guardian.recovery_runtime_adapter.subprocess.Popen", unavailable)

    result = WindowsSubprocessRecoveryAdapterProcessRunner().run(package, b"{}", 30)

    assert not result.started
    assert result.returncode == 127
    assert attempts == [True]
    with pytest.raises(OSError):
        os.fstat(descriptor)


def test_launcher_has_no_caller_command_authority_and_relock_is_permanently_rejected(
    tmp_path,
) -> None:
    package, _artifact = _windows_package(tmp_path / "package")
    process = _ProtocolProcess()
    adapter = GuardianTrustedRecoveryProcessAdapter(package, process)
    parameters = tuple(
        inspect.signature(WindowsSubprocessRecoveryAdapterProcessRunner.run).parameters
    )

    assert parameters == ("self", "package", "request_bytes", "timeout_seconds")
    assert adapter.automatic_retry_allowed is False
    assert adapter.bootloader_relock_allowed is False
    with pytest.raises(RecoveryRuntimeAdapterError, match="outside the verified package allowlist"):
        adapter.invoke(_request(tmp_path, action_id=f"{ADAPTER_ID}.bootloader-relock"))
    assert process.calls == 0
