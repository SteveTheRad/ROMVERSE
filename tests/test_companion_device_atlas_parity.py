from importlib.resources import files
from pathlib import Path

from romverse.device_packs.companion_export import render_companion_kotlin
from romverse.device_packs.registry import DevicePackRegistry


def test_companion_device_atlas_is_generated_from_verified_desktop_packs():
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    assert registry.issues == ()
    generated = Path(
        "companion/app/src/main/kotlin/com/radforge/romverse/companion/GeneratedDeviceAtlasPacks.kt"
    )

    assert generated.read_text(encoding="utf-8") == render_companion_kotlin(registry)
