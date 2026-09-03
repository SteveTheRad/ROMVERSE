from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from romverse.rom.ota_metadata import AndroidOtaMetadata
from romverse.rom.source_identity import xiaomi_build_region


class FirmwareRelationship(StrEnum):
    UPGRADE = "upgrade"
    SAME = "same"
    DOWNGRADE = "downgrade"
    INCOMPATIBLE = "incompatible"
    UNCONFIRMED = "unconfirmed"


@dataclass(frozen=True, slots=True)
class FirmwareUpgradeAssessment:
    relationship: FirmwareRelationship
    current_build: str
    candidate_build: str
    device_codename: str
    candidate_codename: str
    current_region: str
    candidate_region: str
    summary: str
    reasons: tuple[str, ...]
    user_supplied_source: bool = True
    install_authority: bool = False
    phone_changed: bool = False


USER_FIRMWARE_RESPONSIBILITY_NOTICE = (
    "Firmware files are selected and supplied by you. You are responsible for confirming that a "
    "package came from a trusted official source and is intended for your exact model, region, "
    "and current update path. ROMVERSE does not provide, endorse, or warrant user-supplied "
    "firmware and cannot guarantee third-party provenance. Firmware changes can cause data loss "
    "or device failure and remain at your own risk. Import and upgrade detection grant no "
    "installation or flash authority. Nothing in this notice excludes rights or obligations that "
    "cannot legally be excluded."
)


@dataclass(frozen=True, slots=True)
class _XiaomiBuild:
    raw: str
    version: tuple[int, ...]
    branch: str
    region: str


_XIAOMI_BUILD = re.compile(
    r"^OS(?P<version>[0-9]+(?:\.[0-9]+){2,4})\.(?P<branch>[A-Z0-9]{4,20})$",
    re.IGNORECASE,
)


def assess_firmware_upgrade(
    *,
    current_build: str,
    candidate_build: str,
    device_codename: str,
    candidate_codename: str,
    current_fingerprint: str = "",
    current_incremental: str = "",
    current_sdk_level: str = "",
    current_build_timestamp: int | None = None,
    device_aliases: tuple[str, ...] = (),
    ota_metadata: AndroidOtaMetadata | None = None,
) -> FirmwareUpgradeAssessment:
    """Classify a conservative firmware relationship without granting install authority."""

    if ota_metadata is not None:
        return _assess_android_ota(
            current_build=current_build,
            candidate_build=candidate_build,
            device_codename=device_codename,
            candidate_codename=candidate_codename,
            current_fingerprint=current_fingerprint,
            current_incremental=current_incremental,
            current_sdk_level=current_sdk_level,
            current_build_timestamp=current_build_timestamp,
            device_aliases=device_aliases,
            metadata=ota_metadata,
        )

    current = _parse_xiaomi_build(current_build)
    candidate = _parse_xiaomi_build(candidate_build)
    device = str(device_codename).casefold().strip()
    target = str(candidate_codename).casefold().strip()
    current_text = str(current_build).strip().upper()
    candidate_text = str(candidate_build).strip().upper()

    if device and target and device != target:
        return _assessment(
            FirmwareRelationship.INCOMPATIBLE,
            current_text,
            candidate_text,
            device,
            target,
            current.region if current else "",
            candidate.region if candidate else "",
            "INCOMPATIBLE FIRMWARE",
            (f"Connected device is {device}; candidate firmware targets {target}.",),
        )
    if not device or not target:
        return _assessment(
            FirmwareRelationship.UNCONFIRMED,
            current_text,
            candidate_text,
            device,
            target,
            current.region if current else "",
            candidate.region if candidate else "",
            "UPGRADE STATUS UNCONFIRMED",
            ("Both live device and candidate codenames are required.",),
        )
    if current is None or candidate is None:
        return _assessment(
            FirmwareRelationship.UNCONFIRMED,
            current_text,
            candidate_text,
            device,
            target,
            current.region if current else "",
            candidate.region if candidate else "",
            "UPGRADE STATUS UNCONFIRMED",
            ("Both current and candidate builds need a recognized Xiaomi HyperOS identity.",),
        )
    if not current.region or not candidate.region:
        return _assessment(
            FirmwareRelationship.UNCONFIRMED,
            current.raw,
            candidate.raw,
            device,
            target,
            current.region,
            candidate.region,
            "UPGRADE STATUS UNCONFIRMED",
            ("Both current and candidate firmware regions must be recognized.",),
        )
    if current.region and candidate.region and current.region != candidate.region:
        return _assessment(
            FirmwareRelationship.INCOMPATIBLE,
            current.raw,
            candidate.raw,
            device,
            target,
            current.region,
            candidate.region,
            "INCOMPATIBLE REGION",
            (f"Current region is {current.region}; candidate region is {candidate.region}.",),
        )
    if current.branch != candidate.branch:
        return _assessment(
            FirmwareRelationship.UNCONFIRMED,
            current.raw,
            candidate.raw,
            device,
            target,
            current.region,
            candidate.region,
            "UPGRADE STATUS UNCONFIRMED",
            (
                f"Firmware branch changes from {current.branch} to {candidate.branch}; "
                "a Device Pack upgrade contract is required.",
            ),
        )

    relationship = (
        FirmwareRelationship.UPGRADE
        if candidate.version > current.version
        else FirmwareRelationship.DOWNGRADE
        if candidate.version < current.version
        else FirmwareRelationship.SAME
    )
    label = {
        FirmwareRelationship.UPGRADE: "UPGRADE CANDIDATE",
        FirmwareRelationship.DOWNGRADE: "DOWNGRADE CANDIDATE",
        FirmwareRelationship.SAME: "SAME FIRMWARE VERSION",
    }[relationship]
    return _assessment(
        relationship,
        current.raw,
        candidate.raw,
        device,
        target,
        current.region,
        candidate.region,
        f"{label} • {current.raw} → {candidate.raw}",
        (
            f"Exact codename matched: {device}.",
            f"Firmware branch matched: {current.branch}.",
            f"Firmware region matched: {current.region or 'unconfirmed'}.",
            "Version order was derived from numeric HyperOS components.",
        ),
    )


