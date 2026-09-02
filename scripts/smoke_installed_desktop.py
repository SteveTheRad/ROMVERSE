from __future__ import annotations

import argparse
from importlib.resources import files
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QLockFile
from PySide6.QtWidgets import QApplication

from romverse import app as romverse_app
from romverse.device_packs.registry import DevicePackRegistry
from romverse.knowledge.archives import CANONICAL_ROUTES, KNOWN_FIXES
from romverse.ui import main_window as main_window_module
from romverse.ui.backup_center import BackupCenter
from romverse.ui.knowledge_center import ARCHIVE_ARTICLES
from romverse.ui.theme import STYLESHEET, apply_dark_palette
from romverse.ui.workspace_shell import NAVIGATION_GROUPS


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test an installed ROMVERSE desktop wheel")
    parser.add_argument("workspace", type=Path)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    smoke_lock = workspace.parent / f".{workspace.name}.romverse-smoke.lock"

    QApplication.exec = lambda _self: 0  # type: ignore[method-assign]
    # A developer may be exercising the real Desktop while CI validates an installed
    # wheel. Preserve production's single-instance lock and redirect only this in-process
    # smoke launch to a unique temporary lock beside its disposable workspace.
    with (
        patch.object(
            romverse_app,
            "QLockFile",
            side_effect=lambda _production_path: QLockFile(str(smoke_lock)),
        ),
        # The smoke replaces QApplication.exec, so a real asynchronous device scan
        # would outlive the temporary MainWindow. Production launches retain the
        # normal managed worker; this harness validates startup without orphaning it.
        patch.object(main_window_module, "start_background"),
    ):
        result = romverse_app.main(
            ["--workspace", str(workspace), "--skip-onboarding"],
        )
        launched_app = QApplication.instance()
        if launched_app is not None:
            for widget in launched_app.topLevelWidgets():
                widget.close()
            launched_app.processEvents()
    if result != 0 or not (workspace / ".romverse-workspace.json").is_file():
        raise RuntimeError("Installed desktop did not initialize a fresh workspace")

    assets = files("romverse.assets")
    registry = DevicePackRegistry.load(assets.joinpath("device_packs"))
    if registry.issues or not registry.packs:
        raise RuntimeError("Installed desktop could not verify packaged Device Packs")
    for name in ("product-family.png", "romverse-mark.svg", "romverse-app-icon.png"):
        if not assets.joinpath(name).is_file():
            raise RuntimeError(f"Installed desktop asset is missing: {name}")
    required_handoffs = {
        "time-machine-empty-state-dead-end",
        "command-console-no-trusted-result",
        "health-timeline-comparison-unavailable",
        "members-service-unavailable-or-unconfigured",
        "galaxy-local-publishing-boundary",
        "nexus-current-evidence-route-unavailable",
        "command-palette-nested-feature-missing",
        "synapse-evidence-opens-wrong-workspace",
        "nexus-intelligence-feature-opens-generic-page",
        "architect-mode-does-not-change-desktop",
        "fastboot-identity-only",
    }
    installed_handoffs = {item.key for item in KNOWN_FIXES}
    if missing := required_handoffs - installed_handoffs:
        raise RuntimeError(f"Installed Archives are missing recovery handoffs: {sorted(missing)}")
    desktop_routes = {route for group in NAVIGATION_GROUPS for route in group.routes}
    archive_routes = {article.route for article in ARCHIVE_ARTICLES}
    if desktop_routes - CANONICAL_ROUTES or desktop_routes - archive_routes:
        raise RuntimeError("Installed Archives do not cover every desktop route")

    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    apply_dark_palette(app)
    app.setStyleSheet(STYLESHEET)
    time_machine = BackupCenter(workspace)
    requested: list[str] = []
    time_machine.rom_studio_setup_requested.connect(requested.append)
    time_machine.resize(1_200, 760)
    time_machine.show()
    app.processEvents()
    try:
        if (
            not time_machine.local_setup.isVisibleTo(time_machine)
            or not time_machine.local_setup_button.isEnabled()
        ):
            raise RuntimeError("Installed Time Machine has no fresh-workspace recovery route")
        time_machine.local_setup_button.click()
        if requested != [""]:
            raise RuntimeError("Installed Time Machine did not preserve empty project identity")
        viewport = time_machine.snapshot_list.viewport().grab().toImage()
        if viewport.pixelColor(8, 8).lightness() >= 64:
            raise RuntimeError("Installed Time Machine inherited a light host viewport")
    finally:
        time_machine.close()
    print(
        f"Installed ROMVERSE desktop smoke passed with {len(registry.packs)} Device Packs, "
        f"{len(KNOWN_FIXES)} known fixes, {len(desktop_routes)} covered desktop routes, "
        "and a connected dark Time Machine empty state"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
