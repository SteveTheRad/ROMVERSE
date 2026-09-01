from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest

from romverse.device_packs.models import (
    AvbExecutionPolicy,
    AvbPolicyAuthority,
    AvbPolicyMode,
)
from romverse.rom.avb_evidence import AvbEvidenceService, AvbImageEvidence
from romverse.rom.build_execution import LocalDeviceBuildExecutor
from romverse.rom.models import ProjectError

from .test_build_contracts import _fixture

SIGNED_INFO = """Minimum libavb version:   1.0
Algorithm:                SHA256_RSA4096
Public key (sha1):        8256e695b81d1eb6dd0b1ce5d08b9c73cbb5e5b6
Rollback Index:           1782864000
Flags:                    0
Rollback Index Location:  2
Descriptors:
    Hashtree descriptor:
      Partition Name:        product
    Hashtree descriptor:
      Partition Name:        system
"""

UNSIGNED_INFO = """Minimum libavb version:   1.0
Algorithm:                NONE
Rollback Index:           0
Flags:                    0
Rollback Index Location:  0
Descriptors:
    Hashtree descriptor:
      Partition Name:        product
"""


def _image(role: str, signed: bool = True, key: str = "8256e695b81d1eb6dd0b1ce5d08b9c73cbb5e5b6"):
    return AvbImageEvidence(
        role,
        f"working/{role}.img",
        "a" * 64,
        "SHA256_RSA4096" if signed else "NONE",
        key if signed else "",
        0,
        0,
        0,
        ("product",),
    )


def test_avb_info_parser_records_identity_and_descriptor_chain():
    evidence = AvbEvidenceService.parse_info(
        "source-vbmeta_system",
        "source.img",
        "a" * 64,
        SIGNED_INFO,
    )

    assert evidence.algorithm == "SHA256_RSA4096"
    assert evidence.public_key_sha1 == "8256e695b81d1eb6dd0b1ce5d08b9c73cbb5e5b6"
    assert evidence.rollback_index == 1782864000
    assert evidence.rollback_index_location == 2
    assert evidence.descriptor_partitions == ("product", "system")


def test_avb_topology_truthfully_reports_unsigned_candidate():
    images = (
        _image("source-vbmeta"),
        _image("source-vbmeta_system"),
        _image("candidate-product", False),
        _image("candidate-vbmeta_system", False),
    )

    receipt = AvbEvidenceService.classify(
        "project",
        "pack",
        "contract",
        "b" * 64,
        "c" * 64,
        images,
    )

    assert not receipt.candidate_signed
    assert not receipt.source_identity_matches
    assert not receipt.signing_ready
    assert "unsigned" in receipt.diagnosis
    assert not receipt.phone_changed


def test_avb_topology_accepts_only_exact_matching_source_identity():
    exact = (
        _image("source-vbmeta"),
        _image("source-vbmeta_system"),
        _image("candidate-product"),
        _image("candidate-vbmeta_system"),
    )
    mismatch = (*exact[:3], _image("candidate-vbmeta_system", key="1" * 40))

    ready = AvbEvidenceService.classify("p", "pack", "contract", "a" * 64, "b" * 64, exact)
    wrong = AvbEvidenceService.classify("p", "pack", "contract", "a" * 64, "b" * 64, mismatch)

    assert ready.signing_ready
    assert not wrong.signing_ready
    assert "re-chaining policy" in wrong.diagnosis


def test_avb_parser_rejects_invalid_public_key_fingerprint():
    with pytest.raises(ProjectError, match="fingerprint"):
        AvbEvidenceService.parse_info(
            "source-vbmeta",
            "source.img",
            "a" * 64,
            SIGNED_INFO.replace(
                "8256e695b81d1eb6dd0b1ce5d08b9c73cbb5e5b6",
                "not-a-key",
            ),
        )


