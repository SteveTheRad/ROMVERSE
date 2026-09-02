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
    "device_engine": FeatureName(
        "Device Engine", "Read-only Android discovery", ("ADB device scan",)
    ),
    "system_scan": FeatureName("System Scan", "Diagnostics and analysis", ("Diagnostics",)),
    "health_review": FeatureName("Health Review", "Current evidence and recommended action plan"),
    "health_timeline": FeatureName(
        "Health Timeline", "Device history", ("Health History", "Logs", "Timeline")
    ),
    "activity_center": FeatureName(
        "Activity Center", "Workspace and mission outcomes", ("Activity Ledger", "Full Log")
    ),
    "guardian_core": FeatureName("Guardian Core", "Safety and protection", ("Guardian Center",)),
    "recovery_bay": FeatureName(
        "Recovery Bay", "Diagnose and repair", ("Repair My Phone", "Repair Phone")
    ),
    "device_atlas": FeatureName(
        "Device Atlas", "Compatibility profiles", ("Device Packs", "Mod Manager")
    ),
    "rom_studio": FeatureName("ROM Studio", "Build and customize", ("Build Manager",)),
    "source_lab": FeatureName(
        "Source Lab", "Protected firmware import, inspection, and isolation", ("Working Tree",)
    ),
    "build_proof": FeatureName(
        "Build & Proof", "Deterministic planning and artifact verification", ("Build and Proof",)
    ),
    "genesis_sequence": FeatureName(
        "Genesis Sequence", "Guided ROM creation", ("Automatic Guided Setup", "Build ROM")
    ),
    "guided_arcana": FeatureName(
        "Guided Arcana", "Plain-language next-safe-action workspace", ("ROMVERSE Arcana",)
    ),
    "ascension_protocol": FeatureName(
        "Ascension Protocol",
        "Evidence-bound optional root preparation",
        ("Root preparation wizard",),
    ),
    "architect_mode": FeatureName("Architect Mode", "Advanced ROM tools", ("Expert mode",)),
    "partition_atlas": FeatureName(
        "Partition Atlas", "Images and filesystems", ("Partition Workspace",)
    ),
    "recipe_forge": FeatureName(
        "Recipe Forge", "Guided, auditable modifications", ("Recipes", "Guided Recipe Setup")
    ),
    "forge_control": FeatureName(
        "Forge Control", "Build, sign, and flash readiness", ("Build Control Center",)
    ),
    "forge_bundle": FeatureName("Forge Bundle", "Verified non-bootable intermediate artifact"),
    "nebula_debloat": FeatureName("Nebula Debloat", "Reviewed working-tree system-app removal"),
    "device_dna": FeatureName(
        "Device DNA", "Source-bound device profile and Capability Map", ("Capability Map",)
    ),
    "compatibility_matrix": FeatureName(
        "Compatibility Matrix", "Evidence strength and support decisions"
    ),
    "prebuild_simulation": FeatureName(
        "Pre-Build Simulation", "Dry-run build readiness", ("Prebuild Simulation",)
    ),
    "rom_dna": FeatureName("ROM DNA", "Project and build provenance"),
    "boot_observatory": FeatureName("Boot Observatory", "Read-only boot stability evidence"),
    "app_launchpad": FeatureName(
        "App Launchpad", "Install Android applications", ("APK Installer",)
    ),
    "time_machine": FeatureName(
        "Time Machine",
        "Backup and recovery",
        ("Backup & Recovery", "Backup & Restore", "Rescue & Backup"),
    ),
    "quantum_optimizer": FeatureName(
        "Quantum Optimizer", "Performance and storage", ("System Optimizer",)
    ),
    "recovery_autopilot": FeatureName("Recovery Autopilot", "Bounded ADB host recovery"),
    "romverse_intelligence": FeatureName(
        "ROMVERSE Intelligence", "Verified online repair research"
    ),
    "command_console": FeatureName("Command Console", "Guardian-bounded commands", ("Terminal",)),
    "live_console": FeatureName(
        "Live Console", "Genuine Nexus mission events", ("Mission Console", "Live Operations")
    ),
    "nexus": FeatureName(
        "ROMVERSE Nexus",
        "Pathfinder routes and evidence decisions",
        ("Mission Control", "ROMVERSE Lab"),
    ),
    "pathfinder": FeatureName("Pathfinder", "Evidence-backed Nexus route map"),
    "foresight": FeatureName("Foresight", "Predict, verify, and learn"),
    "insight": FeatureName("Insight", "Why, evidence, and decision timeline"),
    "forge_arsenal": FeatureName(
        "Forge Arsenal", "Tools and dependencies", ("Toolchain Manager", "Toolchain")
    ),
    "archives": FeatureName(
        "ROMVERSE Archives", "Connected knowledge", ("Knowledge Base", "ROMVERSE Knowledge")
    ),
    "romverse_synapse": FeatureName(
        "ROMVERSE Synapse", "Private verified resolution memory", ("Local Learning",)
    ),
    "companion_link": FeatureName(
        "ROMVERSE Link",
        "Desktop and phone connection",
        ("Companion Center", "Companion Link", "Wireless Transfer"),
    ),
    "members": FeatureName(
        "ROMVERSE Members", "Account, membership, and entitlements", ("Account", "Sign in")
    ),
    "galaxy": FeatureName("ROMVERSE Galaxy", "Optional connected ecosystem", ("Galaxy",)),
    "about": FeatureName("About ROMVERSE", "Product family and project story"),
}


