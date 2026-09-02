from __future__ import annotations

from pathlib import Path

from romverse.guardian.gateway import ExecutionGateway
from romverse.guardian.models import OperationClass, OperationRequest
from romverse.infrastructure.process import CommandResult


class FastbootClient:
    """Guardian-routed, read-only access to Android fastboot identity evidence."""

    def __init__(self, executable: Path, gateway: ExecutionGateway) -> None:
        self.executable = str(executable)
        self.gateway = gateway

    def devices(self) -> CommandResult:
        return self._run(
            "fastboot.devices",
            ("devices", "-l"),
            "Discover Android devices in fastboot mode",
            timeout=4,
        )

    def getvar(self, serial: str, variable: str, timeout: float = 4) -> CommandResult:
        return self._run(
            f"fastboot.getvar.{variable}",
            ("-s", serial, "getvar", variable),
            f"Read fastboot identity variable: {variable}",
            serial,
            timeout,
        )

    def _run(
        self,
        operation_id: str,
        arguments: tuple[str, ...],
        purpose: str,
        target: str = "host",
        timeout: float = 10,
    ) -> CommandResult:
        request = OperationRequest(
            operation_id=operation_id,
            category=OperationClass.READ_ONLY,
            executable=self.executable,
            arguments=arguments,
            purpose=purpose,
            target=target,
        )
        return self.gateway.execute(request, timeout=timeout)
