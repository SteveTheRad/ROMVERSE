from __future__ import annotations

from dataclasses import replace

import pytest

from romverse.knowledge.archives import (
    ALL_CATEGORIES,
    CANONICAL_ROUTES,
    CATEGORIES,
    KNOWN_FIXES,
    ArchiveSource,
    catalog_metrics,
    search_catalog,
    source_lane,
    validate_catalog,
)
from romverse.ui.knowledge_center import ARCHIVE_ARTICLES
from romverse.ui.workspace_shell import NAVIGATION_GROUPS


def test_archives_catalog_is_large_unique_classified_and_evidence_labelled() -> None:
    validate_catalog(ARCHIVE_ARTICLES)
    metrics = catalog_metrics(ARCHIVE_ARTICLES)

    assert len(ARCHIVE_ARTICLES) == 219
    assert len(KNOWN_FIXES) == 169
    assert metrics == {
        "guides": len(ARCHIVE_ARTICLES),
        "categories": len(CATEGORIES),
        "sourced_guides": 102,
        "official_sources": 95,
        "community_sources": 7,
        "known_fixes": len(KNOWN_FIXES),
    }
    assert len({article.key for article in ARCHIVE_ARTICLES}) == len(ARCHIVE_ARTICLES)
    assert len({article.title.casefold() for article in ARCHIVE_ARTICLES}) == len(ARCHIVE_ARTICLES)
    assert {article.category for article in ARCHIVE_ARTICLES} == set(CATEGORIES)
    assert all(article.evidence and article.automation and article.route for article in KNOWN_FIXES)


def test_archives_have_an_exact_destination_for_every_top_level_desktop_page() -> None:
    top_level_routes = {route for group in NAVIGATION_GROUPS for route in group.routes}
    represented_routes = {article.route for article in ARCHIVE_ARTICLES}

    assert top_level_routes <= CANONICAL_ROUTES
    assert top_level_routes <= represented_routes


@pytest.mark.parametrize(
    ("query", "expected_title"),
    (
        ("boot loop", "Boot loop after a ROM change: first safe triage"),
        ("payload.bin", "payload.bin found but Payload Dumper is missing"),
        ("adb unauthorized", "ADB authorization is pending on the phone"),
        ("multiple devices", "ADB error: more than one device or emulator"),
        (
            "Phone detected in bootloader Fastboot or userspace fastbootd",
            "Phone detected in bootloader Fastboot or userspace fastbootd",
        ),
        (
            "Phone detected in Android recovery or ADB sideload mode",
            "Phone detected in Android recovery or ADB sideload mode",
        ),
        (
            "Android device identity fields: brand, manufacturer, model, device, and product",
            "Android device identity fields: brand, manufacturer, model, device, and product",
        ),
        ("erofs", "EXT4 or EROFS filesystem reader is missing"),
        ("out of space", "Workspace is out of space"),
        ("hash mismatch", "Managed tool changed after verification"),
        ("approval expired", "Guardian approval expired before execution"),
        (
            "guardian consent already consumed",
            "Guardian runtime consent was already consumed or expired",
        ),
        ("install_failed", "APK install error: INSTALL_FAILED_INVALID_APK"),
        ("signature", "APK update error: INSTALL_FAILED_UPDATE_INCOMPATIBLE"),
        ("downgrade", "APK install error: INSTALL_FAILED_VERSION_DOWNGRADE"),
        (
            "return button loses context",
            "Return button opens the right page but loses the exact evidence",
        ),
        (
            "synapse opens nexus",
            "ROMVERSE Synapse evidence opens the wrong workspace",
        ),
        (
            "pathfinder opens generic nexus",
            "Pathfinder, Foresight, or Insight opens only a generic Nexus page",
        ),
        (
            "studio wrong nexus plan",
            "ROM Studio opens with a different Nexus plan or Device Atlas report",
        ),
        (
            "android device id",
            "Android device identity fields: brand, manufacturer, model, device, and product",
        ),
        (
            "exact device toolchain",
            "Recognized device needs its exact build toolchain",
        ),
        (
            "build compile flash requirements",
            "Determine what a recognized Android device needs to build, compile, and flash",
        ),
        (
            "device dna build unconfirmed forge ready",
            "Device DNA says build unconfirmed after Forge verifies the source blueprint",
        ),
        (
            "forge ota plan says fastboot super",
            "Device DNA says build unconfirmed after Forge verifies the source blueprint",
        ),
        (
            "about counters unavailable",
            "About runtime evidence is stale or unavailable",
        ),
        (
            "live console white table",
            "Live Console table is white or unreadable on a dark desktop",
        ),
        (
            "desktop app all white",
            "ROMVERSE Desktop is white or unreadable after a source update",
        ),
        (
            "time machine no enabled buttons",
            "Time Machine has no action when no ROM project or snapshot exists",
        ),
        (
            "command console blocked",
            "Command Console check is blocked or produces no trusted result",
        ),
        (
            "health timeline cannot compare",
            "Health Timeline cannot compare the selected diagnostic snapshot",
        ),
        (
            "members service not configured",
            "ROMVERSE Members sign-in is unavailable or unconfigured",
        ),
        (
            "galaxy topic not published",
            "ROMVERSE Galaxy topic is local and not published",
        ),
        (
            "nexus cannot derive route",
            "ROMVERSE Nexus cannot derive a route from current project evidence",
        ),
        (
            "find anything missing feature",
            "Find Anything cannot open a named internal ROMVERSE feature",
        ),
        (
            "live console opens wrong page",
            "Live Console source opens the owner page but loses the exact feature",
        ),
        (
            "architect mode does nothing",
            "Architect Mode does not reveal the Expert desktop",
        ),
        (
            "synapse fix retired",
            "Local learned fix is missing or retired in Archives",
        ),
        (
            "activity handoff stopped",
            "Activity outcome cannot reopen its exact source evidence",
        ),
        (
            "command deck wrong workflow",
            "Command Deck opens ROM Studio but not the requested workflow",
        ),
        (
            "owner page missing evidence",
            "Command Deck owner page opens without current device evidence",
        ),
        (
            "open rom studio loses context",
            "Open ROM Studio loses the originating Pack, toolchain, or Nexus project",
        ),
        (
            "guardian manifest only in dialog",
            "ROM Studio opens recovery, Device Atlas, or Guardian without the exact project",
        ),
        (
            "apk receipt activity",
            "Activity outcome cannot reopen its exact source evidence",
        ),
        (
            "galaxy activity exact topic",
            "Activity Center opens Galaxy but not the exact local topic",
        ),
        (
            "terms not published",
            "About contains Terms and Privacy drafts pending legal review",
        ),
        (
            "privacy policy local workspace",
            "About Privacy shows the real local and online data boundary",
        ),
        (
            "third party notices incomplete",
            "Open-source licences or third-party notices are incomplete",
        ),
        (
            "changelog build proof",
            "Changelog or installed Desktop build cannot prove what is running",
        ),
        (
            "theme resets after restart",
            "Desktop theme resets to default after ROMVERSE restarts",
        ),
        (
            "official android id no device pack",
            "Official Android ID search finds a phone but no Device Pack",
        ),
        (
            "online badge keeps checking",
            "Online badge keeps checking after online sources are disabled",
        ),
        (
            "device catalog sync finishes after disabled",
            "Official Android ID sync finishes after online sources are disabled",
        ),
        (
            "command deck guardian safety active",
            "Command Deck says Guardian is active before integrity is verified",
        ),
    ),
)
def test_archives_rank_verified_known_fixes_for_real_failure_language(
    query: str, expected_title: str
) -> None:
    matches = search_catalog(ARCHIVE_ARTICLES, query, limit=3)

    assert matches
    assert matches[0].article.title == expected_title


