from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from romverse.guardian.approval import ApprovalStore
from romverse.guardian.gateway import ExecutionGateway
from romverse.guardian.models import OperationClass, OperationRequest
from romverse.infrastructure.local_store import atomic_write_json, read_json_object
from romverse.infrastructure.process import CommandResult


class AdbHostRepairError(RuntimeError):
    pass


class AdbHostRepairMode(StrEnum):
    START = "start"
    RESTART = "restart"


class AdbHostRepairStatus(StrEnum):
    SUCCEEDED = "succeeded"
    ATTENTION = "attention"
    FAILED = "failed"


ADB_HOST_REPAIR_TARGET = "host:adb-server"


@dataclass(frozen=True, slots=True)
class AdbHostRepairPlan:
    schema_version: int
    created_at: str
    mode: AdbHostRepairMode
    reason: str
    executable_path: str
    executable_sha256: str
    target: str = ADB_HOST_REPAIR_TARGET
    phone_changed: bool = False
    execution_authority: str = "host-adb-daemon-only"
    bootloader_relock: str = "never"

    def digest(self) -> str:
        return hashlib.sha256(_canonical(asdict(self))).hexdigest()


@dataclass(frozen=True, slots=True)
class AdbHostRepairResult:
    status: AdbHostRepairStatus
    summary: str
    receipt_saved: bool
    receipt_digest: str = ""
    receipt_ref: str = ""


@dataclass(frozen=True, slots=True)
class AdbHostRepairReceiptReview:
    valid: bool
    integrity_verified: bool
    reason: str
    data: dict[str, object] | None = None


def create_adb_host_repair_plan(
    executable: Path,
    mode: AdbHostRepairMode,
    reason: str,
) -> AdbHostRepairPlan:
    try:
        resolved = executable.resolve(strict=True)
    except OSError as exc:
        raise AdbHostRepairError(f"Verified ADB executable is unavailable: {exc}") from exc
    if (
        not resolved.is_file()
        or not os.access(resolved, os.X_OK)
        or resolved.name.casefold() not in {"adb", "adb.exe"}
    ):
        raise AdbHostRepairError("ADB host recovery requires the verified ADB executable")
    clean_reason = _bounded_text(reason, "repair reason", 400)
    return AdbHostRepairPlan(
        schema_version=1,
        created_at=datetime.now(UTC).isoformat(),
        mode=mode,
        reason=clean_reason,
        executable_path=str(resolved),
        executable_sha256=_sha256_file(resolved),
    )


