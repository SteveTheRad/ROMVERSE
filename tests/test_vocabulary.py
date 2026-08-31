from romverse.ui.vocabulary import FEATURES, canonical_title, feature


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
    assert feature("recipe_forge").title == "Recipe Forge"
    assert feature("live_console").title == "Live Console"
    assert feature("nexus").title == "ROMVERSE Nexus"
    assert feature("galaxy").title == "ROMVERSE Galaxy"
