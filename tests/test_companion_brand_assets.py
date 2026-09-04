from __future__ import annotations

import struct
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESKTOP_ASSETS = ROOT / "src" / "romverse" / "assets"
COMPANION_RES = ROOT / "companion" / "app" / "src" / "main" / "res"
ANDROID = "{http://schemas.android.com/apk/res/android}"


def _png_size(path: Path) -> tuple[int, int]:
    payload = path.read_bytes()
    assert payload[:8] == b"\x89PNG\r\n\x1a\n"
    assert payload[12:16] == b"IHDR"
    return struct.unpack(">II", payload[16:24])


def _png_color_type(path: Path) -> int:
    payload = path.read_bytes()
    assert payload[12:16] == b"IHDR"
    return payload[25]


def test_companion_uses_exact_approved_desktop_brand_masters() -> None:
    assert (COMPANION_RES / "drawable-nodpi" / "romverse_app_icon.png").read_bytes() == (
        DESKTOP_ASSETS / "romverse-app-icon.png"
    ).read_bytes()
    assert (COMPANION_RES / "drawable-nodpi" / "radforge_labs_official_logo.png").read_bytes() == (
        DESKTOP_ASSETS / "radforge-labs-official-logo-transparent.png"
    ).read_bytes()


def test_companion_launcher_icons_cover_every_android_density() -> None:
    expected = {
        "mdpi": 48,
        "hdpi": 72,
        "xhdpi": 96,
        "xxhdpi": 144,
        "xxxhdpi": 192,
    }
    for density, size in expected.items():
        directory = COMPANION_RES / f"mipmap-{density}"
        launcher = directory / "ic_launcher.png"
        round_launcher = directory / "ic_launcher_round.png"
        assert _png_size(launcher) == (size, size)
        assert _png_size(round_launcher) == (size, size)
        assert _png_color_type(launcher) == 6  # RGBA; no pasted-on square corners.
        assert _png_color_type(round_launcher) == 6
        assert round_launcher.read_bytes() != launcher.read_bytes()


def test_companion_launcher_uses_approved_logo_as_an_adaptive_icon() -> None:
    foreground = ET.parse(COMPANION_RES / "drawable" / "ic_launcher_foreground.xml").getroot()
    assert foreground.tag == "inset"
    assert foreground.get(f"{ANDROID}drawable") == "@drawable/romverse_app_icon"
    assert {
        foreground.get(f"{ANDROID}insetLeft"),
        foreground.get(f"{ANDROID}insetTop"),
        foreground.get(f"{ANDROID}insetRight"),
        foreground.get(f"{ANDROID}insetBottom"),
    } == {"18dp"}

    for name in ("ic_launcher.xml", "ic_launcher_round.xml"):
        adaptive = ET.parse(COMPANION_RES / "mipmap-anydpi-v26" / name).getroot()
        assert adaptive.tag == "adaptive-icon"
        assert adaptive.find("background").get(f"{ANDROID}drawable") == (
            "@color/romverse_launcher_background"
        )
        assert adaptive.find("foreground").get(f"{ANDROID}drawable") == (
            "@drawable/ic_launcher_foreground"
        )
