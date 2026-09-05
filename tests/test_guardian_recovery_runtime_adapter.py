from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from romverse.device_packs.models import DeviceRecoveryOperation
from romverse.guardian.recovery_adapter_package import (
    GuardianRecoveryAdapterReleaseTrustRoot,
    RecoveryAdapterTrustScope,
    create_signed_guardian_recovery_adapter_package,
    resolve_radforge_production_recovery_adapter_package,
)
from romverse.guardian.recovery_adapter_runner import GuardianRecoveryAdapterRequest
from romverse.guardian.recovery_execution import RecoveryStepOutcome
from romverse.guardian.recovery_runtime_adapter import (
    GuardianTrustedRecoveryProcessAdapter,
    RecoveryAdapterProcessResult,
    RecoveryRuntimeAdapterError,
    SubprocessRecoveryAdapterProcessRunner,
)
from tests._recovery_adapter_trust import HOST_PLATFORM, make_test_recovery_adapter_package

ADAPTER_ID = "romverse.fixture.recovery"
ACTION_ID = f"{ADAPTER_ID}.restore-stock"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


class _ProtocolProcess:
    def __init__(self) -> None:
        self.calls = []
        self.outcome = RecoveryStepOutcome.SUCCEEDED
        self.returncode = 0
        self.timed_out = False
        self.started = True
        self.output_truncated = False
        self.mutation = None

    def run(self, package, request_bytes, timeout_seconds):
        request = json.loads(request_bytes)
        self.calls.append((package, request, timeout_seconds))
        response = {
            "schema_version": 1,
            "protocol_version": 1,
            "request_digest": request["request_digest"],
            "package_sha256": package.package_sha256,
            "adapter_id": request["adapter_id"],
            "adapter_version": package.manifest.adapter_version,
            "adapter_action_id": request["adapter_action_id"],
            "step_order": request["step_order"],
            "outcome": self.outcome.value,
            "dispatch_started": self.started,
            "timed_out": False,
            "evidence_sha256": "a" * 64,
        }
        if self.mutation is not None:
            self.mutation(response)
        return RecoveryAdapterProcessResult(
            self.started,
            self.returncode,
            _canonical(response),
            b"ignored diagnostic detail",
            self.timed_out,
            self.output_truncated,
        )


def _adapter(tmp_path):
    package, *_rest = make_test_recovery_adapter_package(
        tmp_path / "package",
        adapter_id=ADAPTER_ID,
        action_ids=(ACTION_ID,),
    )
    process = _ProtocolProcess()
    return GuardianTrustedRecoveryProcessAdapter(package, process), process


def _request(tmp_path):
    stock = tmp_path / "stock.zip"
    stock.write_bytes(b"stock")
    return GuardianRecoveryAdapterRequest(
        claim_id="1" * 32,
        incident_id="2" * 32,
        preparation_digest="3" * 64,
        device_key="4" * 64,
        adapter_id=ADAPTER_ID,
        adapter_action_id=ACTION_ID,
        operation=DeviceRecoveryOperation.RESTORE_STOCK_PACKAGE,
        step_order=1,
        expected_from_mode="bootloader",
        expected_to_mode="bootloader",
        target_slot="a",
        stock_package_path=stock,
        stock_package_sha256="5" * 64,
        timeout_seconds=30,
        may_wipe_user_data=False,
        target_serial="private-serial",
    )


def test_adapter_uses_exact_machine_protocol_without_command_or_environment_surface(
    tmp_path,
) -> None:
    adapter, process = _adapter(tmp_path)

    observation = adapter.invoke(_request(tmp_path))

    assert observation.outcome is RecoveryStepOutcome.SUCCEEDED
    assert observation.dispatch_started
    assert observation.evidence_sha256 == "a" * 64
    assert len(process.calls) == 1
    package, request, timeout = process.calls[0]
    assert package == adapter.verified_package
    assert timeout == 30
    assert request["adapter_id"] == ADAPTER_ID
    assert request["adapter_action_id"] == ACTION_ID
    assert request["target_serial"] == "private-serial"
    forbidden = {"command", "executable", "script", "args", "extraArgs", "environment", "env"}
    assert not forbidden.intersection(request)
    assert request["automatic_retry_allowed"] is False
    assert request["bootloader_relock_allowed"] is False


@pytest.mark.parametrize(
    "mutation",
    (
        lambda result: result.update({"protocol_version": 2}),
        lambda result: result.update({"schema_version": 2}),
        lambda result: result.update({"adapter_action_id": f"{ADAPTER_ID}.hidden"}),
        lambda result: result.update({"command": "fastboot flashing lock"}),
        lambda result: result.update({"request_digest": "0" * 64}),
        lambda result: result.update({"package_sha256": "0" * 64}),
    ),
)
def test_protocol_mismatch_hidden_fields_and_request_substitution_become_unknown(
    tmp_path,
    mutation,
) -> None:
    adapter, process = _adapter(tmp_path)
    process.mutation = mutation

    observation = adapter.invoke(_request(tmp_path))

    assert observation.outcome is RecoveryStepOutcome.UNKNOWN
    assert observation.dispatch_started
    assert not observation.timed_out


