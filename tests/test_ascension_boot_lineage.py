from __future__ import annotations

import struct
from pathlib import Path

import pytest

from romverse.ascension.models import AscensionMethod
from romverse.ascension.preparation import _boot_layout, _verify_patch_lineage
from romverse.rom.models import ProjectError


def _boot_image(version: int, ramdisk: bytes, kernel: bytes = b"kernel") -> bytes:
    page_size = 4096
    if version in (3, 4):
        header_size = 1580 if version == 3 else 1584
        header = bytearray(header_size)
        header[:8] = b"ANDROID!"
        struct.pack_into("<I", header, 8, len(kernel))
        struct.pack_into("<I", header, 12, len(ramdisk))
        struct.pack_into("<I", header, 16, 0x01020304)
        struct.pack_into("<I", header, 20, header_size)
        struct.pack_into("<I", header, 40, version)
        header[44:57] = b"console=ttyS0"
    else:
        header_size = {0: 1632, 1: 1648, 2: 1660}[version]
        header = bytearray(header_size)
        header[:8] = b"ANDROID!"
        struct.pack_into("<I", header, 8, len(kernel))
        struct.pack_into("<I", header, 16, len(ramdisk))
        struct.pack_into("<I", header, 36, page_size)
        struct.pack_into("<I", header, 40, version)
        struct.pack_into("<I", header, 44, 0x01020304)
        header[64:77] = b"console=ttyS0"
        if version >= 1:
            struct.pack_into("<I", header, 1644, header_size)
    image = bytes(header).ljust(page_size, b"\0") + kernel
    image = image.ljust((len(image) + page_size - 1) // page_size * page_size, b"\0")
    return image + ramdisk


@pytest.mark.parametrize("version", (0, 1, 2, 3, 4))
def test_aosp_boot_versions_preserve_header_and_kernel_lineage(
    tmp_path: Path,
    version: int,
) -> None:
    source = tmp_path / f"source-v{version}.img"
    patched = tmp_path / f"patched-v{version}.img"
    source.write_bytes(_boot_image(version, b"pristine ramdisk"))
    patched.write_bytes(_boot_image(version, b"patched ramdisk"))

    lineage = _verify_patch_lineage(source, patched, AscensionMethod.KERNELSU_LKM)
    layout = _boot_layout(patched)

    assert layout.header_version == version
    assert lineage.scope == "normalized-header-and-kernel"
    assert lineage.confidence == "high"
    assert lineage.source_kernel_sha256 == lineage.patched_kernel_sha256


def test_header_lineage_rejects_a_different_source_identity(tmp_path: Path) -> None:
    source = tmp_path / "source.img"
    patched = tmp_path / "patched.img"
    source.write_bytes(_boot_image(4, b"pristine ramdisk"))
    different = bytearray(_boot_image(4, b"patched ramdisk"))
    different[44] ^= 1
    patched.write_bytes(different)

    with pytest.raises(ProjectError, match="immutable Android header lineage"):
        _verify_patch_lineage(source, patched, AscensionMethod.MAGISK)


def test_invalid_declared_header_size_is_rejected(tmp_path: Path) -> None:
    image = bytearray(_boot_image(4, b"ramdisk"))
    struct.pack_into("<I", image, 20, 64)
    path = tmp_path / "invalid-header.img"
    path.write_bytes(image)

    with pytest.raises(ProjectError, match="header size"):
        _boot_layout(path)
