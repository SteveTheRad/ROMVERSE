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
        "THIRD_PARTY_NOTICES.txt",
    )

    missing = [name for name in required if not assets.joinpath(name).is_file()]

    assert missing == []
