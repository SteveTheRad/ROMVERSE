#!/usr/bin/env python3
from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from romverse.device_packs.companion_export import render_companion_kotlin
from romverse.device_packs.registry import DevicePackRegistry


def main() -> None:
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    if registry.issues:
        raise SystemExit(f"Device Pack registry is invalid: {registry.issues}")
    root = Path(__file__).resolve().parents[1]
    destination = (
        root
        / "companion/app/src/main/kotlin/com/radforge/romverse/companion/GeneratedDeviceAtlasPacks.kt"
    )
    destination.write_text(render_companion_kotlin(registry), encoding="utf-8")
    print(f"updated {destination.relative_to(root)}")


if __name__ == "__main__":
    main()
