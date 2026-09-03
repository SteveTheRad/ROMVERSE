from __future__ import annotations

import hashlib
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path


class OtaMetadataError(ValueError):
    """The Android OTA metadata entry was present but unsafe or malformed."""


@dataclass(frozen=True, slots=True)
class AndroidOtaMetadata:
    pre_devices: tuple[str, ...]
    pre_builds: tuple[str, ...]
    pre_build_incrementals: tuple[str, ...]
    post_builds: tuple[str, ...]
    post_build_incremental: str
    post_sdk_level: int | None
    post_security_patch_level: str
    post_timestamp: int | None
    ota_type: str
    metadata_digest: str

    @property
    def target_devices(self) -> tuple[str, ...]:
        observed = [*self.pre_devices]
        observed.extend(
            device
            for device in (_fingerprint_device(value) for value in self.post_builds)
            if device
        )
        return tuple(dict.fromkeys(item.casefold() for item in observed if item.strip()))


METADATA_PATH = "META-INF/com/android/metadata"
MAX_METADATA_BYTES = 128 * 1024
_VALID_KEY = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
_SECURITY_PATCH = re.compile(r"\d{4}-\d{2}-\d{2}")


def read_android_ota_metadata(path: Path) -> AndroidOtaMetadata | None:
    """Read the standard bounded Android OTA metadata entry without extracting the archive."""

    try:
        with zipfile.ZipFile(path) as archive:
            entries = [item for item in archive.infolist() if item.filename == METADATA_PATH]
            if not entries:
                return None
            if len(entries) != 1:
                raise OtaMetadataError("Android OTA metadata entry is duplicated")
            entry = entries[0]
            if entry.is_dir() or entry.flag_bits & 0x1:
                raise OtaMetadataError("Android OTA metadata entry is not a readable file")
            if entry.file_size > MAX_METADATA_BYTES:
                raise OtaMetadataError("Android OTA metadata exceeds the bounded read limit")
            with archive.open(entry, "r") as stream:
                payload = stream.read(MAX_METADATA_BYTES + 1)
    except zipfile.BadZipFile:
        return None
    except (NotImplementedError, OSError, RuntimeError, zipfile.LargeZipFile) as exc:
        raise OtaMetadataError(f"Android OTA metadata could not be read: {exc}") from exc
    if len(payload) > MAX_METADATA_BYTES:
        raise OtaMetadataError("Android OTA metadata exceeds the bounded read limit")
    return parse_android_ota_metadata(payload)


def parse_android_ota_metadata(payload: bytes) -> AndroidOtaMetadata:
    if len(payload) > MAX_METADATA_BYTES:
        raise OtaMetadataError("Android OTA metadata exceeds the bounded read limit")
    if b"\x00" in payload:
        raise OtaMetadataError("Android OTA metadata contains a NUL byte")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OtaMetadataError("Android OTA metadata is not valid UTF-8") from exc

    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise OtaMetadataError("Android OTA metadata contains a malformed line")
        key, value = (item.strip() for item in line.split("=", 1))
        if not _VALID_KEY.fullmatch(key) or key in values:
            raise OtaMetadataError("Android OTA metadata contains an invalid or duplicate key")
        if any(ord(character) < 32 for character in value):
            raise OtaMetadataError("Android OTA metadata contains a control character")
        values[key] = value

    post_sdk = _optional_positive_int(values.get("post-sdk-level", ""), "post-sdk-level")
    post_timestamp = _optional_positive_int(values.get("post-timestamp", ""), "post-timestamp")
    security_patch = values.get("post-security-patch-level", "").strip()
    if security_patch and not _SECURITY_PATCH.fullmatch(security_patch):
        raise OtaMetadataError("Android OTA security patch level is malformed")

    pre_devices = _alternatives(values.get("pre-device", ""))
    post_builds = _alternatives(values.get("post-build", ""))
    post_devices = tuple(
        item for item in (_fingerprint_device(value) for value in post_builds) if item
    )
    if (
        pre_devices
        and post_devices
        and set(map(str.casefold, pre_devices)).isdisjoint(map(str.casefold, post_devices))
    ):
        raise OtaMetadataError("Android OTA pre-device and post-build targets disagree")

    return AndroidOtaMetadata(
        pre_devices=pre_devices,
        pre_builds=_alternatives(values.get("pre-build", "")),
        pre_build_incrementals=_alternatives(values.get("pre-build-incremental", "")),
        post_builds=post_builds,
        post_build_incremental=values.get("post-build-incremental", "").strip(),
        post_sdk_level=post_sdk,
        post_security_patch_level=security_patch,
        post_timestamp=post_timestamp,
        ota_type=values.get("ota-type", "").strip().upper(),
        metadata_digest=hashlib.sha256(payload).hexdigest(),
    )


def _alternatives(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item.strip() for item in value.split("|") if item.strip()))


def _optional_positive_int(value: str, label: str) -> int | None:
    if not value:
        return None
    try:
        parsed = int(value)
    except ValueError as exc:
        raise OtaMetadataError(f"Android OTA {label} is not an integer") from exc
    if parsed <= 0:
        raise OtaMetadataError(f"Android OTA {label} is not positive")
    return parsed


def _fingerprint_device(fingerprint: str) -> str:
    prefix = fingerprint.split(":", 1)[0]
    parts = prefix.split("/")
    return parts[2].strip() if len(parts) >= 3 else ""
