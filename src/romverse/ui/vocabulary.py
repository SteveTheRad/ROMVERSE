"""Canonical user-facing names for the ROMVERSE product family.

The keys in this module are stable UI route identifiers.  Existing project schemas,
workspace directories, receipt types, and Python module names intentionally keep their
legacy identifiers so older ROMVERSE workspaces remain compatible.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FeatureName:
    title: str
    subtitle: str
    legacy: tuple[str, ...] = ()


FEATURES: dict[str, FeatureName] = {
    "command_deck": FeatureName("Command Deck", "Device overview", ("Dashboard",)),
    "device_nexus": FeatureName(
        "Device Portal", "Connected Android device", ("Device Center", "Device Nexus")
    ),
    "system_scan": FeatureName("System Scan", "Diagnostics and analysis", ("Diagnostics",)),
    "health_timeline": FeatureName("Health Timeline", "Device history", ("Health History", "Logs")),
    "activity_center": FeatureName(
        "Activity Center", "Workspace and mission outcomes", ("Activity Ledger", "Full Log")
    ),
    "guardian_core": FeatureName("Guardian Core", "Safety and protection", ("Guardian Center",)),
    "recovery_bay": FeatureName("Recovery Bay", "Diagnose and repair", ("Repair My Phone",)),
    "device_atlas": FeatureName(
        "Device Atlas", "Compatibility profiles", ("Device Packs", "Mod Manager")
    ),
    "rom_studio": FeatureName("ROM Studio", "Build and customize", ("Build Manager",)),
    "genesis_sequence": FeatureName("Genesis Sequence", "Guided ROM creation"),
    "architect_mode": FeatureName("Architect Mode", "Advanced ROM tools", ("Expert mode",)),
    "partition_atlas": FeatureName(
        "Partition Atlas", "Images and filesystems", ("Partition Workspace",)
    ),
    "recipe_forge": FeatureName("Recipe Forge", "Guided, auditable modifications"),
    "forge_control": FeatureName(
        "Forge Control", "Build, sign, and flash readiness", ("Build Control Center",)
    ),
    "app_launchpad": FeatureName(
        "App Launchpad", "Install Android applications", ("APK Installer",)
    ),
    "time_machine": FeatureName(
        "Time Machine", "Backup and recovery", ("Backup & Recovery", "Backup & Restore")
    ),
    "quantum_optimizer": FeatureName(
        "Quantum Optimizer", "Performance and storage", ("System Optimizer",)
    ),
    "command_console": FeatureName("Command Console", "Guardian-bounded commands", ("Terminal",)),
    "live_console": FeatureName(
        "Live Console", "Genuine Nexus mission events", ("Mission Console",)
    ),
    "nexus": FeatureName(
        "ROMVERSE Nexus", "Pathfinder routes and evidence decisions", ("Mission Control",)
    ),
    "forge_arsenal": FeatureName(
        "Forge Arsenal", "Tools and dependencies", ("Toolchain Manager", "Toolchain")
    ),
    "archives": FeatureName(
        "ROMVERSE Archives", "Connected knowledge", ("Knowledge Base", "ROMVERSE Knowledge")
    ),
    "companion_link": FeatureName(
        "ROMVERSE Link",
        "Desktop and phone connection",
        ("Companion Center", "Companion Link"),
    ),
    "members": FeatureName(
        "ROMVERSE Members", "Account, membership, and entitlements", ("Account", "Sign in")
    ),
    "galaxy": FeatureName("ROMVERSE Galaxy", "Optional connected ecosystem", ("Galaxy",)),
    "about": FeatureName("About ROMVERSE", "Product family and project story"),
}

SOURCE_ROUTES = {
    "app launchpad": "app_launchpad",
    "ascension protocol": "rom_studio",
    "command console": "command_console",
    "compatibility matrix": "nexus",
    "device atlas": "device_atlas",
    "device dna": "rom_studio",
    "device engine": "command_deck",
    "forge arsenal": "forge_arsenal",
    "forge control": "rom_studio",
    "genesis sequence": "rom_studio",
    "guardian core": "guardian_core",
    "live console": "live_console",
    "quantum optimizer": "quantum_optimizer",
    "recipe forger": "rom_studio",
    "recovery autopilot": "recovery_bay",
    "recovery bay": "recovery_bay",
    "rom studio": "rom_studio",
    "romverse archives": "archives",
    "romverse galaxy": "galaxy",
    "romverse intelligence": "recovery_bay",
    "romverse link": "companion_link",
    "romverse members": "members",
    "romverse nexus": "nexus",
    "romverse synapse": "nexus",
    "system scan": "quantum_optimizer",
    "time machine": "time_machine",
}

CATEGORY_ROUTES = {
    "applications": "app_launchpad",
    "backup": "time_machine",
    "community": "galaxy",
    "device": "command_deck",
    "diagnostics": "quantum_optimizer",
    "guardian": "guardian_core",
    "link": "companion_link",
    "nexus": "nexus",
    "optimizer": "quantum_optimizer",
    "recovery": "time_machine",
    "repair": "recovery_bay",
    "rom-studio": "rom_studio",
    "tools": "forge_arsenal",
}


def feature(key: str) -> FeatureName:
    """Return a canonical feature label without coupling callers to the mapping."""

    return FEATURES[key]


def canonical_source_route(source: str, category: str = "") -> str:
    """Resolve genuine local evidence to the Desktop feature that produced it."""

    return SOURCE_ROUTES.get(
        source.casefold().strip(),
        CATEGORY_ROUTES.get(category.casefold().strip(), ""),
    )


def canonical_title(label: str) -> str:
    """Resolve an old display label to its canonical title.

    This is a display compatibility helper, not a migration of persisted identifiers.
    """

    normalized = label.casefold().strip()
    for item in FEATURES.values():
        if normalized == item.title.casefold() or any(
            normalized == legacy.casefold() for legacy in item.legacy
        ):
            return item.title
    return label
