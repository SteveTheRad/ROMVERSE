from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from romverse.infrastructure import file_identity
from romverse.infrastructure.file_identity import stable_file_identity
from romverse.rom.candidate_avb import _fingerprint as candidate_fingerprint
from romverse.rom.candidate_avb import _hash
from romverse.rom.source_installation import SourceInstallationService


def _details(**changes):
    values = {
        "st_dev": 7,
        "st_ino": 11,
        "st_size": 18,
        "st_mtime_ns": 17,
        "st_ctime_ns": 19,
    }
    values.update(changes)
    return SimpleNamespace(**values)


@pytest.mark.parametrize(
    "identity",
    (stable_file_identity, SourceInstallationService._fingerprint, candidate_fingerprint),
)
def test_windows_descriptor_path_identity_accepts_only_ctime_rounding(
    monkeypatch, identity
) -> None:
    monkeypatch.setattr(file_identity.os, "name", "nt")

    assert identity(_details()) == identity(_details(st_ctime_ns=23))


@pytest.mark.parametrize(
    "change",
    ({"st_dev": 29}, {"st_ino": 29}, {"st_size": 29}, {"st_mtime_ns": 29}),
)
def test_windows_replacement_with_preserved_size_and_mtime_still_changes_identity(
    monkeypatch, change
) -> None:
    monkeypatch.setattr(file_identity.os, "name", "nt")

    assert stable_file_identity(_details()) != stable_file_identity(_details(**change))


def test_posix_identity_retains_ctime_change_detection(monkeypatch) -> None:
    monkeypatch.setattr(file_identity.os, "name", "posix")

    assert stable_file_identity(_details()) != stable_file_identity(_details(st_ctime_ns=23))


def test_fresh_candidate_hash_exposes_same_size_byte_drift_with_restored_mtime(tmp_path) -> None:
    image = tmp_path / "candidate.img"
    image.write_bytes(b"approved-candidate")
    before = image.stat()
    expected = _hash(image)

    image.write_bytes(b"replaced-candidate")
    os.utime(image, ns=(before.st_atime_ns, before.st_mtime_ns))

    observed = _hash(image)
    assert observed[1] == expected[1]
    assert observed[0] != expected[0]