def _assess_android_ota(
    *,
    current_build: str,
    candidate_build: str,
    device_codename: str,
    candidate_codename: str,
    current_fingerprint: str,
    current_incremental: str,
    current_sdk_level: str,
    current_build_timestamp: int | None,
    device_aliases: tuple[str, ...],
    metadata: AndroidOtaMetadata,
) -> FirmwareUpgradeAssessment:
    live_devices = {
        value.casefold().strip() for value in (device_codename, *device_aliases) if value.strip()
    }
    target_devices = set(metadata.target_devices)
    if not target_devices and candidate_codename.strip():
        target_devices.add(candidate_codename.casefold().strip())
    display_device = device_codename.casefold().strip()
    display_target = (
        sorted(target_devices)[0] if target_devices else candidate_codename.casefold().strip()
    )
    current_label = (
        current_build.strip() or current_incremental.strip() or current_fingerprint.strip()
    )
    candidate_label = (
        candidate_build.strip()
        or metadata.post_build_incremental
        or (metadata.post_builds[0] if metadata.post_builds else "")
    )

    if live_devices and target_devices and live_devices.isdisjoint(target_devices):
        return _assessment(
            FirmwareRelationship.INCOMPATIBLE,
            current_label,
            candidate_label,
            display_device,
            display_target,
            "",
            "",
            "INCOMPATIBLE FIRMWARE",
            ("Connected device identities do not match the OTA pre-device/post-build target.",),
        )
    if not live_devices or not target_devices:
        return _assessment(
            FirmwareRelationship.UNCONFIRMED,
            current_label,
            candidate_label,
            display_device,
            display_target,
            "",
            "",
            "UPGRADE STATUS UNCONFIRMED",
            ("Both live device identity and OTA target-device metadata are required.",),
        )

    precondition_error = _ota_precondition_error(
        metadata,
        current_fingerprint=current_fingerprint,
        current_incremental=current_incremental,
    )
    if precondition_error:
        relationship = (
            FirmwareRelationship.UNCONFIRMED
            if "unavailable" in precondition_error
            else FirmwareRelationship.INCOMPATIBLE
        )
        return _assessment(
            relationship,
            current_label,
            candidate_label,
            display_device,
            display_target,
            "",
            "",
            "UPGRADE STATUS UNCONFIRMED"
            if relationship is FirmwareRelationship.UNCONFIRMED
            else "INCOMPATIBLE UPDATE PATH",
            (precondition_error,),
        )

    try:
        current_sdk = int(current_sdk_level) if current_sdk_level else None
    except ValueError:
        current_sdk = None
    if (
        metadata.post_sdk_level is not None
        and current_sdk is not None
        and metadata.post_sdk_level < current_sdk
    ):
        return _assessment(
            FirmwareRelationship.DOWNGRADE,
            current_label,
            candidate_label,
            display_device,
            display_target,
            "",
            "",
            f"DOWNGRADE CANDIDATE • {current_label} → {candidate_label}",
            (f"OTA post SDK {metadata.post_sdk_level} is below live SDK {current_sdk}.",),
        )

    if metadata.post_timestamp is None or current_build_timestamp is None:
        return _assessment(
            FirmwareRelationship.UNCONFIRMED,
            current_label,
            candidate_label,
            display_device,
            display_target,
            "",
            "",
            "UPGRADE STATUS UNCONFIRMED",
            (
                "Device target and OTA update path matched, but comparable build timestamps "
                "were not available.",
            ),
        )

    relationship = (
        FirmwareRelationship.UPGRADE
        if metadata.post_timestamp > current_build_timestamp
        else FirmwareRelationship.DOWNGRADE
        if metadata.post_timestamp < current_build_timestamp
        else FirmwareRelationship.SAME
    )
    if (
        relationship is FirmwareRelationship.SAME
        and candidate_label
        and candidate_label not in {current_incremental.strip(), current_fingerprint.strip()}
    ):
        return _assessment(
            FirmwareRelationship.UNCONFIRMED,
            current_label,
            candidate_label,
            display_device,
            display_target,
            "",
            "",
            "UPGRADE STATUS UNCONFIRMED",
            ("Build timestamps match but the candidate build identity is different.",),
        )
    label = {
        FirmwareRelationship.UPGRADE: "UPGRADE CANDIDATE",
        FirmwareRelationship.DOWNGRADE: "DOWNGRADE CANDIDATE",
        FirmwareRelationship.SAME: "SAME FIRMWARE TIMESTAMP",
    }[relationship]
    reasons = [
        f"OTA target matched the connected device: {display_target}.",
        "Any OTA pre-build requirements matched the live build evidence.",
        "Version order was derived from Android OTA post-timestamp and the live build timestamp.",
    ]
    if metadata.post_sdk_level is not None and current_sdk is not None:
        reasons.append(
            f"OTA post SDK {metadata.post_sdk_level} was checked against live SDK {current_sdk}."
        )
    return _assessment(
        relationship,
        current_label,
        candidate_label,
        display_device,
        display_target,
        "",
        "",
        f"{label} • {current_label} → {candidate_label}",
        tuple(reasons),
    )


