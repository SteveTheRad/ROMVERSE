from __future__ import annotations

import pytest

from romverse.guardian.ascension_transfer import (
    ASCENSION_OUTPUT_LIST_COMMAND,
    ASCENSION_OUTPUT_NAME,
    ascension_output_matches_method,
    ascension_output_method,
)


@pytest.mark.parametrize(
    ("name", "method", "matches"),
    (
        ("magisk_patched-27000_abcd.img", "magisk", True),
        ("MAGISK-PATCHED-31000.img", "magisk", True),
        ("KernelSU_patched-android16.img", "kernelsu_lkm", True),
        ("kernelsu-restore-backup.img", "kernelsu_lkm", True),
        ("KernelSU_patched-android16.img", "magisk", False),
        ("magisk_patched-27000_abcd.img", "kernelsu_lkm", False),
        ("magisk_patched.img", "unknown", False),
    ),
)
def test_ascension_output_name_is_bound_to_selected_method(
    name: str,
    method: str,
    matches: bool,
) -> None:
    assert ascension_output_matches_method(name, method) is matches


def test_ascension_output_scan_is_filename_only_and_newest_first() -> None:
    assert ASCENSION_OUTPUT_LIST_COMMAND == (
        "shell",
        "ls",
        "-1t",
        "/sdcard/Download",
    )


def test_ascension_output_classifier_never_guesses_unknown_names() -> None:
    assert ascension_output_method("magisk_patched-31000.img") == "magisk"
    assert ascension_output_method("KernelSU_restore-stock.img") == "kernelsu_lkm"
    assert ascension_output_method("custom-root-output.img") is None


@pytest.mark.parametrize(
    "name",
    (
        "magisk_patched.img",
        "KernelSU_patched-android16.img",
        "kernelsu_restore-backup.img",
    ),
)
def test_guardian_shared_allowlist_still_accepts_supported_manager_outputs(name: str) -> None:
    assert ASCENSION_OUTPUT_NAME.fullmatch(name)


@pytest.mark.parametrize(
    "name",
    (
        "magisk_patched.zip",
        "magisk_patched/escape.img",
        "../magisk_patched.img",
        "KernelSU_patched.img;reboot",
        "ordinary-boot.img",
    ),
)
def test_guardian_shared_allowlist_rejects_unsafe_or_unrelated_names(name: str) -> None:
    assert ASCENSION_OUTPUT_NAME.fullmatch(name) is None