NESTED_FEATURE_OWNERS: dict[str, str] = {
    "device_nexus": "command_deck",
    "device_engine": "command_deck",
    "system_scan": "quantum_optimizer",
    "health_review": "quantum_optimizer",
    "source_lab": "rom_studio",
    "build_proof": "rom_studio",
    "genesis_sequence": "rom_studio",
    "guided_arcana": "rom_studio",
    "ascension_protocol": "rom_studio",
    "architect_mode": "rom_studio",
    "partition_atlas": "rom_studio",
    "recipe_forge": "rom_studio",
    "forge_control": "rom_studio",
    "forge_bundle": "rom_studio",
    "nebula_debloat": "rom_studio",
    "device_dna": "rom_studio",
    "compatibility_matrix": "rom_studio",
    "prebuild_simulation": "rom_studio",
    "rom_dna": "rom_studio",
    "boot_observatory": "rom_studio",
    "recovery_autopilot": "recovery_bay",
    "romverse_intelligence": "recovery_bay",
    "romverse_synapse": "archives",
    "pathfinder": "nexus",
    "foresight": "nexus",
    "insight": "nexus",
}

EXPERT_ONLY_NESTED_FEATURES = frozenset(
    {
        "architect_mode",
        "partition_atlas",
        "forge_control",
        "rom_dna",
        "boot_observatory",
        "pathfinder",
        "foresight",
        "insight",
    }
)

SOURCE_ROUTES = {
    "app launchpad": "app_launchpad",
    "ascension protocol": "ascension_protocol",
    "architect mode": "architect_mode",
    "boot observatory": "boot_observatory",
    "build & proof": "build_proof",
    "command console": "command_console",
    "compatibility matrix": "compatibility_matrix",
    "device atlas": "device_atlas",
    "device dna": "device_dna",
    "device engine": "device_engine",
    "device nexus": "device_nexus",
    "forge arsenal": "forge_arsenal",
    "forge bundle": "forge_bundle",
    "forge control": "forge_control",
    "foresight": "foresight",
    "genesis sequence": "genesis_sequence",
    "guided arcana": "guided_arcana",
    "guardian core": "guardian_core",
    "health review": "health_review",
    "insight": "insight",
    "live console": "live_console",
    "nebula debloat": "nebula_debloat",
    "partition atlas": "partition_atlas",
    "pre-build simulation": "prebuild_simulation",
    "quantum optimizer": "quantum_optimizer",
    "recipe forge": "recipe_forge",
    "recipe forger": "recipe_forge",
    "recovery autopilot": "recovery_autopilot",
    "recovery bay": "recovery_bay",
    "rom dna": "rom_dna",
    "rom studio": "rom_studio",
    "romverse arcana": "guided_arcana",
    "romverse archives": "archives",
    "romverse galaxy": "galaxy",
    "romverse intelligence": "romverse_intelligence",
    "romverse link": "companion_link",
    "romverse members": "members",
    "romverse nexus": "nexus",
    "romverse synapse": "romverse_synapse",
    "system scan": "system_scan",
    "source lab": "source_lab",
    "time machine": "time_machine",
    "pathfinder": "pathfinder",
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
