"""Authoritative Desktop navigation groups and presentation-only shell state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self


@dataclass(frozen=True, slots=True)
class NavigationGroup:
    """One permanent sidebar group composed only of canonical feature routes."""

    title: str
    routes: tuple[str, ...]


NAVIGATION_GROUPS = (
    NavigationGroup("HOME", ("command_deck",)),
    NavigationGroup("ROM WORKSHOP", ("rom_studio",)),
    NavigationGroup("DEVICE", ("quantum_optimizer", "device_atlas")),
    NavigationGroup(
        "GUARDIAN & RECOVERY",
        ("recovery_bay", "guardian_core", "app_launchpad", "time_machine"),
    ),
    NavigationGroup(
        "ACTIVITY & KNOWLEDGE",
        ("health_timeline", "activity_center", "archives"),
    ),
    NavigationGroup(
        "LIVE OPERATIONS",
        ("command_console", "live_console", "nexus", "forge_arsenal"),
    ),
    NavigationGroup("CONNECTED ROMVERSE", ("companion_link", "members", "galaxy")),
    NavigationGroup("SYSTEM", ("about",)),
)

EXPERT_ONLY_ROUTES = frozenset({"command_console", "nexus", "forge_arsenal"})


def navigation_routes() -> tuple[str, ...]:
    """Return canonical sidebar routes in their single authoritative display order."""

    return tuple(route for group in NAVIGATION_GROUPS for route in group.routes)


def navigation_section(route: str) -> str:
    """Resolve a canonical route to its visible Desktop breadcrumb group."""

    for group in NAVIGATION_GROUPS:
        if route in group.routes:
            return group.title
    raise KeyError(route)


@dataclass(frozen=True, slots=True)
class WorkspaceShellState:
    """Session-only chrome choices that never affect projects, evidence, or operations."""

    navigation_collapsed: bool = False
    focus_mode: bool = False

    def toggle_navigation(self) -> Self:
        return type(self)(not self.navigation_collapsed, self.focus_mode)

    def toggle_focus(self) -> Self:
        return type(self)(self.navigation_collapsed, not self.focus_mode)