def test_archives_reject_weak_matches_and_bound_results() -> None:
    assert not search_catalog(ARCHIVE_ARTICLES, "definitely not a real ROMVERSE topic")
    assert len(search_catalog(ARCHIVE_ARTICLES, "", limit=1_000)) == 219
    assert len(search_catalog(ARCHIVE_ARTICLES, "", limit=0)) == 1
    connectivity = search_catalog(
        ARCHIVE_ARTICLES,
        "",
        category="CONNECTIVITY & ADB",
    )
    assert connectivity
    assert all(match.article.category == "CONNECTIVITY & ADB" for match in connectivity)
    assert not search_catalog(ARCHIVE_ARTICLES, "adb", category="NOT A CATEGORY")
    assert ALL_CATEGORIES not in CATEGORIES


@pytest.mark.parametrize(
    ("query", "expected_title"),
    (
        (
            "compatible not compatible unknown",
            "Unknown compatibility is not the same as known incompatible",
        ),
        ("update engine error 51", "update_engine error 51: payload timestamp rejected"),
        (
            "pre-build pre-build-incremental mismatch",
            "Incremental OTA pre-build and pre-incremental values must match exactly",
        ),
        (
            "gsi compatible rom",
            "A GSI-capable device is not automatically compatible with every ROM",
        ),
        (
            "community report valid evidence",
            "Community reports: reported, corroborated, locally verified, and retired",
        ),
    ),
)
def test_archives_rank_android_identity_compatibility_and_community_knowledge(
    query: str, expected_title: str
) -> None:
    matches = search_catalog(ARCHIVE_ARTICLES, query, limit=3)

    assert matches
    assert matches[0].article.title == expected_title


