from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FirmwareSourceIdentity:
    manufacturer: str
    codename: str
    build_id: str
    android_version: str
    region: str
    package_type: str
    confidence: str
    evidence: tuple[str, ...]

    @property
    def summary(self) -> str:
        details = [self.package_type]
        if self.codename:
            details.append(self.codename)
        if self.build_id:
            details.append(self.build_id)
        if self.android_version:
            details.append(f"Android {self.android_version}")
        if self.region:
            details.append(self.region)
        return "  •  ".join(details)


_XIAOMI_FASTBOOT = re.compile(
    r"^(?P<codename>[a-z0-9_-]+)_images_"
    r"(?P<build>OS[0-9][A-Z0-9.]*)_"
    r"(?P<timestamp>[0-9]{8}\.[0-9]{4}\.[0-9]{2})_"
    r"(?P<android>[0-9]+(?:\.[0-9]+)?)_"
    r"(?P<region>[a-z]{2,12})_",
    re.IGNORECASE,
)
_XIAOMI_OTA = re.compile(
    r"^(?P<codename>[a-z0-9_-]+)-ota_full-"
    r"(?P<build>OS[0-9][A-Z0-9.]*)-"
    r"(?P<channel>[a-z]+)-"
    r"(?P<android>[0-9]+(?:\.[0-9]+)?)-",
    re.IGNORECASE,
)
_REGIONS = {
    "cn": "China",
    "global": "Global",
    "eea": "EEA",
    "in": "India",
    "id": "Indonesia",
    "ru": "Russia",
    "tr": "Türkiye",
    "tw": "Taiwan",
}
_XIAOMI_BUILD_REGIONS = {
    "CNXM": "China",
    "MIXM": "Global",
    "EUXM": "EEA",
    "INXM": "India",
    "IDXM": "Indonesia",
    "RUXM": "Russia",
    "TRXM": "Türkiye",
    "TWXM": "Taiwan",
    "JPXM": "Japan",
}


def xiaomi_build_region(build_id: str) -> str:
    """Derive Xiaomi's distribution region only from a recognized build suffix."""

    normalized = str(build_id).strip().upper()
    return next(
        (region for suffix, region in _XIAOMI_BUILD_REGIONS.items() if normalized.endswith(suffix)),
        "",
    )


def identify_firmware_source(filename: str) -> FirmwareSourceIdentity:
    """Identify a firmware base from bounded vendor filename evidence.

    Filename recognition is descriptive only. It never grants build or flash authority;
    an exact immutable source digest still has to match a published Device Pack contract.
    """

    name = str(filename).strip()
    fastboot = _XIAOMI_FASTBOOT.match(name)
    if fastboot:
        values = fastboot.groupdict()
        region_code = values["region"].casefold()
        return FirmwareSourceIdentity(
            "Xiaomi",
            values["codename"].casefold(),
            values["build"].upper(),
            values["android"],
            _REGIONS.get(region_code, region_code.upper()),
            "Xiaomi fastboot image archive",
            "high",
            (
                "Xiaomi *_images_* naming structure matched",
                f"Published archive timestamp token {values['timestamp']}",
                "Build authority still requires an exact SHA-256 Device Pack contract",
            ),
        )
    ota = _XIAOMI_OTA.match(name)
    if ota:
        values = ota.groupdict()
        channel = values["channel"].casefold()
        build = values["build"].upper()
        build_region = xiaomi_build_region(build)
        return FirmwareSourceIdentity(
            "Xiaomi",
            values["codename"].casefold(),
            build,
            values["android"],
            build_region or channel.title(),
            "Xiaomi full OTA archive",
            "high",
            (
                "Xiaomi *-ota_full-* naming structure matched",
                *(
                    (f"Xiaomi build suffix identifies the {build_region} distribution region",)
                    if build_region
                    else ()
                ),
                "Build authority still requires an exact SHA-256 Device Pack contract",
            ),
        )
    suffix = name.casefold().rsplit(".", 1)[-1] if "." in name else "unknown"
    return FirmwareSourceIdentity(
        "",
        "",
        "",
        "",
        "",
        f"Unclassified {suffix.upper()} firmware container",
        "unknown",
        ("No supported vendor filename signature matched",),
    )
