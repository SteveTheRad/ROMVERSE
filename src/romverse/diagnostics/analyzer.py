from __future__ import annotations

from datetime import UTC, date, datetime

from romverse.device.models import AndroidDevice, DeviceState
from romverse.device.root_identity import review_root_identity
from romverse.diagnostics.models import DiagnosticReport, Evidence, Finding, Severity


class DiagnosticAnalyzer:
    """Converts a read-only device snapshot into evidence-backed findings."""

    def __init__(self, today: date | None = None) -> None:
        self.today = today or datetime.now(UTC).date()

    def analyze(self, device: AndroidDevice) -> DiagnosticReport:
        evidence = self._evidence(device)
        findings: list[Finding] = []
        score = 100

        if device.state is not DeviceState.DEVICE:
            severity = (
                Severity.WARNING if device.state is DeviceState.UNAUTHORIZED else Severity.CRITICAL
            )
            findings.append(
                Finding(
                    "connection.unavailable",
                    severity,
                    "Detailed inspection unavailable",
                    device.connection_note or f"ADB reports the device as {device.state.value}.",
                    ("connection.state",),
                    "Restore an authorized ADB connection, then scan again.",
                )
            )
            score = 40 if severity is Severity.WARNING else 20
            return self._report(device, score, evidence, findings)

        if device.battery_percent is not None and device.battery_percent <= 15:
            severity = Severity.CRITICAL if device.battery_percent <= 5 else Severity.WARNING
            findings.append(
                Finding(
                    "battery.low",
                    severity,
                    "Battery level is low",
                    "Low charge increases interruption risk for later maintenance workflows.",
                    ("battery.level",),
                    "Charge the phone before any future long-running or privileged operation.",
                )
            )
            score -= 25 if severity is Severity.CRITICAL else 12

        temperature = device.battery_temperature_c
        if temperature is not None and temperature >= 40:
            severity = Severity.CRITICAL if temperature >= 45 else Severity.WARNING
            findings.append(
                Finding(
                    "battery.temperature",
                    severity,
                    "Battery temperature is elevated",
                    "The reported battery temperature is above ROMVERSE's conservative review threshold.",
                    ("battery.temperature",),
                    "Let the device cool in a ventilated place and investigate sustained heat.",
                )
            )
            score -= 30 if severity is Severity.CRITICAL else 15

        used = device.storage.percent_used
        if used is not None and used >= 90:
            severity = Severity.CRITICAL if used >= 97 else Severity.WARNING
            findings.append(
                Finding(
                    "storage.capacity",
                    severity,
                    "Device storage is nearly full",
                    "Very low free space can cause updates, apps, and Android services to fail.",
                    ("storage.used",),
                    "Review large files and app storage before attempting repair or build transfer workflows.",
                )
            )
            score -= 25 if severity is Severity.CRITICAL else 12

        patch_age = self._patch_age_days(device.security_patch)
        if patch_age is not None and patch_age > 180:
            severity = Severity.WARNING if patch_age > 365 else Severity.ADVISORY
            findings.append(
                Finding(
                    "security.patch_age",
                    severity,
                    "Android security patch is aging",
                    f"The reported security patch is {patch_age} days old.",
                    ("security.patch",),
                    "Check the OEM's official update channel; availability varies by model and region.",
                )
            )
            score -= 12 if severity is Severity.WARNING else 5

        if device.bootloader_locked is False:
            findings.append(
                Finding(
                    "security.bootloader",
                    Severity.ADVISORY,
                    "Bootloader is reported unlocked",
                    "An unlocked bootloader may be intentional, but changes the device's security posture.",
                    ("security.bootloader",),
                    "No action is proposed. Confirm this state is expected for this device.",
                )
            )
            score -= 5

        if device.verified_boot.lower() in {"orange", "yellow", "red"}:
            severity = (
                Severity.WARNING if device.verified_boot.lower() == "red" else Severity.ADVISORY
            )
            findings.append(
                Finding(
                    "security.verified_boot",
                    severity,
                    "Verified Boot reports a non-green state",
                    "This can be expected on modified devices, but must be understood before future operations.",
                    ("security.verified_boot",),
                    "Compare the state with the device's intended firmware and bootloader configuration.",
                )
            )
            score -= 15 if severity is Severity.WARNING else 5

        root_review = review_root_identity(
            device.root_detected,
            device.root_manager_candidate,
            root_signal_source=device.root_signal_source,
            manager_evidence=device.root_manager_evidence,
        )
        if device.root_detected is True:
            findings.append(
                Finding(
                    "security.root",
                    Severity.ADVISORY,
                    root_review.title,
                    root_review.summary + " ROMVERSE did not request elevation.",
                    ("security.adb_identity", "security.root_manager"),
                    root_review.next_action,
                )
            )
            score -= 5
        elif device.root_manager_candidate in {"magisk", "kernelsu_lkm", "conflict"}:
            findings.append(
                Finding(
                    "security.root_manager_candidate",
                    Severity.INFORMATION,
                    root_review.title,
                    root_review.summary,
                    ("security.adb_identity", "security.root_manager"),
                    root_review.next_action,
                )
            )

        if device.boot_completed is False:
            findings.append(
                Finding(
                    "boot.incomplete",
                    Severity.WARNING,
                    "Android has not reported boot completion",
                    "ADB is available, but sys.boot_completed is not set. This can be temporary during first boot or evidence of a userspace startup problem.",
                    ("boot.completed", "boot.uptime", "boot.slot"),
                    "Allow a declared first-boot window, then rescan. If uptime repeatedly resets or completion remains false, preserve logs and use the exact supported recovery route.",
                )
            )
            score -= 20
        elif device.uptime_seconds is not None and device.uptime_seconds < 300:
            findings.append(
                Finding(
                    "boot.recent",
                    Severity.INFORMATION,
                    "Device booted recently",
                    "The uptime sample is under five minutes. Services and app optimization may still be settling.",
                    ("boot.completed", "boot.uptime", "boot.slot"),
                    "Keep the device connected and compare another read-only scan after several minutes.",
                )
            )

        if device.errors:
            findings.append(
                Finding(
                    "scan.partial",
                    Severity.INFORMATION,
                    "Diagnostic coverage is partial",
                    "One or more read-only probes did not return data, so absence of a finding is not conclusive.",
                    ("scan.errors",),
                    "Review the partial-scan details in Device Portal and scan again if needed.",
                )
            )

        if not findings:
            findings.append(
                Finding(
                    "baseline.clear",
                    Severity.HEALTHY,
                    "No concerning signals found",
                    "Available read-only signals are within ROMVERSE's baseline review thresholds.",
                    tuple(item.evidence_id for item in evidence),
                    "Continue normal monitoring. This is not a guarantee of complete device health.",
                )
            )
        return self._report(device, max(0, score), evidence, findings)

    def _report(
        self,
        device: AndroidDevice,
        score: int,
        evidence: tuple[Evidence, ...],
        findings: list[Finding],
    ) -> DiagnosticReport:
        concerning = sum(
            item.severity in {Severity.WARNING, Severity.CRITICAL} for item in findings
        )
        advisories = sum(item.severity is Severity.ADVISORY for item in findings)
        if concerning:
            summary = f"{concerning} signal{'s' if concerning != 1 else ''} need attention"
        elif advisories:
            summary = (
                f"{advisories} advisory signal{'s' if advisories != 1 else ''} to review; "
                "no warnings"
            )
        else:
            summary = "No concerning signals in available evidence"
        limitations = (
            "This report uses read-only ADB observations and is not a full hardware diagnostic.",
            "Threshold findings are guidance, not medical, electrical, security, or repair guarantees.",
            "Unavailable evidence is never treated as proof that a condition is absent.",
        )
        return DiagnosticReport(
            1,
            datetime.now(UTC).isoformat(),
            device.display_name,
            score,
            summary,
            evidence,
            tuple(findings),
            limitations,
        )

    @staticmethod
    def _evidence(device: AndroidDevice) -> tuple[Evidence, ...]:
        values = (
            ("connection.state", "ADB state", device.state.value, "adb devices -l"),
            ("battery.level", "Battery level", _percent(device.battery_percent), "dumpsys battery"),
            (
                "battery.temperature",
                "Battery temperature",
                _temperature(device.battery_temperature_c),
                "dumpsys battery",
            ),
            ("storage.used", "Storage used", _percent(device.storage.percent_used), "df /data"),
            ("security.patch", "Security patch", device.security_patch or "Unavailable", "getprop"),
            (
                "security.bootloader",
                "Bootloader locked",
                _boolean(device.bootloader_locked),
                "getprop",
            ),
            (
                "security.verified_boot",
                "Verified Boot",
                device.verified_boot or "Unavailable",
                "getprop",
            ),
            ("security.adb_identity", "ADB root identity", _boolean(device.root_detected), "id"),
            (
                "security.root_manager",
                "Root Manager candidate",
                device.root_manager_candidate.replace("_", " "),
                device.root_manager_evidence or "Unavailable",
            ),
            (
                "boot.completed",
                "Android boot completed",
                _boolean(device.boot_completed),
                "getprop sys.boot_completed",
            ),
            (
                "boot.uptime",
                "Device uptime",
                _duration(device.uptime_seconds),
                "cat /proc/uptime",
            ),
            ("boot.slot", "Active slot", device.slot_suffix or "Unavailable", "getprop"),
            ("scan.errors", "Probe errors", str(len(device.errors)), "Device Engine"),
        )
        return tuple(Evidence(*value) for value in values)

    def _patch_age_days(self, value: str) -> int | None:
        try:
            patch_date = date.fromisoformat(value)
        except ValueError:
            return None
        return max(0, (self.today - patch_date).days)


def _percent(value: int | None) -> str:
    return f"{value}%" if value is not None else "Unavailable"


def _temperature(value: float | None) -> str:
    return f"{value:.1f} °C" if value is not None else "Unavailable"


def _boolean(value: bool | None) -> str:
    return "Unknown" if value is None else "Yes" if value else "No"


def _duration(value: int | None) -> str:
    if value is None:
        return "Unavailable"
    days, remainder = divmod(value, 24 * 60 * 60)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    prefix = f"{days}d " if days else ""
    return f"{prefix}{hours:02d}:{minutes:02d}:{seconds:02d}"