def test_avb_parser_supports_unsigned_candidate_without_inventing_a_key():
    evidence = AvbEvidenceService.parse_info(
        "candidate-product",
        "candidate.img",
        "a" * 64,
        UNSIGNED_INFO,
    )
    assert evidence.algorithm == "NONE"
    assert evidence.public_key_sha1 == ""


def test_historical_unsigned_child_policy_is_recognized_but_never_authorized():
    source_top = _image("source-vbmeta")
    source_top = replace(
        source_top,
        descriptor_partitions=("boot", "recovery", "vbmeta_system"),
    )
    source_child = _image("source-vbmeta_system")
    source_child = replace(
        source_child,
        descriptor_partitions=("product", "system", "system_ext"),
    )
    candidate_product = _image("candidate-product", False)
    candidate_child = _image("candidate-vbmeta_system", False)
    candidate_child = replace(
        candidate_child,
        descriptor_partitions=("product", "system", "system_ext"),
    )
    policy = AvbExecutionPolicy(
        AvbPolicyMode.UNLOCKED_UNSIGNED_CHILD,
        AvbPolicyAuthority.REFERENCE_ONLY,
        "OLDER.BUILD",
        "preserve_exact_source",
        "vbmeta_system",
        "NONE",
        0,
        0,
        0,
        True,
        True,
        True,
        "a",
        "b",
    )

    receipt = AvbEvidenceService.classify(
        "p",
        "pack",
        "contract",
        "a" * 64,
        "b" * 64,
        (source_top, source_child, candidate_product, candidate_child),
        policy,
    )

    assert receipt.policy_compatible
    assert not receipt.policy_authorized
    assert not receipt.signing_ready
    assert "reference-only" in receipt.diagnosis


def test_avb_receipt_loader_rejects_hostile_files_and_missing_images(
    tmp_path,
    monkeypatch,
):
    store, project, registry, tools, _metadata, _partitions = _fixture(tmp_path)
    build_digest = "c" * 64
    monkeypatch.setattr(
        LocalDeviceBuildExecutor,
        "load_receipt",
        lambda *_args: SimpleNamespace(receipt_digest=build_digest),
    )
    pack = registry.packs[0]
    assert pack.build_contract is not None
    images = []
    for role in (
        "source-vbmeta",
        "source-vbmeta_system",
        "candidate-product",
        "candidate-vbmeta_system",
    ):
        image = store.working_root / project.project_id / "avb-fixtures" / f"{role}.img"
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(role.encode())
        images.append(
            AvbImageEvidence(
                role,
                image.relative_to(store.workspace).as_posix(),
                hashlib.sha256(image.read_bytes()).hexdigest(),
                "SHA256_RSA4096",
                "a" * 40,
                0,
                0,
                0,
                ("product",),
            )
        )
    receipt = AvbEvidenceService.classify(
        project.project_id,
        pack.pack_id,
        pack.build_contract.contract_id,
        project.original.sha256,
        build_digest,
        tuple(images),
    )
    service = AvbEvidenceService(store, registry, tools, None, tmp_path / "avbtool", None)
    path = store.projects_root / project.project_id / service.RECEIPT_NAME
    payload = {"format": "romverse.avb-topology", **asdict(receipt)}
    if receipt.schema_version == 2:
        for item in payload["images"]:
            item.pop("size_bytes")
            item.pop("modified_ns")
    path.write_text(json.dumps(payload), encoding="utf-8")
    original = path.read_bytes()
    assert service.load(project.project_id) == receipt

    hostile = dict(payload)
    hostile["unexpected"] = True
    path.write_text(json.dumps(hostile), encoding="utf-8")
    assert service.load(project.project_id) is None

    path.write_bytes(b"{" + b" " * service.MAX_RECEIPT_BYTES + b"}")
    assert service.load(project.project_id) is None

    outside = tmp_path / "outside-avb.json"
    outside.write_bytes(original)
    path.unlink()
    path.symlink_to(outside)
    assert service.load(project.project_id) is None

    path.unlink()
    path.write_bytes(original)
    (store.workspace / images[-1].path).unlink()
    assert service.load(project.project_id) is None
