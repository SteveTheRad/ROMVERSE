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
        return FirmwareSourceIdentity(
            "Xiaomi",
            values["codename"].casefold(),
            values["build"].upper(),
            values["android"],
            channel.title(),
            "Xiaomi full OTA archive",
            "high",
            (
                "Xiaomi *-ota_full-* naming structure matched",
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
