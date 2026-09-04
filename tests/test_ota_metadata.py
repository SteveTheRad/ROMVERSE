from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from romverse.rom.ota_metadata import (
    MAX_METADATA_BYTES,
    OtaMetadataError,
    parse_android_ota_metadata,
    read_android_ota_metadata,
)

METADATA = b"""\
ota-type=AB
pre-device=komodo|komodo_beta
pre-build=google/komodo/komodo:16/BP2A.260801.001/123:user/release-keys
pre-build-incremental=123
post-build=google/komodo/komodo:16/BP2A.260901.001/456:user/release-keys
post-build-incremental=456
post-sdk-level=36
post-security-patch-level=2026-09-01
post-timestamp=1788220800
"""


def test_parses_standard_android_ota_metadata_and_fingerprint_target() -> None:
    metadata = parse_android_ota_metadata(METADATA)

    assert metadata.pre_devices == ("komodo", "komodo_beta")
    assert metadata.target_devices == ("komodo", "komodo_beta")
    assert metadata.pre_build_incrementals == ("123",)
    assert metadata.post_build_incremental == "456"
    assert metadata.post_sdk_level == 36
    assert metadata.post_timestamp == 1788220800
    assert len(metadata.metadata_digest) == 64


def test_reads_only_the_standard_metadata_entry_from_zip(tmp_path: Path) -> None:
    package = tmp_path / "ota.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("payload.bin", b"not inspected")
        archive.writestr("META-INF/com/android/metadata", METADATA)

    metadata = read_android_ota_metadata(package)

    assert metadata is not None
    assert metadata.ota_type == "AB"


@pytest.mark.parametrize(
    "payload",
    (
        b"pre-device=komodo\npre-device=other\n",
        b"pre-device=komodo\x00\n",
        b"post-sdk-level=not-a-number\n",
        b"post-security-patch-level=September\n",
        b"post-security-patch-level=2026-13-40\n",
        (b"pre-device=komodo\npost-build=google/husky/husky:16/BP2A/456:user/release-keys\n"),
        b"missing-separator\n",
        b"x" * (MAX_METADATA_BYTES + 1),
    ),
)
def test_rejects_ambiguous_or_malformed_metadata(payload: bytes) -> None:
    with pytest.raises(OtaMetadataError):
        parse_android_ota_metadata(payload)


def test_non_zip_or_zip_without_metadata_is_not_claimed_as_an_ota(tmp_path: Path) -> None:
    raw = tmp_path / "firmware.bin"
    raw.write_bytes(b"opaque")
    empty_zip = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty_zip, "w") as archive:
        archive.writestr("payload.bin", b"opaque")

    assert read_android_ota_metadata(raw) is None
    assert read_android_ota_metadata(empty_zip) is None


def test_malformed_zip_is_rejected_instead_of_becoming_filename_evidence(tmp_path: Path) -> None:
    broken = tmp_path / "device-ota_full-OS9.9.9.9.TEST.zip"
    broken.write_bytes(b"PK\x03\x04truncated")

    with pytest.raises(OtaMetadataError, match="ZIP container is malformed"):
        read_android_ota_metadata(broken)
