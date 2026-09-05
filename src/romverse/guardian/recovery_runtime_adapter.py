from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import threading
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from romverse.guardian.invariants import contains_bootloader_lock_action_id
from romverse.guardian.recovery_adapter_package import (
    RECOVERY_ADAPTER_PROTOCOL_VERSION,
    RECOVERY_ADAPTER_REQUEST_SCHEMA_VERSION,
    RECOVERY_ADAPTER_RESULT_SCHEMA_VERSION,
    RecoveryAdapterPackageValidationError,
    RecoveryAdapterTrustScope,
    VerifiedGuardianRecoveryAdapterPackage,
    revalidate_verified_guardian_recovery_adapter_package,
)
from romverse.guardian.recovery_adapter_runner import (
    GuardianRecoveryAdapterObservation,
    GuardianRecoveryAdapterRequest,
)
from romverse.guardian.recovery_execution import RecoveryStepOutcome
from romverse.rom.models import ProjectError

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows launcher remains deliberately disabled.
    fcntl = None  # type: ignore[assignment]

_SHA256 = re.compile(r"[0-9a-f]{64}")


class RecoveryRuntimeAdapterError(ProjectError):
    """The trusted Recovery adapter protocol or launcher failed closed."""


@dataclass(frozen=True, slots=True)
class RecoveryAdapterProcessResult:
    """Bounded process facts; raw output is never success authority by itself."""

    started: bool
    returncode: int
    stdout: bytes
    stderr: bytes
    timed_out: bool
    output_truncated: bool


class RecoveryAdapterProcessRunner(Protocol):
    """No executable path, arguments or environment are accepted from the caller."""

    def run(
        self,
        package: VerifiedGuardianRecoveryAdapterPackage,
        request_bytes: bytes,
        timeout_seconds: int,
    ) -> RecoveryAdapterProcessResult: ...


