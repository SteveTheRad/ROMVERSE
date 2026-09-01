from __future__ import annotations

from dataclasses import replace

from romverse.ascension.entry import (
    AscensionEntryState,
    build_ascension_entry_brief,
)
from romverse.ascension.models import AscensionMethod
from romverse.ascension.route import AscensionRouteRecord


def _record() -> AscensionRouteRecord:
    return AscensionRouteRecord(
        schema_version=2,
        project_id="project-1",
        created_at="2026-08-30T00:00:00+00:00",
        state="ready-local-only",
        confidence="verified",
        candidate_method=AscensionMethod.MAGISK,
        recommended_method=AscensionMethod.MAGISK,
        ready_for_local_preparation=True,
        title="Magisk image patch recommended",
        reason="Exact evidence permits contained local preparation.",
        patch_target="init_boot.img",
        evidence=("Exact source verified", "Device DNA identity supported"),
        blocker_count=0,
        source_original_sha256="a" * 64,
        source_authority="device-pack",
        source_codename="popsicle",
        device_dna_digest="b" * 64,
        device_dna_identity_state="supported",
        device_key="device-key",
        device_name="Xiaomi 17 Pro Max",
        device_codename="popsicle",
        kernel_version="6.12.23-android16",
        execution_authority="none",
        command_manifest=(),
        bootloader_relock_allowed=False,
        phone_changed=False,
        record_digest="c" * 64,
    )


def test_verified_matching_route_becomes_a_supported_beginner_recommendation() -> None:
    brief = build_ascension_entry_brief(_record(), device_matches=True)

    assert brief.state is AscensionEntryState.SUPPORTED
    assert brief.method is AscensionMethod.MAGISK
    assert brief.method_label == "Magisk"
    assert brief.patch_target == "init_boot.img"
    assert brief.rooted_button_label == "Yes • Use Magisk in Ascension"
    assert "Phone changed now: NO" in brief.guidance()
    assert "Execution authority: NONE" in brief.guidance()
    assert "Bootloader relock: NEVER" in brief.guidance()


def test_nonverified_local_candidate_is_caution_not_supported() -> None:
    brief = build_ascension_entry_brief(
        replace(_record(), confidence="high"),
        device_matches=True,
    )

    assert brief.state is AscensionEntryState.CAUTION
    assert brief.method is AscensionMethod.MAGISK
    assert "Review candidate" in brief.rooted_button_label


def test_device_mismatch_never_reuses_the_saved_method() -> None:
    brief = build_ascension_entry_brief(_record(), device_matches=False)

    assert brief.state is AscensionEntryState.UNCONFIRMED
    assert brief.method is None
    assert brief.patch_target == ""
    assert "does not match" in brief.title


def test_blocked_route_explains_the_candidate_but_recommends_no_method() -> None:
    record = replace(
        _record(),
        state="blocked",
        confidence="unconfirmed",
        recommended_method=None,
        ready_for_local_preparation=False,
        blocker_count=1,
        title="Complete source and device checks first",
    )

    brief = build_ascension_entry_brief(record, device_matches=True)

    assert brief.state is AscensionEntryState.BLOCKED
    assert brief.method is None
    assert brief.rooted_button_label == "Review blockers in Ascension Protocol"


def test_unsafe_route_boundary_is_rejected_before_display() -> None:
    brief = build_ascension_entry_brief(
        replace(_record(), execution_authority="flash", command_manifest=("fastboot flash",)),
        device_matches=True,
    )

    assert brief.state is AscensionEntryState.BLOCKED
    assert brief.method is None
    assert "Guardian boundary" in brief.title


def test_missing_or_failed_scan_remains_explicitly_unconfirmed() -> None:
    missing = build_ascension_entry_brief(None)
    failed = build_ascension_entry_brief(None, error="Device DNA unavailable")

    assert missing.state is AscensionEntryState.UNCONFIRMED
    assert missing.method is None
    assert "No root method is being guessed" in missing.summary
    assert failed.evidence == ("Device DNA unavailable",)