class AdbHostRepairReceiptStore:
    FORMAT = "romverse.adb-host-repair"
    SCHEMA_VERSION = 1
    MAX_RECEIPT_BYTES = 64 * 1024

    def __init__(self, workspace: Path) -> None:
        self.root = workspace / "diagnostics" / "host-repair-receipts"
        self.latest_path = self.root / "latest.romverse-adb-host-repair.json"

    def write(
        self,
        plan: AdbHostRepairPlan,
        status: AdbHostRepairStatus,
        steps: tuple[dict[str, object], ...],
    ) -> tuple[str, str]:
        unsigned: dict[str, object] = {
            "format": self.FORMAT,
            "schema_version": self.SCHEMA_VERSION,
            "receipt_id": uuid4().hex,
            "recorded_at": datetime.now(UTC).isoformat(),
            "plan_digest": plan.digest(),
            "mode": plan.mode.value,
            "status": status.value,
            "steps": list(steps),
            "device_commands_executed": False,
            "phone_changed": False,
            "execution_authority": "host-adb-daemon-only",
            "bootloader_relock": "never",
        }
        digest = hashlib.sha256(_canonical(unsigned)).hexdigest()
        payload = {**unsigned, "receipt_digest": digest}
        history = self.root / f"{unsigned['receipt_id']}.romverse-adb-host-repair.json"
        self._atomic_write(history, payload)
        self._atomic_write(self.latest_path, payload)
        evidence_ref = history.relative_to(self.root.parent.parent).as_posix()
        return digest, evidence_ref

    def load_latest(self) -> AdbHostRepairReceiptReview:
        if not os.path.lexists(self.latest_path):
            return AdbHostRepairReceiptReview(False, False, "No ADB host repair receipt exists")
        try:
            payload = read_json_object(
                self.latest_path,
                boundary=self.root.parent.parent,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
            expected = str(payload.pop("receipt_digest", ""))
            self._validate_payload(payload)
            if (
                payload.get("device_commands_executed") is not False
                or payload.get("phone_changed") is not False
                or payload.get("execution_authority") != "host-adb-daemon-only"
                or payload.get("bootloader_relock") != "never"
                or not _sha256_value(expected)
                or expected != hashlib.sha256(_canonical(payload)).hexdigest()
            ):
                raise ValueError("receipt integrity or safety boundary is invalid")
            restored = {**payload, "receipt_digest": expected}
            return AdbHostRepairReceiptReview(
                True,
                True,
                "SHA-256 repair receipt verified",
                restored,
            )
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            return AdbHostRepairReceiptReview(False, False, f"Repair receipt rejected: {exc}")

    def _validate_payload(self, payload: dict[str, object]) -> None:
        expected_keys = {
            "format",
            "schema_version",
            "receipt_id",
            "recorded_at",
            "plan_digest",
            "mode",
            "status",
            "steps",
            "device_commands_executed",
            "phone_changed",
            "execution_authority",
            "bootloader_relock",
        }
        if (
            set(payload) != expected_keys
            or payload.get("format") != self.FORMAT
            or payload.get("schema_version") != self.SCHEMA_VERSION
            or payload.get("mode") not in {item.value for item in AdbHostRepairMode}
            or payload.get("status") not in {item.value for item in AdbHostRepairStatus}
            or not _sha256_value(str(payload.get("plan_digest", "")))
        ):
            raise ValueError("receipt schema is invalid")
        receipt_id = str(payload.get("receipt_id", ""))
        if len(receipt_id) != 32 or any(
            character not in "0123456789abcdef" for character in receipt_id
        ):
            raise ValueError("receipt identity is invalid")
        _aware_timestamp(payload.get("recorded_at"))
        steps = payload.get("steps")
        if not isinstance(steps, list) or not 1 <= len(steps) <= 3:
            raise ValueError("receipt step collection is invalid")
        allowed_steps = {"kill-server", "start-server", "verify-devices"}
        for step in steps:
            if not isinstance(step, dict) or set(step) != {
                "step",
                "returncode",
                "timed_out",
                "output_digest",
            }:
                raise ValueError("receipt step is invalid")
            if (
                step.get("step") not in allowed_steps
                or not isinstance(step.get("returncode"), int)
                or not isinstance(step.get("timed_out"), bool)
                or not _sha256_value(str(step.get("output_digest", "")))
            ):
                raise ValueError("receipt step evidence is invalid")

    def _atomic_write(self, path: Path, payload: dict[str, object]) -> None:
        atomic_write_json(
            path,
            payload,
            boundary=self.root.parent.parent,
            maximum_bytes=self.MAX_RECEIPT_BYTES,
        )


class AdbHostRepairService:
    """Exact host-daemon recovery with no Android-device command surface."""

    def __init__(
        self,
        executable: Path,
        gateway: ExecutionGateway,
        approvals: ApprovalStore,
        receipts: AdbHostRepairReceiptStore,
    ) -> None:
        self.executable = executable
        self.gateway = gateway
        self.approvals = approvals
        self.receipts = receipts

    def plan(self, mode: AdbHostRepairMode, reason: str) -> AdbHostRepairPlan:
        return create_adb_host_repair_plan(self.executable, mode, reason)

    def approve(self, plan: AdbHostRepairPlan) -> None:
        self._validate(plan)
        self.approvals.issue(plan.digest(), plan.target)

    def execute(self, plan: AdbHostRepairPlan) -> AdbHostRepairResult:
        self._validate(plan)
        digest = plan.digest()
        if not self.approvals.is_approved(digest, plan.target):
            raise AdbHostRepairError("ADB host recovery has not been approved for this exact plan")

        steps: list[dict[str, object]] = []
        kill_ok = True
        if plan.mode is AdbHostRepairMode.RESTART:
            kill = self._execute_step(plan, "repair.adb_kill_server", ("kill-server",))
            steps.append(_step_receipt("kill-server", kill))
            kill_ok = kill.ok

        # Even after an unsuccessful kill, starting the daemon is the safest bounded
        # restoration attempt. No command below addresses a phone or accepts input.
        start = self._execute_step(plan, "repair.adb_start_server", ("start-server",))
        steps.append(_step_receipt("start-server", start))
        verification: CommandResult | None = None
        if start.ok:
            verification = self._execute_step(
                plan,
                "adb.devices",
                ("devices", "-l"),
                category=OperationClass.READ_ONLY,
            )
            steps.append(_step_receipt("verify-devices", verification))

        if not start.ok or verification is None or not verification.ok:
            status = AdbHostRepairStatus.FAILED
            summary = (
                "ADB host recovery stopped safely. The daemon did not pass its read-only "
                "verification; ROMVERSE did not run a phone command."
            )
        elif not kill_ok:
            status = AdbHostRepairStatus.ATTENTION
            summary = (
                "ADB is responding again, but the old daemon did not confirm a clean stop. "
                "ROMVERSE will rescan before claiming the connection recovered."
            )
        else:
            status = AdbHostRepairStatus.SUCCEEDED
            summary = (
                "The host ADB daemon restarted and passed a fresh read-only device-list check. "
                "ROMVERSE will now rescan the connection."
            )

        receipt_saved = True
        receipt_digest = ""
        receipt_ref = ""
        try:
            receipt_digest, receipt_ref = self.receipts.write(plan, status, tuple(steps))
        except OSError:
            receipt_saved = False
        return AdbHostRepairResult(
            status,
            summary,
            receipt_saved,
            receipt_digest,
            receipt_ref,
        )

    def _execute_step(
        self,
        plan: AdbHostRepairPlan,
        operation_id: str,
        arguments: tuple[str, ...],
        *,
        category: OperationClass = OperationClass.STATE_CHANGING,
    ) -> CommandResult:
        request = OperationRequest(
            operation_id=operation_id,
            category=category,
            executable=plan.executable_path,
            arguments=arguments,
            purpose="Recover and verify the host ADB daemon without changing a phone",
            target=plan.target if category is OperationClass.STATE_CHANGING else "host",
            approval_digest=plan.digest() if category is OperationClass.STATE_CHANGING else "",
            approval_target=plan.target if category is OperationClass.STATE_CHANGING else "",
        )
        return self.gateway.execute(request, timeout=15)

    def _validate(self, plan: AdbHostRepairPlan) -> None:
        try:
            created = datetime.fromisoformat(plan.created_at)
            if created.tzinfo is None:
                raise ValueError("timestamp has no timezone")
            created = created.astimezone(UTC)
        except (TypeError, ValueError) as exc:
            raise AdbHostRepairError("ADB host repair plan timestamp is invalid") from exc
        age = datetime.now(UTC) - created
        if (
            plan.schema_version != 1
            or plan.target != ADB_HOST_REPAIR_TARGET
            or plan.phone_changed
            or plan.execution_authority != "host-adb-daemon-only"
            or plan.bootloader_relock != "never"
            or plan.mode not in {AdbHostRepairMode.START, AdbHostRepairMode.RESTART}
            or age < timedelta(0)
            or age > ApprovalStore.VALID_FOR
        ):
            raise AdbHostRepairError("ADB host repair plan failed its safety contract")
        _bounded_text(plan.reason, "repair reason", 400)
        path = Path(plan.executable_path)
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise AdbHostRepairError(f"Approved ADB executable is unavailable: {exc}") from exc
        if (
            resolved != path
            or not resolved.is_file()
            or not os.access(resolved, os.X_OK)
            or resolved.name.casefold() not in {"adb", "adb.exe"}
            or _sha256_file(resolved) != plan.executable_sha256
        ):
            raise AdbHostRepairError("ADB executable changed after the repair plan was created")


def _step_receipt(label: str, result: CommandResult) -> dict[str, object]:
    return {
        "step": label,
        "returncode": result.returncode,
        "timed_out": result.timed_out,
        "output_digest": hashlib.sha256(
            (result.stdout + "\n" + result.stderr).encode("utf-8", errors="replace")
        ).hexdigest(),
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bounded_text(value: object, label: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise AdbHostRepairError(f"{label} must be text")
    clean = value.replace("\x00", " ").strip()
    if not clean or len(clean) > maximum or any(ord(character) < 32 for character in clean):
        raise AdbHostRepairError(f"{label} must contain 1-{maximum} printable characters")
    return clean


def _canonical(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_value(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _aware_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be text")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("timestamp requires a timezone")
    return parsed.astimezone(UTC)
