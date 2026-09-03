from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum

from romverse.guardian.models import OperationClass, RiskLevel


class CheckStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


class PreflightStatus(StrEnum):
    READY = "ready"
    REVIEW = "review"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class Precondition:
    check_id: str
    title: str
    status: CheckStatus
    evidence: str
    required: bool = True


@dataclass(frozen=True, slots=True)
class PlannedStep:
    step_id: str
    title: str
    purpose: str
    category: OperationClass
    expected_effect: str
    reversible: bool | None


@dataclass(frozen=True, slots=True)
class OperationManifest:
    schema_version: int
    manifest_id: str
    created_at: str
    title: str
    concern: str
    target: str
    preconditions: tuple[Precondition, ...]
    steps: tuple[PlannedStep, ...]

    def digest(self) -> str:
        canonical = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PreflightAssessment:
    status: PreflightStatus
    risk: RiskLevel
    reasons: tuple[str, ...]
    approval_required: bool
    execution_locked: bool
    manifest_digest: str


class GuardianPreflight:
    """Assesses a proposed manifest without executing any step."""

    def assess(
        self, manifest: OperationManifest, *, execution_supported: bool = False
    ) -> PreflightAssessment:
        required_failures = tuple(
            check.title
            for check in manifest.preconditions
            if check.required and check.status is CheckStatus.FAIL
        )
        required_unknown = tuple(
            check.title
            for check in manifest.preconditions
            if check.required and check.status is CheckStatus.UNKNOWN
        )
        advisory_findings = tuple(
            check.title
            for check in manifest.preconditions
            if not check.required and check.status is not CheckStatus.PASS
        )
        highest = max(
            (self._risk(step.category) for step in manifest.steps),
            key=self._risk_order,
            default=RiskLevel.NONE,
        )
        has_non_read_only = any(
            step.category is not OperationClass.READ_ONLY for step in manifest.steps
        )
        has_destructive = any(
            step.category is OperationClass.DESTRUCTIVE for step in manifest.steps
        )

        reasons: list[str] = []
        if required_failures:
            reasons.append("Failed required checks: " + ", ".join(required_failures))
        if required_unknown:
            reasons.append("Evidence still required: " + ", ".join(required_unknown))
        if advisory_findings:
            reasons.append("Review advisory warnings: " + ", ".join(advisory_findings))
        if has_destructive:
            reasons.append(
                "Manifest contains a destructive step; every exact consequence requires "
                "fresh plan-bound acceptance before a supported gateway may proceed"
            )
        elif has_non_read_only:
            reasons.append("Manifest contains future device-changing or privileged steps")
        if not reasons:
            reasons.append("All available preconditions pass for a read-only plan")

        if required_failures:
            status = PreflightStatus.BLOCKED
        elif required_unknown or advisory_findings or has_non_read_only:
            status = PreflightStatus.REVIEW
        else:
            status = PreflightStatus.READY
        return PreflightAssessment(
            status=status,
            risk=highest,
            reasons=tuple(reasons),
            approval_required=has_non_read_only,
            execution_locked=not execution_supported or status is PreflightStatus.BLOCKED,
            manifest_digest=manifest.digest(),
        )

    @staticmethod
    def verify_manifest(manifest: OperationManifest, expected_digest: str) -> bool:
        return manifest.digest() == expected_digest

    @staticmethod
    def _risk(category: OperationClass) -> RiskLevel:
        return {
            OperationClass.READ_ONLY: RiskLevel.NONE,
            OperationClass.STATE_CHANGING: RiskLevel.MEDIUM,
            OperationClass.PRIVILEGED: RiskLevel.HIGH,
            OperationClass.DESTRUCTIVE: RiskLevel.CRITICAL,
        }[category]

    @staticmethod
    def _risk_order(risk: RiskLevel) -> int:
        return {
            RiskLevel.NONE: 0,
            RiskLevel.LOW: 1,
            RiskLevel.MEDIUM: 2,
            RiskLevel.HIGH: 3,
            RiskLevel.CRITICAL: 4,
        }[risk]
