from __future__ import annotations

import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESKTOP_ASSETS = ROOT / "src" / "romverse" / "assets"
COMPANION_RES = ROOT / "companion" / "app" / "src" / "main" / "res"


def _png_size(path: Path) -> tuple[int, int]:
    payload = path.read_bytes()
    assert payload[:8] == b"\x89PNG\r\n\x1a\n"
    assert payload[12:16] == b"IHDR"
    return struct.unpack(">II", payload[16:24])


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
        assert round_launcher.read_bytes() == launcher.read_bytes()
