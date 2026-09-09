from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, fields


class CanonicalFirmwareIdentityError(ValueError):
    """Firmware identity is incomplete, malformed, or would require inference."""


@dataclass(frozen=True, slots=True)
class CanonicalFirmwareIdentity:
    """One immutable firmware artifact beneath an exact canonical device identity."""

    schema_version: int
    firmware_id: str
    canonical_device_id: str
    model_variant: str
    region: str
    build_id: str
    firmware_version: str
    android_version: str
    security_patch: str
    artifact_sha256: str
    partition_layout_digest: str
    evidence_claim_ids: tuple[str, ...]
    compatibility_status: str = "UNCONFIRMED"
    execution_authority: str = "none"
    phone_action_allowed: bool = False
    guardian_approval: bool = False
    bootloader_relock_allowed: bool = False

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise CanonicalFirmwareIdentityError("Canonical firmware schema is unsupported")
        if (
            self.compatibility_status != "UNCONFIRMED"
            or self.execution_authority != "none"
            or self.phone_action_allowed
            or self.guardian_approval
            or self.bootloader_relock_allowed
        ):
            raise CanonicalFirmwareIdentityError(
                "Canonical firmware cannot promote compatibility or execution authority"
            )

    def exactly_matches(self, other: CanonicalFirmwareIdentity) -> bool:
        return self.firmware_id == other.firmware_id


_CANONICAL_FIRMWARE_FIELDS = {field.name for field in fields(CanonicalFirmwareIdentity)}
_PRIVATE_FIRMWARE_TEXT = re.compile(
    r"(?i)(?:\b(?:imei|serial|account|username|password|secret|token)\b|"
    r"(?<!\d)\d{15}(?!\d)|/home/|/users/|[a-z]:\\users\\|"
    r"-----begin [^-]+private key-----)"
)


def create_canonical_firmware_identity(
    *,
    canonical_device_id: str,
    model_variant: str,
    build_id: str,
    artifact_sha256: str,
    evidence_claim_ids: Sequence[str],
    region: str = "",
    firmware_version: str = "",
    android_version: str = "",
    security_patch: str = "",
    partition_layout_digest: str = "",
) -> CanonicalFirmwareIdentity:
    """Create a deterministic artifact identity without inferring compatibility."""

    device_id = _firmware_digest(canonical_device_id, "canonical device")
    model = _firmware_text(model_variant, 120, required=True)
    build = _firmware_text(build_id, 160, required=True)
    artifact = _firmware_digest(artifact_sha256, "firmware artifact")
    claims = _firmware_digests(evidence_claim_ids, required=True)
    region_value = _firmware_text(region, 80)
    version = _firmware_text(firmware_version, 120)
    android = _firmware_text(android_version, 40)
    patch = _firmware_text(security_patch, 40)
    layout = (
        _firmware_digest(partition_layout_digest, "partition layout")
        if partition_layout_digest
        else ""
    )
    basis = {
        "schema": "romverse.canonical-firmware-identity.v1",
        "canonical_device_id": device_id,
        "model_variant": model.casefold(),
        "region": region_value.casefold(),
        "build_id": build.casefold(),
        "firmware_version": version.casefold(),
        "android_version": android.casefold(),
        "security_patch": patch.casefold(),
        "artifact_sha256": artifact,
        "partition_layout_digest": layout,
    }
    firmware_id = hashlib.sha256(
        json.dumps(basis, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return CanonicalFirmwareIdentity(
        1,
        firmware_id,
        device_id,
        model,
        region_value,
        build,
        version,
        android,
        patch,
        artifact,
        layout,
        claims,
    )


def canonical_firmware_identity_mapping(identity: CanonicalFirmwareIdentity) -> dict[str, object]:
    return json.loads(json.dumps(asdict(identity)))


def parse_canonical_firmware_identity(raw: Mapping[str, object]) -> CanonicalFirmwareIdentity:
    if (
        set(raw) != _CANONICAL_FIRMWARE_FIELDS
        or type(raw.get("schema_version")) is not int
        or raw.get("schema_version") != 1
    ):
        raise CanonicalFirmwareIdentityError("Canonical firmware schema is unsupported")
    required_authority = {
        "compatibility_status": "UNCONFIRMED",
        "execution_authority": "none",
        "phone_action_allowed": False,
        "guardian_approval": False,
        "bootloader_relock_allowed": False,
    }
    if any(
        raw.get(name) != value or type(raw.get(name)) is not type(value)
        for name, value in required_authority.items()
    ):
        raise CanonicalFirmwareIdentityError(
            "Canonical firmware cannot promote compatibility or execution authority"
        )
    claim_ids = raw.get("evidence_claim_ids")
    if not isinstance(claim_ids, list) or any(not isinstance(item, str) for item in claim_ids):
        raise CanonicalFirmwareIdentityError("Firmware evidence claims are malformed")
    created = create_canonical_firmware_identity(
        canonical_device_id=_firmware_mapping_text(raw, "canonical_device_id"),
        model_variant=_firmware_mapping_text(raw, "model_variant"),
        region=_firmware_mapping_text(raw, "region"),
        build_id=_firmware_mapping_text(raw, "build_id"),
        firmware_version=_firmware_mapping_text(raw, "firmware_version"),
        android_version=_firmware_mapping_text(raw, "android_version"),
        security_patch=_firmware_mapping_text(raw, "security_patch"),
        artifact_sha256=_firmware_mapping_text(raw, "artifact_sha256"),
        partition_layout_digest=_firmware_mapping_text(raw, "partition_layout_digest"),
        evidence_claim_ids=tuple(claim_ids),
    )
    if raw.get("firmware_id") != created.firmware_id:
        raise CanonicalFirmwareIdentityError("Canonical firmware digest is invalid")
    expected = json.loads(json.dumps(canonical_firmware_identity_mapping(created)))
    if dict(raw) != expected:
        raise CanonicalFirmwareIdentityError("Canonical firmware identity is not deterministic")
    return created


def _firmware_text(value: object, limit: int, *, required: bool = False) -> str:
    if not isinstance(value, str) or "\0" in value:
        raise CanonicalFirmwareIdentityError("Firmware identity text is malformed")
    cleaned = " ".join(value.split())
    if len(cleaned) > limit or (required and not cleaned):
        raise CanonicalFirmwareIdentityError("Firmware identity remains UNCONFIRMED")
    if _PRIVATE_FIRMWARE_TEXT.search(cleaned):
        raise CanonicalFirmwareIdentityError("Firmware identity contains private data")
    return cleaned


def _firmware_digest(value: object, label: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise CanonicalFirmwareIdentityError(f"Exact {label} digest is required")
    return value


def _firmware_digests(values: Sequence[str], *, required: bool) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or len(values) > 64:
        raise CanonicalFirmwareIdentityError("Firmware evidence claims are malformed")
    result = tuple(sorted(set(values)))
    if (required and not result) or any(
        not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None
        for value in result
    ):
        raise CanonicalFirmwareIdentityError("Exact firmware evidence digests are required")
    return result


def _firmware_mapping_text(raw: Mapping[str, object], name: str) -> str:
    value = raw.get(name)
    if not isinstance(value, str):
        raise CanonicalFirmwareIdentityError("Firmware identity text is malformed")
    return value


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
