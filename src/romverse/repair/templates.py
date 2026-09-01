from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from romverse.device.models import AndroidDevice, DeviceState
from romverse.diagnostics.models import DiagnosticReport, Finding, Severity
from romverse.guardian.models import OperationClass
from romverse.guardian.planning import (
    CheckStatus,
    OperationManifest,
    PlannedStep,
    Precondition,
)


class RepairConcern(StrEnum):
    BATTERY_HEAT = "Battery drain or overheating"
    STORAGE = "Storage or update-space problem"
    USB_ADB = "USB or ADB connection problem"
    APP_CRASH = "App crashes or instability"
    BOOT_UPDATE = "Boot or system-update problem"
    DISPLAY_TOUCH = "Display or touch problem"
    NETWORK = "Wi-Fi, Bluetooth, or mobile network problem"
    CAMERA_AUDIO = "Camera, microphone, or speaker problem"
    PERFORMANCE = "Slow performance or freezing"


DIAGNOSTIC_REPAIR_CONCERNS = {
    "battery.low": RepairConcern.BATTERY_HEAT,
    "battery.temperature": RepairConcern.BATTERY_HEAT,
    "storage.capacity": RepairConcern.STORAGE,
    "connection.unavailable": RepairConcern.USB_ADB,
    "scan.partial": RepairConcern.USB_ADB,
    "boot.incomplete": RepairConcern.BOOT_UPDATE,
    "boot.recent": RepairConcern.BOOT_UPDATE,
    "security.patch_age": RepairConcern.BOOT_UPDATE,
    "security.bootloader": RepairConcern.BOOT_UPDATE,
    "security.verified_boot": RepairConcern.BOOT_UPDATE,
    "security.root": RepairConcern.BOOT_UPDATE,
    "security.root_manager_candidate": RepairConcern.BOOT_UPDATE,
}


def concern_for_finding(finding_id: str) -> RepairConcern | None:
    """Return the exact guided-repair category for one typed diagnostic finding."""

    return DIAGNOSTIC_REPAIR_CONCERNS.get(finding_id.strip()[:120])


def actionable_repair_finding(report: DiagnosticReport | None) -> Finding | None:
    """Select the highest-priority current finding that has an exact repair route."""

    if report is None:
        return None
    ranking = {
        Severity.ADVISORY: 1,
        Severity.WARNING: 2,
        Severity.CRITICAL: 3,
    }
    candidates = tuple(
        finding
        for finding in report.findings
        if finding.severity in ranking and concern_for_finding(finding.finding_id) is not None
    )
    return max(candidates, key=lambda item: ranking[item.severity], default=None)


class RepairAssessmentTemplates:
    def build(
        self,
        concern: RepairConcern,
        device: AndroidDevice,
        report: DiagnosticReport,
    ) -> OperationManifest:
        preconditions = list(self._base_preconditions(device))
        if concern is RepairConcern.BATTERY_HEAT:
            preconditions.extend(
                (
                    self._known(
                        "battery.level",
                        "Battery level available",
                        device.battery_percent,
                        f"{device.battery_percent}%"
                        if device.battery_percent is not None
                        else "Unavailable",
                    ),
                    self._known(
                        "battery.temperature",
                        "Battery temperature available",
                        device.battery_temperature_c,
                        f"{device.battery_temperature_c} °C"
                        if device.battery_temperature_c is not None
                        else "Unavailable",
                    ),
                )
            )
        elif concern is RepairConcern.STORAGE:
            preconditions.append(
                self._known(
                    "storage.capacity",
                    "Storage capacity evidence available",
                    device.storage.percent_used,
                    f"{device.storage.percent_used}% used"
                    if device.storage.percent_used is not None
                    else "Unavailable",
                )
            )
        elif concern is RepairConcern.BOOT_UPDATE:
            preconditions.append(
                self._known(
                    "boot.state",
                    "Boot security state available",
                    device.bootloader_locked,
                    "Known" if device.bootloader_locked is not None else "Unavailable",
                )
            )

        action_category = (
            OperationClass.PRIVILEGED
            if concern is RepairConcern.BOOT_UPDATE
            else OperationClass.STATE_CHANGING
        )
        related = tuple(
            finding.title for finding in report.findings if finding.finding_id != "baseline.clear"
        )
        related_text = ", ".join(related) or "No matching warning in current baseline evidence"
        steps = (
            PlannedStep(
                "inspect",
                "Inspect existing evidence",
                related_text,
                OperationClass.READ_ONLY,
                "No device changes",
                True,
            ),
            PlannedStep(
                "simulate",
                "Build and review a diagnostic hypothesis",
                "Relate the selected concern to captured evidence and identify missing facts.",
                OperationClass.READ_ONLY,
                "No device changes",
                True,
            ),
            PlannedStep(
                "future-action",
                "Review a specific recovery route",
                "ROMVERSE presents model-aware guidance only after the evidence and compatibility checks above; no generic device command is invented.",
                action_category,
                "Guided user action only; device execution remains locked",
                None,
            ),
            PlannedStep(
                "verify",
                "Verify outcome against a new baseline",
                "Repeat read-only evidence collection and compare it with the saved pre-repair report.",
                OperationClass.READ_ONLY,
                "No device changes",
                True,
            ),
        )
        return OperationManifest(
            schema_version=1,
            manifest_id=str(uuid4()),
            created_at=datetime.now(UTC).isoformat(),
            title=f"Repair assessment: {concern.value}",
            concern=concern.value,
            target="local-pseudonymous-device",
            preconditions=tuple(preconditions),
            steps=steps,
        )

    @staticmethod
    def _base_preconditions(device: AndroidDevice) -> tuple[Precondition, ...]:
        connection = CheckStatus.PASS if device.state is DeviceState.DEVICE else CheckStatus.FAIL
        connection_evidence = f"ADB state: {device.state.value}"
        if device.connection_note:
            connection_evidence += f" • {device.connection_note}"
        coverage = CheckStatus.PASS if not device.errors else CheckStatus.UNKNOWN
        if device.battery_percent is None:
            battery = CheckStatus.UNKNOWN
            battery_evidence = "Unavailable"
        elif device.battery_percent >= 30:
            battery = CheckStatus.PASS
            battery_evidence = f"{device.battery_percent}%"
        else:
            battery = CheckStatus.FAIL
            battery_evidence = f"{device.battery_percent}% — charge to at least 30%"
        return (
            Precondition(
                "connection.authorized",
                "Authorized ADB connection",
                connection,
                connection_evidence,
            ),
            Precondition(
                "scan.coverage",
                "Required read-only probes completed",
                coverage,
                "Complete" if not device.errors else f"{len(device.errors)} probe errors",
            ),
            Precondition(
                "battery.safety",
                "Battery safety threshold for future operations",
                battery,
                battery_evidence,
            ),
        )

    @staticmethod
    def _known(
        check_id: str,
        title: str,
        value: object | None,
        evidence: str,
    ) -> Precondition:
        return Precondition(
            check_id,
            title,
            CheckStatus.PASS if value is not None else CheckStatus.UNKNOWN,
            evidence,
        )
