from dataclasses import replace

from romverse.device.models import StorageInfo
from romverse.diagnostics.analyzer import DiagnosticAnalyzer
from romverse.guardian.models import OperationClass, RiskLevel
from romverse.guardian.planning import (
    CheckStatus,
    GuardianPreflight,
    OperationManifest,
    PlannedStep,
    Precondition,
    PreflightStatus,
)
from romverse.repair.templates import (
    DIAGNOSTIC_REPAIR_CONCERNS,
    RepairAssessmentTemplates,
    RepairConcern,
    actionable_repair_finding,
    concern_for_finding,
)

from .test_diagnostics import device


def manifest(category=OperationClass.READ_ONLY, status=CheckStatus.PASS):
    return OperationManifest(
        1,
        "manifest-id",
        "2026-08-27T00:00:00+00:00",
        "Test plan",
        "Test concern",
        "local-pseudonymous-device",
        (Precondition("check", "Required check", status, "Evidence"),),
        (
            PlannedStep(
                "step",
                "Test step",
                "Test purpose",
                category,
                "Expected effect",
                True,
            ),
        ),
    )


def test_read_only_plan_can_be_ready_but_execution_stays_locked():
    assessment = GuardianPreflight().assess(manifest())
    assert assessment.status is PreflightStatus.READY
    assert assessment.risk is RiskLevel.NONE
    assert not assessment.approval_required
    assert assessment.execution_locked


def test_device_changing_plan_requires_review_and_approval():
    assessment = GuardianPreflight().assess(manifest(OperationClass.STATE_CHANGING))
    assert assessment.status is PreflightStatus.REVIEW
    assert assessment.risk is RiskLevel.MEDIUM
    assert assessment.approval_required
    assert assessment.execution_locked


def test_failed_required_precondition_blocks_plan():
    assessment = GuardianPreflight().assess(manifest(status=CheckStatus.FAIL))
    assert assessment.status is PreflightStatus.BLOCKED
    assert "Failed required checks" in assessment.reasons[0]


def test_manifest_digest_detects_changes():
    planner = GuardianPreflight()
    original = manifest()
    digest = original.digest()
    assert planner.verify_manifest(original, digest)
    assert not planner.verify_manifest(replace(original, title="Changed plan"), digest)


def test_repair_template_uses_live_evidence_and_never_defines_execution():
    source = device(battery_percent=75)
    report = DiagnosticAnalyzer().analyze(source)
    operation = RepairAssessmentTemplates().build(RepairConcern.BATTERY_HEAT, source, report)
    assessment = GuardianPreflight().assess(operation)
    assert all(check.status is CheckStatus.PASS for check in operation.preconditions)
    assert assessment.status is PreflightStatus.REVIEW
    assert assessment.execution_locked
    assert operation.steps[2].expected_effect == (
        "Guided user action only; device execution remains locked"
    )


def test_low_battery_blocks_future_repair_plan():
    source = device(battery_percent=12)
    operation = RepairAssessmentTemplates().build(
        RepairConcern.APP_CRASH,
        source,
        DiagnosticAnalyzer().analyze(source),
    )
    assessment = GuardianPreflight().assess(operation)
    battery = next(check for check in operation.preconditions if check.check_id == "battery.safety")
    assert battery.status is CheckStatus.FAIL
    assert assessment.status is PreflightStatus.BLOCKED


def test_boot_assessment_escalates_to_high_risk_review():
    source = device()
    operation = RepairAssessmentTemplates().build(
        RepairConcern.BOOT_UPDATE,
        source,
        DiagnosticAnalyzer().analyze(source),
    )
    assessment = GuardianPreflight().assess(operation)
    assert assessment.risk is RiskLevel.HIGH
    assert assessment.status is PreflightStatus.REVIEW


def test_every_typed_diagnostic_handoff_has_a_deterministic_repair_concern():
    expected = {
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

    assert expected == DIAGNOSTIC_REPAIR_CONCERNS
    assert all(concern_for_finding(key) is value for key, value in expected.items())
    assert concern_for_finding("baseline.clear") is None
    assert concern_for_finding("unknown.future.rule") is None


def test_repair_finding_selector_is_severity_ranked_and_actionable_only():
    analyzer = DiagnosticAnalyzer()
    report = analyzer.analyze(
        device(
            battery_percent=10,
            storage=StorageInfo(percent_used=98),
        )
    )
    selected = actionable_repair_finding(report)

    assert selected is not None
    assert selected.finding_id == "storage.capacity"
    assert actionable_repair_finding(analyzer.analyze(device(uptime_seconds=90))) is None
    assert actionable_repair_finding(None) is None
