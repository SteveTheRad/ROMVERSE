from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    HEALTHY = "healthy"
    INFORMATION = "information"
    ADVISORY = "advisory"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class Evidence:
    evidence_id: str
    label: str
    value: str
    source: str


@dataclass(frozen=True, slots=True)
class Finding:
    finding_id: str
    severity: Severity
    title: str
    explanation: str
    evidence_ids: tuple[str, ...]
    guidance: str = ""


@dataclass(frozen=True, slots=True)
class DiagnosticReport:
    schema_version: int
    generated_at: str
    device_name: str
    health_score: int
    summary: str
    evidence: tuple[Evidence, ...]
    findings: tuple[Finding, ...]
    limitations: tuple[str, ...]

    @property
    def highest_severity(self) -> Severity:
        ranking = {
            Severity.HEALTHY: 0,
            Severity.INFORMATION: 1,
            Severity.ADVISORY: 2,
            Severity.WARNING: 3,
            Severity.CRITICAL: 4,
        }
        return max(self.findings, key=lambda item: ranking[item.severity]).severity
