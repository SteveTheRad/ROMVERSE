from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OriginScene:
    """One public-facing chapter of ROMVERSE: The Origin.

    The copy deliberately describes ROMVERSE's values and outcomes without exposing
    implementation rules, matching logic, confidence formulas, or security internals.
    """

    key: str
    eyebrow: str
    title: str
    body: str
    constellation: str
    duration_ms: int


ORIGIN_SCENES = (
    OriginScene(
        key="beginning",
        eyebrow="SCENE 01  •  THE BEGINNING",
        title="EVERY PROJECT BEGINS WITH AN IDEA",
        body=(
            "ROMVERSE began with a question.\n\n"
            "What if Android ROM development could be powerful without being intimidating?\n\n"
            "A distant point of light becomes the first shape of a new Android universe."
        ),
        constellation="IDEA  •  POSSIBILITY  •  BEGIN",
        duration_ms=11_000,
    ),
    OriginScene(
        key="vision",
        eyebrow="SCENE 02  •  THE VISION",
        title="A BETTER WAY TO BRING IT TOGETHER",
        body=(
            "Not another collection of tools. A connected experience that helps people build, "
            "understand, protect, verify, and learn.\n\n"
            "ROM Studio, Device DNA, Nexus, Guardian, and Companion share one purpose while the "
            "technology that protects their work remains private."
        ),
        constellation="BUILD  •  UNDERSTAND  •  PROTECT  •  VERIFY  •  LEARN",
        duration_ms=13_000,
    ),
    OriginScene(
        key="promise",
        eyebrow="SCENE 03  •  THE ROMVERSE PROMISE",
        title="REAL PROGRESS. REAL EVIDENCE.",
        body=(
            "Never pretend something worked when it didn't.\n\n"
            "Never hide uncertainty behind a green tick.\n\n"
            "Never take control away from the person whose device it is.\n\n"
            "Build powerful automation without forgetting responsibility.\n\n"
            "Your device. Your decision."
        ),
        constellation="HONESTY  •  EVIDENCE  •  RESPONSIBILITY",
        duration_ms=16_000,
    ),
    OriginScene(
        key="founder",
        eyebrow="SCENE 04  •  A MESSAGE FROM STEVETHERAD",
        title="WHY ROMVERSE EXISTS",
        body=(
            "ROMVERSE started as an idea I wanted to see exist.\n\n"
            "Something that could take the complicated world of Android ROM development and make "
            "it more understandable, more capable, and safer—without taking away the freedom that "
            "makes Android special.\n\n"
            "What began as an idea became a much bigger vision: a place where someone building "
            "their first ROM and someone who has been doing this for years can work with the same "
            "powerful tools, at their own level.\n\n"
            "ROMVERSE will continue to grow, learn, and improve. But no matter how advanced it "
            "becomes, I want it to remain true to the principles it started with.\n\n"
            "Respect the user. Respect the device. Be honest about what we know. Never fake "
            "success. And most importantly—never stop building.\n\n"
            "Thank you for being part of ROMVERSE.\n\n"
            "— SteveTheRad\nFounder & Creator of ROMVERSE"
        ),
        constellation="RESPECT THE USER  •  RESPECT THE DEVICE",
        duration_ms=25_000,
    ),
    OriginScene(
        key="community",
        eyebrow="SCENE 05  •  THE COMMUNITY",
        title="ONE IDEA CAN BECOME SOMETHING GREATER",
        body=(
            "One point of light becomes several, then many. They are a symbol—not a fabricated "
            "user count.\n\n"
            "To everyone who builds, tests, reports, creates, helps, and believes in what ROMVERSE "
            "can become: thank you.\n\n"
            "Personal recognition appears only when genuine account evidence says it has been "
            "earned. ROMVERSE never invents a badge, membership milestone, or reward."
        ),
        constellation="BUILDERS  •  TESTERS  •  CREATORS  •  COMMUNITY",
        duration_ms=15_000,
    ),
    OriginScene(
        key="future",
        eyebrow="SCENE 06  •  THE FUTURE",
        title="WE'RE ONLY GETTING STARTED",
        body=(
            "Desktop, Companion, and Android device move together through one expanding universe.\n\n"
            "Build what wasn't possible yesterday.\n"
            "Understand what others leave unexplained.\n"
            "Protect what matters.\n"
            "Perfect what comes next."
        ),
        constellation="DESKTOP  •  COMPANION  •  ANDROID",
        duration_ms=14_000,
    ),
    OriginScene(
        key="finale",
        eyebrow="THE ORIGIN  •  FINALE",
        title="ROMVERSE",
        body=(
            "BUILD. OPTIMIZE. PERFECT.\n\n"
            "Created by SteveTheRad\n"
            "A RadForge Labs Project\n\n"
            "To every supporter, tester, builder, curious newcomer, and person who shared an idea: "
            "thank you. Your time, trust, patience, and belief are part of this universe.\n\n"
            "ROMVERSE is being built for you—and it is better because you are here.\n\n"
            "Made for the people who refuse to stop tinkering.\n\n"
            "27.08.2026"
        ),
        constellation="THE JOURNEY IS ONLY BEGINNING",
        duration_ms=13_000,
    ),
)


def origin_total_duration_ms() -> int:
    return sum(scene.duration_ms for scene in ORIGIN_SCENES)
