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


def contains_bootloader_lock_action_id(value: str) -> bool:
    """Reject separator and compact lock/relock variants in structured action IDs."""

    if not isinstance(value, str):
        return True
    tokens = re.sub(r"[^a-z0-9]+", " ", value.casefold()).split()
    compact = "".join(tokens)
    return bool(
        any(token == "relock" or token.startswith("relock") for token in tokens)
        or "relockbootloader" in compact
        or any(
            phrase in compact
            for phrase in (
                "bootloaderlock",
                "lockbootloader",
                "flashinglock",
                "lockflashing",
                "oemlock",
                "lockoem",
                "criticallock",
                "lockcritical",
            )
        )
    )
