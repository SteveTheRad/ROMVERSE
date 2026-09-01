from __future__ import annotations

from datetime import date

from romverse.device.models import DeviceState, StorageInfo
from romverse.diagnostics.analyzer import DiagnosticAnalyzer
from romverse.diagnostics.models import Finding, Severity
from romverse.knowledge.advisor import (
    DIAGNOSTIC_ARTICLE_KEYS,
    REPAIR_CONCERN_ARTICLE_KEYS,
    article_for_key,
    recommend_for_findings,
    recommend_for_repair,
)
from romverse.repair.templates import RepairConcern

from .test_diagnostics import device


def test_every_advisor_rule_resolves_to_a_structured_article() -> None:
    keys = set(DIAGNOSTIC_ARTICLE_KEYS.values()) | set(REPAIR_CONCERN_ARTICLE_KEYS.values())

    assert keys
    assert all(article_for_key(key) is not None for key in keys)
    assert set(REPAIR_CONCERN_ARTICLE_KEYS) == set(RepairConcern)


def test_diagnostics_recommend_exact_guides_in_severity_and_evidence_order() -> None:
    report = DiagnosticAnalyzer(date(2026, 9, 1)).analyze(
        device(
            battery_percent=4,
            battery_temperature_c=46.5,
            storage=StorageInfo(percent_used=98),
        )
    )

    recommendations = recommend_for_findings(report.findings, limit=3)

    assert [item.article.key for item in recommendations] == [
        "device-battery-low",
        "device-temperature-elevated",
        "device-storage-nearly-full",
    ]
    assert recommendations[0].reason == "Exact diagnostic rule: battery.low"


def test_connection_finding_uses_exact_adb_state_language() -> None:
    unauthorized = Finding(
        "connection.unavailable",
        Severity.WARNING,
        "Detailed inspection unavailable",
        "ADB reports the device as unauthorized.",
        ("connection.state",),
        "Unlock the phone and accept the RSA prompt.",
    )
    offline = Finding(
        "connection.unavailable",
        Severity.CRITICAL,
        "Detailed inspection unavailable",
        "ADB reports the device as offline.",
        ("connection.state",),
    )

    assert recommend_for_findings((unauthorized,), limit=1)[0].article.key == "adb-unauthorized"
    assert recommend_for_findings((offline,), limit=1)[0].article.key == "adb-device-offline"


def test_exact_error_code_overrides_generic_repair_concern() -> None:
    recommendations = recommend_for_repair(
        RepairConcern.STORAGE,
        "INSTALL_FAILED_VERSION_DOWNGRADE",
        limit=3,
    )

    assert recommendations[0].article.key == "apk-version-downgrade"
    assert recommendations[0].reason == "Exact symptom or error match"
    assert recommendations[1].article.key == "device-storage-nearly-full"


def test_unknown_symptom_falls_back_to_exact_concern_without_guessing() -> None:
    recommendations = recommend_for_repair(
        RepairConcern.NETWORK,
        "an unclassified but bounded symptom phrase",
        limit=8,
    )

    assert [item.article.key for item in recommendations] == ["android-network-triage"]
    assert recommend_for_repair(RepairConcern.NETWORK, limit=0) == ()


def test_each_repair_concern_has_one_exact_primary_guide() -> None:
    for concern in RepairConcern:
        recommendation = recommend_for_repair(concern, limit=1)
        assert len(recommendation) == 1
        assert recommendation[0].article.key == REPAIR_CONCERN_ARTICLE_KEYS[concern]


def test_unauthorized_analyzer_report_reaches_authorization_guide() -> None:
    report = DiagnosticAnalyzer(date(2026, 9, 1)).analyze(
        device(
            state=DeviceState.UNAUTHORIZED,
            connection_note="Unlock the phone and accept the RSA authorization prompt",
        )
    )

    assert recommend_for_findings(report.findings, limit=1)[0].article.key == "adb-unauthorized"
