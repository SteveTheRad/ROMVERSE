from __future__ import annotations

import pytest

from romverse.ui.vocabulary import FEATURES
from romverse.ui.workspace_shell import (
    EXPERT_ONLY_ROUTES,
    NAVIGATION_GROUPS,
    WorkspaceShellState,
    navigation_routes,
    navigation_section,
)


def test_navigation_groups_are_complete_unique_and_canonical() -> None:
    routes = navigation_routes()

    assert len(routes) == len(set(routes)) == 19
    assert set(routes) == {
        "command_deck",
        "rom_studio",
        "quantum_optimizer",
        "device_atlas",
        "recovery_bay",
        "guardian_core",
        "app_launchpad",
        "time_machine",
        "health_timeline",
        "activity_center",
        "archives",
        "command_console",
        "live_console",
        "nexus",
        "forge_arsenal",
        "companion_link",
        "members",
        "galaxy",
        "about",
    }
    assert set(routes) <= set(FEATURES)
    assert [group.title for group in NAVIGATION_GROUPS] == [
        "HOME",
        "ROM WORKSHOP",
        "DEVICE",
        "GUARDIAN & RECOVERY",
        "ACTIVITY & KNOWLEDGE",
        "LIVE OPERATIONS",
        "CONNECTED ROMVERSE",
        "SYSTEM",
    ]
    assert navigation_section("guardian_core") == "GUARDIAN & RECOVERY"
    assert navigation_section("about") == "SYSTEM"
    assert {"command_console", "nexus", "forge_arsenal"} == EXPERT_ONLY_ROUTES
    with pytest.raises(KeyError):
        navigation_section("missing")


def test_workspace_shell_state_preserves_navigation_choice_through_focus() -> None:
    initial = WorkspaceShellState()
    collapsed = initial.toggle_navigation()
    focused = collapsed.toggle_focus()
    restored = focused.toggle_focus()

    assert initial == WorkspaceShellState(navigation_collapsed=False, focus_mode=False)
    assert collapsed == WorkspaceShellState(navigation_collapsed=True, focus_mode=False)
    assert focused == WorkspaceShellState(navigation_collapsed=True, focus_mode=True)
    assert restored == collapsed
