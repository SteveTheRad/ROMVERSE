from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANDROID = "{http://schemas.android.com/apk/res/android}"


def test_facebook_mark_is_a_crisp_untinted_two_tone_vector() -> None:
    resource = ROOT / "companion/app/src/main/res/drawable/ic_facebook_f.xml"
    vector = ET.parse(resource).getroot()
    paths = vector.findall("path")

    assert vector.get(f"{ANDROID}viewportWidth") == "24"
    assert vector.get(f"{ANDROID}viewportHeight") == "24"
    assert vector.get(f"{ANDROID}tint") is None
    assert [path.get(f"{ANDROID}fillColor") for path in paths] == ["#1877F2", "#FFFFFF"]
    assert all(len(path.get(f"{ANDROID}pathData", "")) > 20 for path in paths)


def test_reddit_mark_is_a_crisp_untinted_two_tone_vector() -> None:
    resource = ROOT / "companion/app/src/main/res/drawable/ic_reddit.xml"
    vector = ET.parse(resource).getroot()
    paths = vector.findall("path")

    assert vector.get(f"{ANDROID}viewportWidth") == "24"
    assert vector.get(f"{ANDROID}viewportHeight") == "24"
    assert vector.get(f"{ANDROID}tint") is None
    assert [path.get(f"{ANDROID}fillColor") for path in paths] == ["#FF4500", "#FFFFFF"]
    assert all(len(path.get(f"{ANDROID}pathData", "")) > 20 for path in paths)


def test_official_website_marks_are_crisp_untinted_vectors() -> None:
    for name in ("ic_romverse_web.xml", "ic_radforge_labs.xml"):
        resource = ROOT / "companion/app/src/main/res/drawable" / name
        vector = ET.parse(resource).getroot()
        paths = vector.findall("path")

        assert vector.get(f"{ANDROID}viewportWidth") == "48"
        assert vector.get(f"{ANDROID}viewportHeight") == "48"
        assert vector.get(f"{ANDROID}tint") is None
        assert len(paths) >= 2
        assert all(len(path.get(f"{ANDROID}pathData", "")) > 20 for path in paths)


def test_about_uses_a_standalone_social_icon_instead_of_button_tinting() -> None:
    source = (
        ROOT / "companion/app/src/main/kotlin/com/radforge/romverse/companion/MainActivity.kt"
    ).read_text(encoding="utf-8")

    assert 'socialAction(\n                    "Facebook"' in source
    assert "R.drawable.ic_facebook_f" in source
    assert 'socialAction(\n                    "Reddit"' in source
    assert "R.drawable.ic_reddit" in source
    assert 'const val FACEBOOK_URL = "https://www.facebook.com/ROMVERSEOfficial"' in source
    assert 'const val REDDIT_URL = "https://www.reddit.com/user/ROMVERSE/"' in source
    assert 'const val ROMVERSE_WEBSITE_URL = "https://romverse.app/"' in source
    assert 'const val RADFORGE_LABS_URL = "https://radforgelabs.com/"' in source
    assert 'openOfficialPage(ROMVERSE_WEBSITE_URL, "romverse.app", "website")' in source
    assert (
        'openOfficialPage(RADFORGE_LABS_URL, "radforgelabs.com", "RadForge Labs website")' in source
    )
    assert "R.drawable.ic_romverse_web" in source
    assert "R.drawable.ic_radforge_labs" in source
    assert "utm_" not in source
    assert "setCompoundDrawablesRelativeWithIntrinsicBounds" not in source
    assert "CompanionLayoutSpec.CONTENT_HORIZONTAL_DP" in source


def test_about_origin_is_double_tap_discovered_replayable_and_honest() -> None:
    source = (
        ROOT / "companion/app/src/main/kotlin/com/radforge/romverse/companion/MainActivity.kt"
    ).read_text(encoding="utf-8")

    assert "now - lastMarkTap in 40..420" in source
    assert '.putBoolean("origin_discovered", true)' in source
    assert '.putBoolean("beyond_the_verse_discovered", true)' in source
    assert "EXPERIENCE THE ORIGIN AGAIN" in source
    assert "Discovery is recorded locally; " in source
    assert "account XP is never simulated." in source
    assert 'userSettingsPrefs.getBoolean("reduced_motion", false)' in source


