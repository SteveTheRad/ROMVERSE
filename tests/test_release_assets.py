from hashlib import sha256
from importlib.resources import files


def test_required_release_branding_and_device_art_are_packaged() -> None:
    assets = files("romverse.assets")
    required = (
        "romverse-app-icon.png",
        "romverse-app-icon.ico",
        "romverse-brand.png",
        "romverse-r.png",
        "product-family.png",
        "dashboard-phone.png",
        "sidebar-phone-white.png",
        "romverse-origin-living-chronicle-v2.png",
    )

    missing = [name for name in required if not assets.joinpath(name).is_file()]

    assert missing == []


def test_desktop_uses_the_byte_exact_production_romverse_app_assets() -> None:
    assets = files("romverse.assets")

    assert sha256(assets.joinpath("romverse-app-icon.png").read_bytes()).hexdigest() == (
        "ab9286ce69e77abd82fe88105df70680186a4eb992289580c23f5d362c132a18"
    )
    assert sha256(assets.joinpath("romverse-brand.png").read_bytes()).hexdigest() == (
        "7c85d0c8b7f62d3f757243e6ca336daf78078d04550b264323135cf4e1beb98a"
    )
    assert (
        sha256(assets.joinpath("romverse-origin-living-chronicle-v2.png").read_bytes()).hexdigest()
        == "7b185313ba8df9a6d189ff55c7fd79e58a3c2244b7c718a56d1cbc4996844f9b"
    )
