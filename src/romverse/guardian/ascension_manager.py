from __future__ import annotations

import re
from pathlib import PurePosixPath

ASCENSION_MANAGER_PACKAGES = frozenset(
    {
        "com.topjohnwu.magisk",
        "me.weishu.kernelsu",
    }
)
ASCENSION_MANAGER_LAUNCH_CATEGORY = "android.intent.category.LAUNCHER"


def manager_path_arguments(serial: str, package_name: str) -> tuple[str, ...]:
    _validate_serial(serial)
    _validate_package(package_name)
    return ("-s", serial, "shell", "pm", "path", package_name)


def manager_launch_arguments(serial: str, package_name: str) -> tuple[str, ...]:
    _validate_serial(serial)
    _validate_package(package_name)
    return (
        "-s",
        serial,
        "shell",
        "monkey",
        "-p",
        package_name,
        "-c",
        ASCENSION_MANAGER_LAUNCH_CATEGORY,
        "1",
    )


def installed_manager_path(value: str) -> bool:
    """Accept only a bounded base APK path inside Android's app-install root."""

    if not isinstance(value, str) or not 24 <= len(value) <= 768:
        return False
    if any(ord(character) < 32 for character in value):
        return False
    # This is a path on the Android device, never a host path.  Host-native
    # ``Path`` would reinterpret it with Windows separators and reject a valid
    # package path before Guardian review.
    path = PurePosixPath(value)
    parts = path.parts
    return bool(
        path.is_absolute()
        and len(parts) in range(5, 11)
        and parts[:3] == ("/", "data", "app")
        and parts[-1] == "base.apk"
        and all(
            part not in {"", ".", ".."} and re.fullmatch(r"[A-Za-z0-9._~+=-]{1,180}", part)
            for part in parts[3:-1]
        )
    )


def _validate_serial(value: str) -> None:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 256
        or any(ord(character) < 33 for character in value)
    ):
        raise ValueError("Ascension manager device identity is invalid")


def _validate_package(value: str) -> None:
    if value not in ASCENSION_MANAGER_PACKAGES:
        raise ValueError("Ascension manager package is not allowlisted")
