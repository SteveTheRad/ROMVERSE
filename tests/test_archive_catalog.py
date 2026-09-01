from __future__ import annotations

from dataclasses import replace

import pytest

from romverse.knowledge.archives import (
    ALL_CATEGORIES,
    CATEGORIES,
    KNOWN_FIXES,
    ArchiveSource,
    catalog_metrics,
    search_catalog,
    validate_catalog,
)
from romverse.ui.knowledge_center import ARCHIVE_ARTICLES


def test_archives_catalog_is_large_unique_classified_and_evidence_labelled() -> None:
    validate_catalog(ARCHIVE_ARTICLES)
    metrics = catalog_metrics(ARCHIVE_ARTICLES)

    assert len(ARCHIVE_ARTICLES) == 118
    assert len(KNOWN_FIXES) == 68
    assert metrics == {
        "guides": len(ARCHIVE_ARTICLES),
        "categories": len(CATEGORIES),
        "official_sources": 35,
        "known_fixes": len(KNOWN_FIXES),
    }
    assert len({article.key for article in ARCHIVE_ARTICLES}) == len(ARCHIVE_ARTICLES)
    assert len({article.title.casefold() for article in ARCHIVE_ARTICLES}) == len(ARCHIVE_ARTICLES)
    assert {article.category for article in ARCHIVE_ARTICLES} == set(CATEGORIES)
    assert all(article.evidence and article.automation and article.route for article in KNOWN_FIXES)


@pytest.mark.parametrize(
    ("query", "expected_title"),
    (
        ("boot loop", "Boot loop after a ROM change: first safe triage"),
        ("payload.bin", "payload.bin found but Payload Dumper is missing"),
        ("adb unauthorized", "ADB authorization is pending on the phone"),
        ("multiple devices", "ADB error: more than one device or emulator"),
        ("erofs", "EXT4 or EROFS filesystem reader is missing"),
        ("out of space", "Workspace is out of space"),
        ("hash mismatch", "Managed tool changed after verification"),
        ("approval expired", "Guardian approval expired before execution"),
        ("install_failed", "APK install error: INSTALL_FAILED_INVALID_APK"),
        ("signature", "APK update error: INSTALL_FAILED_UPDATE_INCOMPATIBLE"),
        ("downgrade", "APK install error: INSTALL_FAILED_VERSION_DOWNGRADE"),
        (
            "android device id",
            "Recognize an Android model without guessing build or flash support",
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
            "about counters unavailable",
            "About runtime evidence is stale or unavailable",
        ),
        (
            "synapse fix retired",
            "Local learned fix is missing or retired in Archives",
        ),
        (
            "activity handoff stopped",
            "Activity outcome cannot reopen its exact source evidence",
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
    assert len(search_catalog(ARCHIVE_ARTICLES, "", limit=1_000)) == 118
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
