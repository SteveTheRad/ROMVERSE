"""Deterministic Archives recommendations for typed ROMVERSE evidence."""

from __future__ import annotations

from dataclasses import dataclass

from romverse.diagnostics.models import Finding, Severity
from romverse.knowledge.archives import KNOWN_FIXES, ArchiveArticle, search_catalog
from romverse.repair.templates import RepairConcern


@dataclass(frozen=True, slots=True)
class ArchiveRecommendation:
    """One exact local guide match with an explainable selection reason."""

    article: ArchiveArticle
    reason: str
    finding_ids: tuple[str, ...] = ()


DIAGNOSTIC_ARTICLE_KEYS = {
    "battery.low": "device-battery-low",
    "battery.temperature": "device-temperature-elevated",
    "storage.capacity": "device-storage-nearly-full",
    "security.patch_age": "security-patch-aging",
    "security.bootloader": "bootloader-unlocked-review",
    "security.verified_boot": "verified-boot-state-review",
    "security.root": "root-signal-review",
    "security.root_manager_candidate": "root-signal-review",
    "boot.incomplete": "boot-loop-first-triage",
    "scan.partial": "unknown-is-not-healthy",
}

REPAIR_CONCERN_ARTICLE_KEYS = {
    RepairConcern.BATTERY_HEAT: "device-temperature-elevated",
    RepairConcern.STORAGE: "device-storage-nearly-full",
    RepairConcern.USB_ADB: "adb-no-device",
    RepairConcern.APP_CRASH: "android-app-crash-triage",
    RepairConcern.BOOT_UPDATE: "boot-loop-first-triage",
    RepairConcern.DISPLAY_TOUCH: "android-screen-touch-triage",
    RepairConcern.NETWORK: "android-network-triage",
    RepairConcern.CAMERA_AUDIO: "android-camera-audio-triage",
    RepairConcern.PERFORMANCE: "android-performance-freezing",
}

_ARTICLE_BY_KEY = {article.key: article for article in KNOWN_FIXES}
_REQUIRED_KEYS = frozenset(DIAGNOSTIC_ARTICLE_KEYS.values()) | frozenset(
    REPAIR_CONCERN_ARTICLE_KEYS.values()
)
if missing := _REQUIRED_KEYS.difference(_ARTICLE_BY_KEY):
    raise RuntimeError(f"Archives Advisor references missing guides: {', '.join(sorted(missing))}")

_SEVERITY_RANK = {
    Severity.HEALTHY: 0,
    Severity.INFORMATION: 1,
    Severity.ADVISORY: 2,
    Severity.WARNING: 3,
    Severity.CRITICAL: 4,
}


def article_for_key(key: str) -> ArchiveArticle | None:
    """Resolve one stable structured article identity."""

    return _ARTICLE_BY_KEY.get(key)


def _connection_key(finding: Finding) -> str:
    context = " ".join((finding.title, finding.explanation, finding.guidance)).casefold()
    if "unauthor" in context or "rsa" in context:
        return "adb-unauthorized"
    if "offline" in context:
        return "adb-device-offline"
    return "adb-no-device"


def recommend_for_findings(
    findings: tuple[Finding, ...],
    *,
    limit: int = 3,
) -> tuple[ArchiveRecommendation, ...]:
    """Map typed findings to exact guides, ordered by diagnostic severity."""

    bounded_limit = max(0, min(limit, 8))
    if not bounded_limit:
        return ()
    ordered = sorted(
        enumerate(findings),
        key=lambda indexed: (-_SEVERITY_RANK[indexed[1].severity], indexed[0]),
    )
    recommendations: list[ArchiveRecommendation] = []
    seen: set[str] = set()
    for _index, finding in ordered:
        key = (
            _connection_key(finding)
            if finding.finding_id == "connection.unavailable"
            else DIAGNOSTIC_ARTICLE_KEYS.get(finding.finding_id, "")
        )
        article = _ARTICLE_BY_KEY.get(key)
        if article is None or article.key in seen:
            continue
        seen.add(article.key)
        recommendations.append(
            ArchiveRecommendation(
                article,
                f"Exact diagnostic rule: {finding.finding_id}",
                (finding.finding_id,),
            )
        )
        if len(recommendations) >= bounded_limit:
            break
    return tuple(recommendations)


def recommend_for_repair(
    concern: RepairConcern,
    symptom: str = "",
    findings: tuple[Finding, ...] = (),
    *,
    limit: int = 3,
) -> tuple[ArchiveRecommendation, ...]:
    """Combine exact symptom, concern, and finding rules without inventing a fix."""

    bounded_limit = max(0, min(limit, 8))
    if not bounded_limit:
        return ()
    recommendations: list[ArchiveRecommendation] = []
    seen: set[str] = set()

    normalized_symptom = symptom.replace("\x00", " ").strip()[:160]
    if normalized_symptom:
        for match in search_catalog(KNOWN_FIXES, normalized_symptom, limit=bounded_limit):
            # Scores at this level require the full phrase in a structured article.
            # Lower token-overlap matches are useful for manual search, not diagnosis.
            if match.score < 650_000:
                continue
            seen.add(match.article.key)
            recommendations.append(
                ArchiveRecommendation(
                    match.article,
                    "Exact symptom or error match",
                )
            )
            if len(recommendations) >= bounded_limit:
                return tuple(recommendations)

    concern_key = REPAIR_CONCERN_ARTICLE_KEYS[concern]
    concern_article = _ARTICLE_BY_KEY[concern_key]
    if concern_article.key not in seen:
        seen.add(concern_article.key)
        recommendations.append(
            ArchiveRecommendation(
                concern_article,
                f"Exact Recovery Bay concern: {concern.value}",
            )
        )

    for recommendation in recommend_for_findings(findings, limit=bounded_limit):
        if recommendation.article.key in seen:
            continue
        seen.add(recommendation.article.key)
        recommendations.append(recommendation)
        if len(recommendations) >= bounded_limit:
            break
    return tuple(recommendations[:bounded_limit])