def _ota_precondition_error(
    metadata: AndroidOtaMetadata,
    *,
    current_fingerprint: str,
    current_incremental: str,
) -> str:
    if metadata.pre_builds:
        if not current_fingerprint.strip():
            return "Live build fingerprint is unavailable for the OTA pre-build check."
        if current_fingerprint.strip() not in metadata.pre_builds:
            return "Live build fingerprint does not satisfy the OTA pre-build requirement."
    if metadata.pre_build_incrementals:
        if not current_incremental.strip():
            return "Live incremental build is unavailable for the OTA update-path check."
        if current_incremental.strip() not in metadata.pre_build_incrementals:
            return "Live incremental build does not satisfy the OTA update-path requirement."
    return ""


def _parse_xiaomi_build(value: str) -> _XiaomiBuild | None:
    raw = str(value).strip().upper()
    matched = _XIAOMI_BUILD.fullmatch(raw)
    if matched is None:
        return None
    try:
        version = tuple(int(item) for item in matched.group("version").split("."))
    except ValueError:
        return None
    branch = matched.group("branch").upper()
    return _XiaomiBuild(raw, version, branch, xiaomi_build_region(raw))


def _assessment(
    relationship: FirmwareRelationship,
    current_build: str,
    candidate_build: str,
    device_codename: str,
    candidate_codename: str,
    current_region: str,
    candidate_region: str,
    summary: str,
    reasons: tuple[str, ...],
) -> FirmwareUpgradeAssessment:
    return FirmwareUpgradeAssessment(
        relationship,
        current_build,
        candidate_build,
        device_codename,
        candidate_codename,
        current_region,
        candidate_region,
        summary,
        reasons,
    )
