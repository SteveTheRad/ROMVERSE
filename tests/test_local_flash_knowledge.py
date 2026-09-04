from __future__ import annotations

import pytest

from romverse.knowledge.archives import search_catalog, source_lane
from romverse.ui.knowledge_center import ARCHIVE_ARTICLES


@pytest.mark.parametrize(
    "query",
    (
        "Flash / restore images",
        "expert flash",
        "manual stock image restore",
        "image flash failed",
        "private image snapshots space",
        "stop after current write",
    ),
)
def test_expert_image_search_reaches_the_local_write_workflow(query: str) -> None:
    match = search_catalog(ARCHIVE_ARTICLES, query, limit=1)[0]

    assert match.article.key == "expert-image-flash-and-manual-restore"
    assert match.article.route == "rom_studio"
    assert source_lane(match.article.source) == "local"


@pytest.mark.parametrize(
    ("query", "expected_key", "expected_route"),
    (
        ("fastboot device detected", "fastboot-identity-only", "device_atlas"),
        ("architect mode does nothing", "architect-mode-does-not-change-desktop", "rom_studio"),
    ),
)
def test_discovery_and_experience_help_keep_their_own_destinations(
    query: str, expected_key: str, expected_route: str
) -> None:
    match = search_catalog(ARCHIVE_ARTICLES, query, limit=1)[0]

    assert match.article.key == expected_key
    assert match.article.route == expected_route
