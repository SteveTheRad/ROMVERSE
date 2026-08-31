from __future__ import annotations

import re


def contains_bootloader_relock(commands: tuple[tuple[str, ...], ...]) -> bool:
    """Recognize relock intent without misclassifying read-only 'unlocked' evidence."""

    forbidden_phrases = (
        "flashing lock",
        "flashing lock_critical",
        "oem lock",
        "oem relock",
        "lock bootloader",
        "relock bootloader",
    )
    for command in commands:
        normalized = " ".join(str(token).strip().casefold() for token in command)
        if any(phrase in normalized for phrase in forbidden_phrases) or re.search(
            r"(?:^|\s)--?(?:re)?lock(?:\s|$)", normalized
        ):
            return True
    return False
