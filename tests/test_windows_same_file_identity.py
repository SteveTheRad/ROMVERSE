from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from romverse.guardian.source_installation import _file_identity
from romverse.rom.candidate_avb import _fingerprint, _hash

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows file identity regression")


@pytest.mark.parametrize("identity", [_fingerprint, _file_identity])
def test_windows_same_file_accepts_descriptor_path_ctime_difference(identity) -> None:
    descriptor = SimpleNamespace(
        st_dev=7,
        st_ino=11,
        st_size=13,
        st_mtime_ns=17,
        st_ctime_ns=19,
    )
    path = SimpleNamespace(
        st_dev=7,
        st_ino=11,
        st_size=13,
        st_mtime_ns=17,
        st_ctime_ns=23,
    )

    assert identity(descriptor) == identity(path)


@pytest.mark.parametrize("identity", [_fingerprint, _file_identity])
def test_windows_path_replacement_changes_identity_with_preserved_metadata(identity) -> None:
    original = SimpleNamespace(
        st_dev=7,
        st_ino=11,
        st_size=13,
        st_mtime_ns=17,
        st_ctime_ns=19,
    )
    replacement = SimpleNamespace(
        st_dev=7,
        st_ino=29,
        st_size=13,
        st_mtime_ns=17,
        st_ctime_ns=19,
    )

    assert identity(original) != identity(replacement)


def test_windows_fresh_hash_exposes_byte_drift_with_restored_mtime(tmp_path) -> None:
    image = tmp_path / "candidate.img"
    image.write_bytes(b"approved-candidate")
    before = image.stat()
    expected = _hash(image)

    image.write_bytes(b"replaced-candidate")
    os.utime(image, ns=(before.st_atime_ns, before.st_mtime_ns))

    observed = _hash(image)
    assert observed[1] == expected[1]
    assert observed[0] != expected[0]
