"""Deterministic Archives recommendations for typed ROMVERSE evidence."""

from __future__ import annotations

from dataclasses import dataclass

from romverse.device.apk_install import extract_apk_install_failure_code
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
    "connection.fastboot_identity_only": "fastboot-identity-only",
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

REPAIR_CONCERN_FINDING_IDS = {
    RepairConcern.BATTERY_HEAT: frozenset({"battery.low", "battery.temperature"}),
    RepairConcern.STORAGE: frozenset({"storage.capacity"}),
    RepairConcern.USB_ADB: frozenset({"connection.unavailable", "scan.partial"}),
    RepairConcern.APP_CRASH: frozenset(),
    RepairConcern.BOOT_UPDATE: frozenset(
        {"boot.incomplete", "security.bootloader", "security.verified_boot"}
    ),
    RepairConcern.DISPLAY_TOUCH: frozenset(),
    RepairConcern.NETWORK: frozenset(),
    RepairConcern.CAMERA_AUDIO: frozenset(),
    RepairConcern.PERFORMANCE: frozenset(
        {"battery.temperature", "storage.capacity", "boot.recent"}
    ),
}

OEM_ARTICLE_KEYS = {
    "asus": "asus-firmware-sku-mismatch",
    "fairphone": "fairphone-update-problem-triage",
    "google": "pixel-ota-versus-factory",
    "hmd": "hmd-nokia-staged-update-delivery",
    "hmd global": "hmd-nokia-staged-update-delivery",
    "honor": "honor-magicos-update-not-offered",
    "huawei": "huawei-hisuite-erecovery-restore",
    "infinix": "infinix-model-update-support",
    "iqoo": "vivo-funtouch-local-firmware",
    "itel": "itel-ota-firmware-troubleshooting",
    "motorola": "motorola-rescue-identity-and-wipe",
    "lenovo": "motorola-rescue-identity-and-wipe",
    "nothing": "nothing-os-ota-failure",
    "nokia": "hmd-nokia-staged-update-delivery",
    "nubia": "nubia-redmagic-myos-update-scope",
    "oneplus": "oneplus-oxygenos-local-install",
    "oppo": "oppo-coloros-assistant-update",
    "poco": "xiaomi-phased-regional-updates",
    "realme": "realme-recovery-local-update",
    "redmagic": "nubia-redmagic-myos-update-scope",
    "redmi": "xiaomi-phased-regional-updates",
    "samsung": "samsung-smart-switch-update-recovery",
    "sony": "sony-xperia-companion-software-repair",
    "tecno": "tecno-transsion-update-scope",
    "vivo": "vivo-funtouch-local-firmware",
    "xiaomi": "xiaomi-phased-regional-updates",
    "zte": "zte-online-offline-system-update",
}

APK_FAILURE_ARTICLE_KEYS = {
    "INSTALL_FAILED_INVALID_APK": "apk-invalid",
    "INSTALL_FAILED_UPDATE_INCOMPATIBLE": "apk-signature-conflict",
    "INSTALL_FAILED_INSUFFICIENT_STORAGE": "apk-insufficient-storage",
    "INSTALL_FAILED_NO_MATCHING_ABIS": "apk-abi-incompatible",
    "INSTALL_FAILED_VERSION_DOWNGRADE": "apk-version-downgrade",
    "INSTALL_FAILED_MISSING_SPLIT": "apk-missing-split",
    "INSTALL_FAILED_USER_RESTRICTED": "apk-user-restricted",
    "INSTALL_FAILED_TEST_ONLY": "apk-test-only",
}

_ARTICLE_BY_KEY = {article.key: article for article in KNOWN_FIXES}
_DYNAMIC_DIAGNOSTIC_KEYS = frozenset({"adb-no-device", "adb-unauthorized", "adb-device-offline"})
_REQUIRED_KEYS = (
    frozenset(DIAGNOSTIC_ARTICLE_KEYS.values())
    | frozenset(REPAIR_CONCERN_ARTICLE_KEYS.values())
    | _DYNAMIC_DIAGNOSTIC_KEYS
    | frozenset(APK_FAILURE_ARTICLE_KEYS.values())
    | frozenset(OEM_ARTICLE_KEYS.values())
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


def article_key_for_diagnostic_finding(finding_id: str, context: str = "") -> str:
    """Resolve one typed finding to an exact guide, or return empty when context is ambiguous."""

    normalized = finding_id.replace("\x00", "").strip()[:120]
    if normalized != "connection.unavailable":
        return DIAGNOSTIC_ARTICLE_KEYS.get(normalized, "")
    context = context.replace("\x00", " ").casefold()[:2_000]
    if "unauthor" in context or "rsa" in context:
        return "adb-unauthorized"
    if "offline" in context:
        return "adb-device-offline"
    if any(token in context for token in ("no device", "not found", "disconnected")):
        return "adb-no-device"
    return ""


def article_key_for_apk_failure(output: str) -> str:
    """Resolve one exact Android install failure without guessing from broad wording."""

    return APK_FAILURE_ARTICLE_KEYS.get(extract_apk_install_failure_code(output), "")


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
        key = article_key_for_diagnostic_finding(
            finding.finding_id,
            " ".join((finding.title, finding.explanation, finding.guidance)),
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
    manufacturer: str = "",
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

    contextual_ids = REPAIR_CONCERN_FINDING_IDS[concern]
    contextual_findings = tuple(
        finding for finding in findings if finding.finding_id in contextual_ids
    )
    for recommendation in recommend_for_findings(contextual_findings, limit=bounded_limit):
        if recommendation.article.key in seen:
            continue
        seen.add(recommendation.article.key)
        recommendations.append(recommendation)
        if len(recommendations) >= bounded_limit:
            return tuple(recommendations)

    normalized_manufacturer = " ".join(
        manufacturer.replace("\x00", " ").casefold().strip().split()
    )[:80]
    oem_article = _ARTICLE_BY_KEY.get(OEM_ARTICLE_KEYS.get(normalized_manufacturer, ""))
    if oem_article is not None and oem_article.key not in seen:
        seen.add(oem_article.key)
        recommendations.append(
            ArchiveRecommendation(
                oem_article,
                f"Device DNA manufacturer: {manufacturer.strip()[:80]}",
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
