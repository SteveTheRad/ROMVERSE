from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class OperationClass(StrEnum):
    READ_ONLY = "read_only"
    STATE_CHANGING = "state_changing"
    PRIVILEGED = "privileged"
    DESTRUCTIVE = "destructive"


class RiskLevel(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class OperationRequest:
    operation_id: str
    category: OperationClass
    executable: str
    arguments: tuple[str, ...]
    purpose: str
    target: str = "host"
    approval_digest: str = ""
    approval_target: str = ""


@dataclass(frozen=True, slots=True)
class GuardianDecision:
    allowed: bool
    risk: RiskLevel
    reasons: tuple[str, ...]
    user_approval_required: bool = False


class GuardianDeniedError(PermissionError):
    pass