class SubprocessRecoveryAdapterProcessRunner:
    """Launch only a sealed byte-exact Linux snapshot using one fixed protocol argv."""

    MAX_STDOUT_BYTES = 64 * 1024
    MAX_STDERR_BYTES = 64 * 1024
    MAX_REQUEST_BYTES = 64 * 1024
    FIXED_ARGUMENTS = (
        "--romverse-recovery-protocol",
        str(RECOVERY_ADAPTER_PROTOCOL_VERSION),
    )
    FIXED_ENVIRONMENT = {
        "PATH": "/usr/bin:/bin",
        "LANG": "C",
        "LC_ALL": "C",
    }

    def run(
        self,
        package: VerifiedGuardianRecoveryAdapterPackage,
        request_bytes: bytes,
        timeout_seconds: int,
    ) -> RecoveryAdapterProcessResult:
        try:
            current = revalidate_verified_guardian_recovery_adapter_package(package)
            if (
                not sys.platform.startswith("linux")
                or current.manifest.platform != "linux-x86_64"
                or not isinstance(request_bytes, bytes)
                or not 1 <= len(request_bytes) <= self.MAX_REQUEST_BYTES
                or type(timeout_seconds) is not int
                or not 1 <= timeout_seconds <= 3600
            ):
                raise RecoveryRuntimeAdapterError(
                    "Recovery adapter process launch is unavailable for this exact boundary"
                )
            descriptor = self._sealed_executable(current)
        except (RecoveryAdapterPackageValidationError, OSError, TypeError, ValueError) as exc:
            raise RecoveryRuntimeAdapterError(
                "Recovery adapter executable could not be pinned before launch"
            ) from exc

        reference = f"/proc/self/fd/{descriptor}"
        try:
            try:
                process = subprocess.Popen(
                    (reference, *self.FIXED_ARGUMENTS),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd="/",
                    env=dict(self.FIXED_ENVIRONMENT),
                    shell=False,
                    close_fds=True,
                    pass_fds=(descriptor,),
                    start_new_session=True,
                )
            except OSError:
                return RecoveryAdapterProcessResult(False, 127, b"", b"", False, False)
            stdout, stderr, timed_out, truncated = self._bounded_communication(
                process,
                request_bytes,
                timeout_seconds,
            )
            return RecoveryAdapterProcessResult(
                True,
                int(process.returncode if process.returncode is not None else 126),
                stdout[: self.MAX_STDOUT_BYTES],
                stderr[: self.MAX_STDERR_BYTES],
                timed_out,
                truncated,
            )
        finally:
            os.close(descriptor)

    @classmethod
    def _bounded_communication(
        cls,
        process: subprocess.Popen,
        request_bytes: bytes,
        timeout_seconds: int,
    ) -> tuple[bytes, bytes, bool, bool]:
        buffers = [bytearray(), bytearray()]
        truncated = [False, False]

        def drain(stream, index: int, limit: int) -> None:
            while True:
                block = stream.read(8192)
                if not block:
                    return
                remaining = max(limit - len(buffers[index]), 0)
                buffers[index].extend(block[:remaining])
                if len(block) > remaining:
                    truncated[index] = True

        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise RecoveryRuntimeAdapterError("Recovery adapter process pipes were not isolated")
        readers = (
            threading.Thread(
                target=drain,
                args=(process.stdout, 0, cls.MAX_STDOUT_BYTES),
                daemon=True,
            ),
            threading.Thread(
                target=drain,
                args=(process.stderr, 1, cls.MAX_STDERR_BYTES),
                daemon=True,
            ),
        )
        for reader in readers:
            reader.start()
        with suppress(BrokenPipeError, OSError):
            process.stdin.write(request_bytes)
            process.stdin.flush()
        with suppress(OSError):
            process.stdin.close()
        timed_out = False
        try:
            process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            with suppress(OSError, ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                with suppress(OSError):
                    process.kill()
                process.wait(timeout=5)
        for reader in readers:
            reader.join(timeout=5)
        for reader, stream in zip(
            readers,
            (process.stdout, process.stderr),
            strict=True,
        ):
            if reader.is_alive():
                truncated[0] = True
                truncated[1] = True
                with suppress(OSError):
                    stream.close()
        return bytes(buffers[0]), bytes(buffers[1]), timed_out, any(truncated)

    @staticmethod
    def _sealed_executable(package: VerifiedGuardianRecoveryAdapterPackage) -> int:
        """Copy verified bytes into an immutable memfd, eliminating path TOCTOU."""

        if (
            not hasattr(os, "memfd_create")
            or not hasattr(os, "MFD_ALLOW_SEALING")
            or not Path("/proc/self/fd").is_dir()
            or fcntl is None
        ):
            raise RecoveryRuntimeAdapterError(
                "This Linux host cannot pin a Recovery adapter executable"
            )
        descriptor = os.memfd_create(
            "romverse-recovery-adapter",
            os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING,
        )
        try:
            source = os.open(
                package.artifact_path,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            )
            digest = hashlib.sha256()
            size = 0
            try:
                with os.fdopen(source, "rb", closefd=False) as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        size += len(block)
                        if size > package.manifest.artifact.size_bytes:
                            raise RecoveryRuntimeAdapterError(
                                "Recovery adapter grew before its bytes were pinned"
                            )
                        digest.update(block)
                        view = memoryview(block)
                        while view:
                            written = os.write(descriptor, view)
                            if written <= 0:
                                raise RecoveryRuntimeAdapterError(
                                    "Recovery adapter executable snapshot was incomplete"
                                )
                            view = view[written:]
            finally:
                os.close(source)
            if (
                size != package.manifest.artifact.size_bytes
                or digest.hexdigest() != package.manifest.artifact.sha256
            ):
                raise RecoveryRuntimeAdapterError(
                    "Recovery adapter bytes changed before the executable was pinned"
                )
            os.fchmod(descriptor, 0o500)
            seals = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL
            fcntl.fcntl(descriptor, fcntl.F_ADD_SEALS, seals)
            os.lseek(descriptor, 0, os.SEEK_SET)
            return descriptor
        except Exception:
            os.close(descriptor)
            raise


class GuardianTrustedRecoveryProcessAdapter:
    """The only adapter accepted by the governed runner: signed package + fixed protocol."""

    __slots__ = ("verified_package", "process_runner")

    def __init__(
        self,
        package: VerifiedGuardianRecoveryAdapterPackage,
        process_runner: RecoveryAdapterProcessRunner,
    ) -> None:
        try:
            verified = revalidate_verified_guardian_recovery_adapter_package(package)
            run = process_runner.run
        except (AttributeError, RecoveryAdapterPackageValidationError) as exc:
            raise RecoveryRuntimeAdapterError(
                "Recovery adapter construction requires a verified package and fixed launcher"
            ) from exc
        if not callable(run):
            raise RecoveryRuntimeAdapterError("Recovery adapter launcher is invalid")
        if (
            verified.release_trust_scope is RecoveryAdapterTrustScope.RADFORGE_PRODUCTION
            and type(process_runner) is not SubprocessRecoveryAdapterProcessRunner
        ):
            raise RecoveryRuntimeAdapterError(
                "Production Recovery adapters require the sealed fixed launcher"
            )
        self.verified_package = verified
        self.process_runner = process_runner

    @property
    def adapter_id(self) -> str:
        return self.verified_package.manifest.adapter_id

    @property
    def adapter_version(self) -> int:
        return self.verified_package.manifest.adapter_version

    @property
    def package_sha256(self) -> str:
        return self.verified_package.package_sha256

    @property
    def protocol_version(self) -> int:
        return self.verified_package.manifest.protocol_version

    @property
    def action_ids(self) -> tuple[str, ...]:
        return self.verified_package.manifest.supported_action_ids

    @property
    def bootloader_relock_allowed(self) -> bool:
        return False

    @property
    def automatic_retry_allowed(self) -> bool:
        return False

    def invoke(
        self,
        request: GuardianRecoveryAdapterRequest,
    ) -> GuardianRecoveryAdapterObservation:
        try:
            package = revalidate_verified_guardian_recovery_adapter_package(self.verified_package)
            request_bytes, request_digest = self._request_bytes(request, package)
            process = self.process_runner.run(
                package,
                request_bytes,
                request.timeout_seconds,
            )
            return self._observation(process, request, package, request_digest)
        except RecoveryAdapterPackageValidationError as exc:
            raise RecoveryRuntimeAdapterError(
                "Recovery adapter package changed before invocation"
            ) from exc

    @staticmethod
    def _request_bytes(
        request: GuardianRecoveryAdapterRequest,
        package: VerifiedGuardianRecoveryAdapterPackage,
    ) -> tuple[bytes, str]:
        if (
            not isinstance(request, GuardianRecoveryAdapterRequest)
            or request.adapter_id != package.manifest.adapter_id
            or request.adapter_action_id not in package.manifest.supported_action_ids
            or contains_bootloader_lock_action_id(request.adapter_action_id)
        ):
            raise RecoveryRuntimeAdapterError(
                "Recovery adapter request is outside the verified package allowlist"
            )
        payload: dict[str, object] = {
            "schema_version": RECOVERY_ADAPTER_REQUEST_SCHEMA_VERSION,
            "protocol_version": RECOVERY_ADAPTER_PROTOCOL_VERSION,
            "invocation_id": secrets.token_hex(16),
            "claim_id": request.claim_id,
            "incident_id": request.incident_id,
            "preparation_digest": request.preparation_digest,
            "device_key": request.device_key,
            "adapter_id": request.adapter_id,
            "adapter_version": package.manifest.adapter_version,
            "package_sha256": package.package_sha256,
            "adapter_action_id": request.adapter_action_id,
            "operation": request.operation.value,
            "step_order": request.step_order,
            "expected_from_mode": request.expected_from_mode,
            "expected_to_mode": request.expected_to_mode,
            "target_slot": request.target_slot,
            "stock_package_path": str(request.stock_package_path),
            "stock_package_sha256": request.stock_package_sha256,
            "timeout_seconds": request.timeout_seconds,
            "may_wipe_user_data": request.may_wipe_user_data,
            "target_serial": request.target_serial,
            "automatic_retry_allowed": False,
            "bootloader_relock_allowed": False,
        }
        digest = _digest(payload)
        payload["request_digest"] = digest
        encoded = _canonical(payload)
        if len(encoded) > SubprocessRecoveryAdapterProcessRunner.MAX_REQUEST_BYTES:
            raise RecoveryRuntimeAdapterError(
                "Recovery adapter request exceeds its protocol boundary"
            )
        return encoded, digest

    @staticmethod
    def _observation(
        process: RecoveryAdapterProcessResult,
        request: GuardianRecoveryAdapterRequest,
        package: VerifiedGuardianRecoveryAdapterPackage,
        request_digest: str,
    ) -> GuardianRecoveryAdapterObservation:
        if not isinstance(process, RecoveryAdapterProcessResult):
            raise RecoveryRuntimeAdapterError("Recovery adapter process result is malformed")
        if not isinstance(process.stdout, bytes) or not isinstance(process.stderr, bytes):
            raise RecoveryRuntimeAdapterError("Recovery adapter process output is malformed")
        fallback = _digest(
            {
                "request_digest": request_digest,
                "started": process.started,
                "returncode": process.returncode,
                "timed_out": process.timed_out,
                "output_truncated": process.output_truncated,
                "stdout_sha256": hashlib.sha256(process.stdout).hexdigest(),
                "stderr_sha256": hashlib.sha256(process.stderr).hexdigest(),
            }
        )
        if (
            type(process.started) is not bool
            or type(process.returncode) is not int
            or not isinstance(process.stdout, bytes)
            or not isinstance(process.stderr, bytes)
            or type(process.timed_out) is not bool
            or type(process.output_truncated) is not bool
            or process.timed_out
            or process.output_truncated
            or not process.started
        ):
            return GuardianRecoveryAdapterObservation(
                request.adapter_id,
                request.adapter_action_id,
                request.step_order,
                RecoveryStepOutcome.UNKNOWN,
                process.started if type(process.started) is bool else True,
                process.timed_out if type(process.timed_out) is bool else False,
                fallback,
            )
        try:
            response = _strict_json(process.stdout)
            expected_fields = {
                "schema_version",
                "protocol_version",
                "request_digest",
                "package_sha256",
                "adapter_id",
                "adapter_version",
                "adapter_action_id",
                "step_order",
                "outcome",
                "dispatch_started",
                "timed_out",
                "evidence_sha256",
            }
            if set(response) != expected_fields or process.stdout != _canonical(response):
                raise ValueError("response schema is not exact canonical JSON")
            outcome = RecoveryStepOutcome(response["outcome"])
            if (
                type(response["schema_version"]) is not int
                or response["schema_version"] != RECOVERY_ADAPTER_RESULT_SCHEMA_VERSION
                or type(response["protocol_version"]) is not int
                or response["protocol_version"] != RECOVERY_ADAPTER_PROTOCOL_VERSION
                or response["request_digest"] != request_digest
                or response["package_sha256"] != package.package_sha256
                or response["adapter_id"] != request.adapter_id
                or type(response["adapter_version"]) is not int
                or response["adapter_version"] != package.manifest.adapter_version
                or response["adapter_action_id"] != request.adapter_action_id
                or type(response["step_order"]) is not int
                or response["step_order"] != request.step_order
                or type(response["dispatch_started"]) is not bool
                or type(response["timed_out"]) is not bool
                or response["timed_out"] is not False
                or not _hex(response["evidence_sha256"])
                or (outcome is RecoveryStepOutcome.SUCCEEDED and process.returncode != 0)
                or (
                    outcome is RecoveryStepOutcome.SUCCEEDED
                    and response["dispatch_started"] is not True
                )
            ):
                raise ValueError("response conflicts with exact request or process facts")
            return GuardianRecoveryAdapterObservation(
                request.adapter_id,
                request.adapter_action_id,
                request.step_order,
                outcome,
                response["dispatch_started"],
                False,
                response["evidence_sha256"],
            )
        except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return GuardianRecoveryAdapterObservation(
                request.adapter_id,
                request.adapter_action_id,
                request.step_order,
                RecoveryStepOutcome.UNKNOWN,
                True,
                False,
                fallback,
            )


def _strict_json(encoded: bytes) -> dict[str, object]:
    def pairs(values: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in values:
            if key in result:
                raise ValueError(f"duplicate Recovery adapter result field: {key}")
            result[key] = value
        return result

    value = json.loads(encoded.decode("ascii"), object_pairs_hook=pairs)
    if not isinstance(value, dict):
        raise ValueError("Recovery adapter result must be one object")
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _hex(value: object) -> bool:
    return isinstance(value, str) and bool(_SHA256.fullmatch(value))
