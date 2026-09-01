from __future__ import annotations

import argparse
from importlib.resources import files
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QLockFile
from PySide6.QtWidgets import QApplication

from romverse import app as romverse_app
from romverse.device_packs.registry import DevicePackRegistry


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
    with patch.object(
        romverse_app,
        "QLockFile",
        side_effect=lambda _production_path: QLockFile(str(smoke_lock)),
    ):
        result = romverse_app.main(
            ["--workspace", str(workspace), "--skip-onboarding"],
        )
    if result != 0 or not (workspace / ".romverse-workspace.json").is_file():
        raise RuntimeError("Installed desktop did not initialize a fresh workspace")

    assets = files("romverse.assets")
    registry = DevicePackRegistry.load(assets.joinpath("device_packs"))
    if registry.issues or not registry.packs:
        raise RuntimeError("Installed desktop could not verify packaged Device Packs")
    for name in ("product-family.png", "romverse-mark.svg", "romverse-app-icon.png"):
        if not assets.joinpath(name).is_file():
            raise RuntimeError(f"Installed desktop asset is missing: {name}")
    print(f"Installed ROMVERSE desktop smoke passed with {len(registry.packs)} Device Packs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
