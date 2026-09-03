from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

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
) -> FirmwareUpgradeAssessment:
    """Classify a conservative firmware relationship without granting install authority."""

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