@pytest.mark.parametrize(
    ("query", "expected_title"),
    (
        (
            "samsung smart switch emergency recovery",
            "Samsung Galaxy update failure: Smart Switch and emergency recovery boundaries",
        ),
        (
            "sony xperia companion software repair",
            "Sony Xperia boot loop or failed update: Xperia Companion software repair",
        ),
        (
            "oneplus oxygenos local install",
            "OnePlus OxygenOS local install: official package and version scope",
        ),
        (
            "asus incorrect firmware sku",
            "ASUS Zenfone or ROG Phone update fails: firmware SKU must match",
        ),
        ("nothing ota failed", "Nothing OS OTA will not download or install"),
        (
            "oppo coloros assistant",
            "OPPO ColorOS update: phone route versus ColorOS Assistant",
        ),
        (
            "realme recovery install from storage",
            "realme UI update failure and official Recovery Mode install",
        ),
        (
            "vivo iqoo downgrade android 8",
            "vivo or iQOO local firmware update and downgrade boundary",
        ),
        (
            "huawei hisuite erecovery",
            "HUAWEI HiSuite or eRecovery restoration may erase data and may be unsupported",
        ),
        (
            "honor update not showing",
            "HONOR MagicOS update not offered: network, SIM, cache, and staged rollout",
        ),
        (
            "hmd nokia operator rollout",
            "HMD or Nokia update availability depends on model, operator, market, and rollout",
        ),
        (
            "fairphone preparing to restart",
            "Fairphone update problem: rollout, storage, download, restart, and safe mode",
        ),
        (
            "tecno model country update",
            "TECNO update coverage is model-, month-, region-, and country-specific",
        ),
        (
            "infinix update support",
            "Infinix updates and support promises are exact-model evidence",
        ),
        (
            "itel forced update data loss",
            "itel OTA, boot crash, and firmware troubleshooting boundaries",
        ),
        (
            "zte offline system update",
            "ZTE system update: online offer or exact official offline package",
        ),
        (
            "nubia redmagic myos bug",
            "nubia or REDMAGIC MyOS updates and bug reports require exact model scope",
        ),
    ),
)
def test_archives_cover_each_supported_oem_family(query: str, expected_title: str) -> None:
    matches = search_catalog(ARCHIVE_ARTICLES, query, limit=1)

    assert matches[0].article.title == expected_title
    assert source_lane(matches[0].article.source) == "official"


@pytest.mark.parametrize(
    ("key", "lane"),
    (
        ("samsung-smart-switch-update-recovery", "official"),
        ("lineageos-exact-device-install-evidence", "community"),
        ("community-slot-switch-bootloop-caution", "community"),
        ("popsicle-os40025-android-auto-integration", "field"),
    ),
)
def test_archives_classify_evidence_without_granting_authority(key: str, lane: str) -> None:
    article = next(item for item in KNOWN_FIXES if item.key == key)

    assert source_lane(article.source) == lane
    if lane == "community":
        assert "NO " in article.automation


@pytest.mark.parametrize(
    ("query", "expected_title"),
    (
        (
            "popsicle OS4.0.0.25 android auto",
            "HyperOS 4 OS4.0.0.25 Android Auto: field-validated integration pattern",
        ),
        (
            "android auto installed but not working projection",
            "Android Auto is installed as a system app but projection is unavailable",
        ),
        (
            "will popsicle OS4.0.0.25 work all devices",
            "OS4.0.0.25 popsicle field result and same-device compatibility boundary",
        ),
    ),
)
def test_archives_surface_hyperos_40025_field_knowledge(query: str, expected_title: str) -> None:
    matches = search_catalog(ARCHIVE_ARTICLES, query, limit=3)

    assert matches
    assert matches[0].article.title == expected_title
    assert matches[0].article.source.authority == "FIELD VERIFIED • ONE DEVICE/EXACT BUILD"


def test_hyperos_40025_field_knowledge_preserves_evidence_boundaries() -> None:
    integration = next(
        article
        for article in KNOWN_FIXES
        if article.key == "popsicle-os40025-android-auto-integration"
    )
    boundary = next(
        article for article in KNOWN_FIXES if article.key == "popsicle-os40025-same-device-boundary"
    )

    integration_text = integration.search_document.casefold()
    boundary_text = boundary.search_document.casefold()
    assert "config_systemautomotiveprojection" in integration_text
    assert "config_defaultlisteneraccesspackages" in integration_text
    assert "google services framework" in integration_text
    assert "carwith was a confirmed conflict in this exact build" in integration_text
    assert "one-device, exact-build field evidence" in integration_text
    assert "does not statistically establish universal success" in boundary_text
    assert "never be followed by bootloader relocking" in boundary_text
    assert "no build, flash, wipe" in integration.automation.casefold()


def test_archives_validation_rejects_duplicate_identity_and_unsafe_source() -> None:
    article = KNOWN_FIXES[0]
    with pytest.raises(ValueError, match="duplicated"):
        validate_catalog((article, article))

    unsafe = replace(
        article,
        key="unsafe-source",
        title="Unsafe source fixture",
        source=ArchiveSource("Unsafe", "TEST", "http://user:pass@example.test/fix"),
    )
    with pytest.raises(ValueError, match="source URL"):
        validate_catalog((unsafe,))
