from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from romverse.companion.usb_contract import (
    usb_launch_arguments,
    usb_operation_digest,
    usb_reverse_arguments,
    usb_reverse_remove_arguments,
    validate_usb_pairing_values,
)
from romverse.core.privacy import WorkspacePrivacy
from romverse.guardian.approval import ApprovalRecord, ApprovalStore
from romverse.guardian.gateway import ExecutionGateway
from romverse.guardian.models import GuardianDeniedError, OperationClass, OperationRequest
from romverse.infrastructure.process import CommandResult


@dataclass(frozen=True, slots=True)
class UsbPairingAssistPlan:
    serial: str
    target_key: str
    port: int
    certificate_sha256: str
    pairing_code: str
    expires_at: str

    def arguments_for(self, operation_id: str) -> tuple[str, ...]:
        if operation_id == "companion.usb_reverse":
            return usb_reverse_arguments(self.serial, self.port)
        if operation_id == "companion.usb_launch":
            return usb_launch_arguments(
                self.serial,
                self.port,
                self.certificate_sha256,
                self.pairing_code,
            )
        if operation_id == "companion.usb_reverse_remove":
            return usb_reverse_remove_arguments(self.serial, self.port)
        raise ValueError("Unknown USB pairing operation")

    def digest_for(self, operation_id: str) -> str:
        return usb_operation_digest(operation_id, self.arguments_for(operation_id))


@dataclass(frozen=True, slots=True)
class UsbPairingAssistResult:
    reverse: CommandResult
    launch: CommandResult | None = None
    cleanup: CommandResult | None = None

    @property
    def ok(self) -> bool:
        return self.reverse.ok and self.launch is not None and self.launch.ok

    @property
    def detail(self) -> str:
        if not self.reverse.ok:
            return "ROMVERSE could not create the private USB Link tunnel."
        if self.launch is None or not self.launch.ok:
            return "ROMVERSE could not open the Companion confirmation on this phone."
        return "Companion is showing the Link safety-code confirmation."


class UsbPairingAssistService:
    """Open a one-phone Link confirmation through an explicitly approved USB tunnel."""

    _OPERATIONS = (
        "companion.usb_reverse",
        "companion.usb_launch",
        "companion.usb_reverse_remove",
    )

    def __init__(
        self,
        executable: Path,
        gateway: ExecutionGateway,
        approvals: ApprovalStore,
        workspace: Path,
    ) -> None:
        self.executable = str(executable)
        self.gateway = gateway
        self.approvals = approvals
        self.privacy = WorkspacePrivacy(workspace)

    def prepare(
        self,
        *,
        serial: str,
        port: int,
        certificate_sha256: str,
        pairing_code: str,
        expires_at: str,
    ) -> UsbPairingAssistPlan:
        serial, port, fingerprint, code = validate_usb_pairing_values(
            serial,
            port,
            certificate_sha256,
            pairing_code,
        )
        expiry = _timestamp(expires_at)
        if expiry <= datetime.now(UTC):
            raise ValueError("USB pairing code has already expired")
        return UsbPairingAssistPlan(
            serial=serial,
            target_key=self.privacy.pseudonym(serial),
            port=port,
            certificate_sha256=fingerprint,
            pairing_code=code,
            expires_at=expiry.isoformat(),
        )

    def approve(self, plan: UsbPairingAssistPlan) -> tuple[ApprovalRecord, ...]:
        self._validate(plan)
        return tuple(
            self.approvals.issue(plan.digest_for(operation_id), plan.target_key)
            for operation_id in self._OPERATIONS
        )

    def launch(self, plan: UsbPairingAssistPlan) -> UsbPairingAssistResult:
        self._validate(plan)
        for operation_id in self._OPERATIONS:
            if not self.approvals.is_approved(
                plan.digest_for(operation_id),
                plan.target_key,
            ):
                raise GuardianDeniedError(
                    "USB-assisted pairing has not been approved for this exact phone and request"
                )
        reverse = self.gateway.execute(self._request(plan, "companion.usb_reverse"))
        if not reverse.ok:
            return UsbPairingAssistResult(reverse)
        launch = self.gateway.execute(self._request(plan, "companion.usb_launch"), timeout=15)
        cleanup = None
        if not launch.ok:
            cleanup = self.gateway.execute(self._request(plan, "companion.usb_reverse_remove"))
        return UsbPairingAssistResult(reverse, launch, cleanup)

    def _validate(self, plan: UsbPairingAssistPlan) -> None:
        validate_usb_pairing_values(
            plan.serial,
            plan.port,
            plan.certificate_sha256,
            plan.pairing_code,
        )
        if plan.target_key != self.privacy.pseudonym(plan.serial):
            raise GuardianDeniedError("USB pairing target no longer matches the selected phone")
        if _timestamp(plan.expires_at) <= datetime.now(UTC):
            raise GuardianDeniedError("USB pairing request expired before it was confirmed")

    def _request(self, plan: UsbPairingAssistPlan, operation_id: str) -> OperationRequest:
        return OperationRequest(
            operation_id=operation_id,
            category=OperationClass.STATE_CHANGING,
            executable=self.executable,
            arguments=plan.arguments_for(operation_id),
            purpose="Open the user-confirmed read-only ROMVERSE Link pairing on one USB phone",
            target=plan.serial,
            approval_digest=plan.digest_for(operation_id),
            approval_target=plan.target_key,
        )


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("USB pairing expiry must include a timezone")
    return parsed.astimezone(UTC)