def test_raw_success_text_malformed_duplicate_timeout_and_process_conflict_are_not_success(
    tmp_path,
) -> None:
    adapter, process = _adapter(tmp_path)
    request = _request(tmp_path)

    class RawSuccess:
        def run(self, *_args):
            return RecoveryAdapterProcessResult(True, 0, b"SUCCESS", b"", False, False)

    raw = GuardianTrustedRecoveryProcessAdapter(adapter.verified_package, RawSuccess())
    assert raw.invoke(request).outcome is RecoveryStepOutcome.UNKNOWN

    class Duplicate:
        def run(self, package, request_bytes, _timeout):
            request_data = json.loads(request_bytes)
            body = (
                '{"schema_version":1,"schema_version":1,"protocol_version":1,'
                f'"request_digest":"{request_data["request_digest"]}"}}'
            ).encode()
            return RecoveryAdapterProcessResult(True, 0, body, b"", False, False)

    duplicate = GuardianTrustedRecoveryProcessAdapter(
        adapter.verified_package,
        Duplicate(),
    )
    assert duplicate.invoke(request).outcome is RecoveryStepOutcome.UNKNOWN

    process.timed_out = True
    assert adapter.invoke(request).outcome is RecoveryStepOutcome.UNKNOWN
    process.timed_out = False
    process.returncode = 9
    assert adapter.invoke(request).outcome is RecoveryStepOutcome.UNKNOWN


def test_unsupported_or_lock_action_never_reaches_process(tmp_path) -> None:
    adapter, process = _adapter(tmp_path)
    unexpected = replace(
        _request(tmp_path),
        adapter_action_id=f"{ADAPTER_ID}.hidden",
    )
    with pytest.raises(RecoveryRuntimeAdapterError, match="outside the verified package allowlist"):
        adapter.invoke(unexpected)
    locking = replace(
        _request(tmp_path),
        adapter_action_id=f"{ADAPTER_ID}.bootloader-lock",
    )
    with pytest.raises(RecoveryRuntimeAdapterError, match="outside the verified package allowlist"):
        adapter.invoke(locking)
    assert process.calls == []


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="sealed memfd is Linux-specific")
def test_sealed_launcher_prevents_verification_to_launch_path_substitution(
    tmp_path,
    monkeypatch,
) -> None:
    verified_script = b"#!/bin/sh\nprintf 'verified-bytes\\n'\n"
    substituted_script = b"#!/bin/sh\nprintf 'substituted-bytes\\n'\n"
    package, artifact, *_rest = make_test_recovery_adapter_package(
        tmp_path / "package",
        adapter_id=ADAPTER_ID,
        action_ids=(ACTION_ID,),
        artifact_bytes=verified_script,
    )
    original_popen = subprocess.Popen

    def substitute_after_pin(*args, **kwargs):
        artifact.write_bytes(substituted_script)
        artifact.chmod(0o700)
        return original_popen(*args, **kwargs)

    monkeypatch.setattr(
        "romverse.guardian.recovery_runtime_adapter.subprocess.Popen",
        substitute_after_pin,
    )

    result = SubprocessRecoveryAdapterProcessRunner().run(package, b"{}", 5)

    assert result.started
    assert result.returncode == 0
    assert result.stdout == b"verified-bytes\n"
    assert not result.timed_out


@pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="sealed memfd is Linux-specific",
)
def test_concrete_launcher_bounds_timeout_as_an_uncertain_process_result(tmp_path) -> None:
    package, *_rest = make_test_recovery_adapter_package(
        tmp_path / "package",
        adapter_id=ADAPTER_ID,
        action_ids=(ACTION_ID,),
        artifact_bytes=b"#!/bin/sh\nsleep 30\n",
    )

    result = SubprocessRecoveryAdapterProcessRunner().run(package, b"{}", 1)

    assert result.started
    assert result.timed_out
    assert result.returncode != 0


def test_launcher_interface_has_no_path_argument_and_fixed_environment() -> None:
    runner = SubprocessRecoveryAdapterProcessRunner()

    assert runner.FIXED_ARGUMENTS == ("--romverse-recovery-protocol", "1")
    assert runner.FIXED_ENVIRONMENT == {
        "PATH": "/usr/bin:/bin",
        "LANG": "C",
        "LC_ALL": "C",
    }


def test_radforge_production_package_rejects_an_injected_launcher(tmp_path) -> None:
    _test_package, _artifact, _test_private, _test_trust, manifest, _test_envelope = (
        make_test_recovery_adapter_package(
            tmp_path / "package",
            adapter_id=ADAPTER_ID,
            action_ids=(ACTION_ID,),
        )
    )
    production_private = Ed25519PrivateKey.generate()
    production_trust = GuardianRecoveryAdapterReleaseTrustRoot.from_public_key(
        key_id="radforge.recovery-adapter.release-2026",
        public_key=production_private.public_key(),
        scope=RecoveryAdapterTrustScope.RADFORGE_PRODUCTION,
    )
    envelope = create_signed_guardian_recovery_adapter_package(
        manifest,
        production_private,
        production_trust.key_id,
    )
    production_package = resolve_radforge_production_recovery_adapter_package(
        envelope=envelope,
        trust_root=production_trust,
        package_directory=tmp_path / "package",
        expected_platform=HOST_PLATFORM,
    )

    with pytest.raises(RecoveryRuntimeAdapterError, match="sealed fixed launcher"):
        GuardianTrustedRecoveryProcessAdapter(production_package, _ProtocolProcess())
