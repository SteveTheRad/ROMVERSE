from __future__ import annotations

from time import monotonic

from romverse.guardian.audit import AuditSink
from romverse.guardian.models import GuardianDeniedError, OperationRequest
from romverse.guardian.policy import MilestoneOnePolicy
from romverse.infrastructure.process import CommandResult, CommandRunner


class ExecutionGateway:
    """The only route from a typed operation request to local process execution."""

    def __init__(
        self,
        policy: MilestoneOnePolicy,
        runner: CommandRunner,
        audit: AuditSink | None = None,
    ) -> None:
        self.policy = policy
        self.runner = runner
        self.audit = audit

    def execute(self, request: OperationRequest, timeout: float = 10) -> CommandResult:
        decision = self.policy.assess(request)
        if self.audit is not None:
            self.audit.assert_ready()
        if not decision.allowed:
            if self.audit is not None:
                self.audit.record(request, decision, None, 0)
            raise GuardianDeniedError("; ".join(decision.reasons))
        started = monotonic()
        try:
            result = self.runner.run((request.executable, *request.arguments), timeout=timeout)
        except Exception as exc:
            if self.audit is not None:
                self.audit.record(
                    request,
                    decision,
                    None,
                    int((monotonic() - started) * 1000),
                    type(exc).__name__,
                )
            raise
        if self.audit is not None:
            self.audit.record(
                request,
                decision,
                result,
                int((monotonic() - started) * 1000),
            )
        return result