def test_origin_is_a_vertical_scene_experience_with_all_required_controls() -> None:
    source = (
        ROOT / "companion/app/src/main/kotlin/com/radforge/romverse/companion/MainActivity.kt"
    ).read_text(encoding="utf-8")

    assert source.count("CompanionOriginScene(") == 8  # declaration plus seven scenes
    assert "What if Android ROM development could be powerful without being intimidating?" in source
    assert "Never hide uncertainty behind a green tick." in source
    assert "ROMVERSE started as an idea I wanted to see exist." in source
    assert "Personal recognition appears only" in source
    assert 'originControl("Sound Off")' in source
    assert '"Reduced Effects On"' in source
    assert 'originControl("Pause")' in source
    assert 'originControl("Skip to Finale")' in source
    assert 'originControl("Exit / Return to ROMVERSE")' in source
    assert "R.raw.origin_ambient" in source
    assert "supporterHandler.postDelayed" in source


def test_home_identity_uses_an_optically_balanced_centered_lockup() -> None:
    source = (
        ROOT / "companion/app/src/main/kotlin/com/radforge/romverse/companion/MainActivity.kt"
    ).read_text(encoding="utf-8")
    identity_start = source.index("val homeIdentity = LinearLayout(this).apply")
    identity_end = source.index("page.addView(homeIdentity)", identity_start)
    identity_source = source[identity_start:identity_end]

    assert 'text("ROMVERSE COMPANION", 13f' in identity_source
    assert 'text("YOUR ANDROID SIDEKICK", 10f' in identity_source
    assert 'text("ROMVERSE COMPANION  •  YOUR ANDROID SIDEKICK"' not in identity_source
    assert 'text("A RADFORGE LABS PROJECT"' in identity_source
    assert 'text("Monitor. Understand. Stay connected."' in identity_source
    assert "layoutParams = LinearLayout.LayoutParams(-1, -2)" in identity_source
    assert identity_source.count("textAlignment = View.TEXT_ALIGNMENT_CENTER") == 4


def test_companion_shell_wires_the_bounded_edge_swipe_drawer() -> None:
    source = (
        ROOT / "companion/app/src/main/kotlin/com/radforge/romverse/companion/MainActivity.kt"
    ).read_text(encoding="utf-8")
    drawer = (
        ROOT
        / "companion/app/src/main/kotlin/com/radforge/romverse/companion/RomverseDrawerLayout.kt"
    ).read_text(encoding="utf-8")

    assert "val root = RomverseDrawerLayout(this).apply" in source
    assert "CompanionEdgeSwipeTracker(" in drawer
    assert "systemGestureExclusionRects" in drawer
    assert "openDrawer(GravityCompat.START, true)" in drawer


def test_companion_experience_switch_is_persisted_and_progressively_discloses_dna() -> None:
    source = (
        ROOT / "companion/app/src/main/kotlin/com/radforge/romverse/companion/MainActivity.kt"
    ).read_text(encoding="utf-8")

    assert 'putString("experience_mode", savedMode.persistedValue)' in source
    assert 'text = "Guided\\nArcana"' in source
    assert 'text = "Expert\\nArchitect"' in source
    assert "CompanionExperiencePolicy.initialCapabilityCount(" in source
    assert "TECHNICAL EVIDENCE REVEALED" in source
    assert "bootloader-relock prohibition remain unchanged" in source


def test_companion_home_prioritizes_one_evidence_backed_three_second_hero() -> None:
    source = (
        ROOT / "companion/app/src/main/kotlin/com/radforge/romverse/companion/MainActivity.kt"
    ).read_text(encoding="utf-8")

    assert "CompanionHomeHeroPolicy.choose(" in source
    assert 'homeHeroLink = text("?  ROMVERSE LINK' in source
    assert 'homeHeroGuardian = text("?  GUARDIAN' in source
    assert 'homeHeroMission = text("?  DESKTOP MISSION' in source
    assert source.index("page.addView(homeHero)") < source.index("page.addView(galaxyDashboard)")
