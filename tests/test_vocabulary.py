from romverse.ui.vocabulary import (
    EXPERT_ONLY_NESTED_FEATURES,
    FEATURES,
    NESTED_FEATURE_OWNERS,
    SOURCE_ROUTES,
    canonical_source_route,
    canonical_title,
    feature,
)
from romverse.ui.workspace_shell import navigation_routes


def test_every_feature_has_a_unique_canonical_title_and_help_text() -> None:
    titles = [item.title for item in FEATURES.values()]
    assert len(titles) == len(set(titles))
    assert all(item.subtitle for item in FEATURES.values())


def test_legacy_display_names_resolve_without_migrating_internal_ids() -> None:
    assert canonical_title("Dashboard") == "Command Deck"
    assert canonical_title("Device Center") == "Device Portal"
    assert canonical_title("Device Nexus") == "Device Portal"
    assert canonical_title("Expert Mode") == "Architect Mode"
    assert canonical_title("Build Control Center") == "Forge Control"
    assert canonical_title("Toolchain Manager") == "Forge Arsenal"
    assert canonical_title("unknown internal route") == "unknown internal route"


def test_core_romverse_names_are_locked() -> None:
    assert feature("rom_studio").title == "ROM Studio"
    assert feature("genesis_sequence").title == "Genesis Sequence"
    assert feature("ascension_protocol").title == "Ascension Protocol"
    assert feature("recipe_forge").title == "Recipe Forge"
    assert feature("live_console").title == "Live Console"
    assert feature("nexus").title == "ROMVERSE Nexus"
    assert feature("galaxy").title == "ROMVERSE Galaxy"


def test_every_nested_feature_has_a_real_top_level_owner_and_expert_scope() -> None:
    top_level = set(navigation_routes())

    assert set(NESTED_FEATURE_OWNERS) == set(FEATURES) - top_level
    assert set(NESTED_FEATURE_OWNERS.values()) <= top_level
    assert set(NESTED_FEATURE_OWNERS) >= EXPERT_ONLY_NESTED_FEATURES


def test_evidence_sources_return_to_their_exact_desktop_feature() -> None:
    assert canonical_source_route("Device Engine") == "device_engine"
    assert canonical_source_route("Device DNA") == "device_dna"
    assert canonical_source_route("Compatibility Matrix") == "compatibility_matrix"
    assert canonical_source_route("Recovery Autopilot") == "recovery_autopilot"
    assert canonical_source_route("ROMVERSE Intelligence") == "romverse_intelligence"
    assert canonical_source_route("ROMVERSE Synapse") == "romverse_synapse"


def test_every_evidence_source_resolves_to_a_registered_page_or_nested_feature() -> None:
    assert set(SOURCE_ROUTES.values()) <= set(FEATURES)
    for source in (
        "Ascension Protocol",
        "Forge Control",
        "Genesis Sequence",
        "Recipe Forger",
        "System Scan",
        "Health Review",
        "Pathfinder",
        "Foresight",
        "Insight",
    ):
        assert canonical_source_route(source) in FEATURES
