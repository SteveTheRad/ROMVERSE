from __future__ import annotations

import hashlib
import json
import stat
from datetime import UTC, datetime

import pytest

from romverse.infrastructure.tools import ToolStatus
from romverse.intelligence.action_evidence import (
    ToolchainVerificationStore,
    TypedLocalActionEvidence,
    WorkspaceLocalActionEvidenceVerifier,
)
from romverse.intelligence.online_remediation import (
    ErrorFingerprint,
    OnlineRemediationService,
)
from romverse.repair.host import (
    AdbHostRepairMode,
    AdbHostRepairReceiptStore,
    AdbHostRepairStatus,
    create_adb_host_repair_plan,
)


def test_successful_host_receipt_is_revalidated_and_tampering_revokes_it(tmp_path) -> None:
    adb = tmp_path / "adb"
    adb.write_bytes(b"verified adb")
    adb.chmod(0o755)
    plan = create_adb_host_repair_plan(adb, AdbHostRepairMode.START, "daemon unavailable")
    output_digest = hashlib.sha256(b"bounded output").hexdigest()
    steps = (
        {
            "step": "start-server",
            "returncode": 0,
            "timed_out": False,
            "output_digest": output_digest,
        },
        {
            "step": "verify-devices",
            "returncode": 0,
            "timed_out": False,
            "output_digest": output_digest,
        },
    )
    digest, reference = AdbHostRepairReceiptStore(tmp_path).write(
        plan,
        AdbHostRepairStatus.SUCCEEDED,
        steps,
    )
    evidence = TypedLocalActionEvidence(
        "refresh-adb-evidence",
        digest,
        reference,
        "romverse.adb-host-repair",
    )
    verifier = WorkspaceLocalActionEvidenceVerifier(tmp_path)

    assert verifier.verify(evidence)

    path = tmp_path / reference
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["status"] = "failed"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert not verifier.verify(evidence)


def test_toolchain_receipt_rehashes_exact_tools_and_is_private(tmp_path) -> None:
    adb = tmp_path / "adb"
    fastboot = tmp_path / "fastboot"
    adb.write_bytes(b"adb binary")
    fastboot.write_bytes(b"fastboot binary")
    adb.chmod(0o755)
    fastboot.chmod(0o755)
    receipt = ToolchainVerificationStore(tmp_path).record(
        (
            ToolStatus("ADB", True, str(adb), "1.0.41", "Ready"),
            ToolStatus("Fastboot", True, str(fastboot), "35.0.2", "Ready"),
        ),
        ("ADB", "Fastboot"),
    )
    evidence = TypedLocalActionEvidence(
        "verify-platform-tools",
        receipt.receipt_digest,
        receipt.evidence_ref,
        ToolchainVerificationStore.FORMAT,
    )
    verifier = WorkspaceLocalActionEvidenceVerifier(tmp_path)

    assert verifier.verify(evidence)
    assert stat.S_IMODE((tmp_path / receipt.evidence_ref).stat().st_mode) == 0o600

    adb.write_bytes(b"changed after verification")
    assert not verifier.verify(evidence)


def test_ota_blueprint_evidence_is_project_and_artifact_bound(tmp_path) -> None:
    project_id = "ota-project-1234"
    project_root = tmp_path / "projects" / project_id
    project_root.mkdir(parents=True)
    payload_path = tmp_path / "working_roms" / project_id / "tree" / "payload.bin"
    payload_path.parent.mkdir(parents=True)
    payload_path.write_bytes(b"CrAU\x00bounded payload fixture")
    details = payload_path.stat()
    payload_sha = hashlib.sha256(payload_path.read_bytes()).hexdigest()
    unsigned = {
        "schema_version": 1,
        "project_id": project_id,
        "created_at": datetime.now(UTC).isoformat(),
        "manufacturer": "Example",
        "codename": "example",
        "build_id": "BUILD.1",
        "android_version": "15",
        "region": "global",
        "source_archive_sha256": "a" * 64,
        "payload_path": payload_path.relative_to(tmp_path).as_posix(),
        "payload_size_bytes": details.st_size,
        "payload_modified_ns": details.st_mtime_ns,
        "payload_sha256": payload_sha,
        "partitions": [{"name": "system", "estimated_bytes": 1024}],
        "plan_mode": "verified-ota-payload-baseline",
        "plan_digest": "b" * 64,
        "authority": "project-local-build-evidence-only",
        "phone_changed": False,
    }
    digest = _digest(unsigned)
    reference = f"projects/{project_id}/ota-source-blueprint.romverse"
    (tmp_path / reference).write_text(
        json.dumps(
            {
                "format": "romverse.ota-source-blueprint",
                **unsigned,
                "blueprint_digest": digest,
            }
        ),
        encoding="utf-8",
    )
    evidence = TypedLocalActionEvidence(
        "inspect-payload-source",
        digest,
        reference,
        "romverse.ota-source-blueprint",
    )
    verifier = WorkspaceLocalActionEvidenceVerifier(tmp_path)

    assert verifier.verify(evidence)

    payload_path.write_bytes(payload_path.read_bytes() + b"changed")
    assert not verifier.verify(evidence)


def test_avb_evidence_is_project_bound_and_requires_all_contained_images(tmp_path) -> None:
    project_id = "avb-project-1234"
    project_root = tmp_path / "projects" / project_id
    project_root.mkdir(parents=True)
    image_records = []
    for role in (
        "source-vbmeta",
        "source-vbmeta_system",
        "candidate-product",
        "candidate-vbmeta_system",
    ):
        image = tmp_path / "working_roms" / project_id / "images" / f"{role}.img"
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(f"{role} fixture".encode())
        details = image.stat()
        image_records.append(
            {
                "role": role,
                "path": image.relative_to(tmp_path).as_posix(),
                "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                "algorithm": "SHA256_RSA4096",
                "public_key_sha1": "a" * 40,
                "rollback_index": 0,
                "rollback_index_location": 0,
                "flags": 0,
                "descriptor_partitions": [],
                "size_bytes": details.st_size,
                "modified_ns": details.st_mtime_ns,
            }
        )
    unsigned = {
        "schema_version": 3,
        "project_id": project_id,
        "created_at": datetime.now(UTC).isoformat(),
        "pack_id": "example-pack",
        "contract_id": "example-contract",
        "source_original_sha256": "a" * 64,
        "local_build_receipt_digest": "b" * 64,
        "images": image_records,
        "source_algorithm": "SHA256_RSA4096",
        "source_public_key_sha1": "a" * 40,
        "candidate_signed": False,
        "source_identity_matches": False,
        "signing_ready": False,
        "policy_mode": "",
        "policy_authority": "",
        "policy_compatible": False,
        "policy_authorized": False,
        "diagnosis": "Exact topology inspected; no flash authority.",
        "phone_changed": False,
    }
    digest = _digest(unsigned)
    reference = f"projects/{project_id}/avb-topology.romverse"
    (tmp_path / reference).write_text(
        json.dumps({"format": "romverse.avb-topology", **unsigned}),
        encoding="utf-8",
    )
    evidence = TypedLocalActionEvidence(
        "inspect-avb-topology",
        digest,
        reference,
        "romverse.avb-topology",
    )
    verifier = WorkspaceLocalActionEvidenceVerifier(tmp_path)

    assert verifier.verify(evidence)

    receipt_path = tmp_path / reference
    original = receipt_path.read_bytes()
    legacy = json.loads(original)
    legacy["schema_version"] = 2
    for item in legacy["images"]:
        item.pop("size_bytes")
        item.pop("modified_ns")
    legacy_unsigned = dict(legacy)
    legacy_unsigned.pop("format")
    legacy_digest = _digest(legacy_unsigned)
    receipt_path.write_text(json.dumps(legacy), encoding="utf-8")
    assert not verifier.verify(
        TypedLocalActionEvidence(
            "inspect-avb-topology",
            legacy_digest,
            reference,
            "romverse.avb-topology",
        )
    )

    receipt_path.write_bytes(original)
    (tmp_path / image_records[-1]["path"]).unlink()
    assert not verifier.verify(evidence)


def test_online_outcome_rejects_digest_without_real_typed_evidence(tmp_path) -> None:
    fingerprint = ErrorFingerprint.create("payload.bin extraction failed", category="source")
    service = OnlineRemediationService(tmp_path)
    receipt = service.lookup(fingerprint)
    candidate = next(
        item for item in receipt.candidates if item.local_action_id == "inspect-payload-source"
    )
    fake = TypedLocalActionEvidence(
        candidate.local_action_id,
        "f" * 64,
        "knowledge/missing.romverse",
        "romverse.ota-source-blueprint",
    )

    with pytest.raises(ValueError, match="absent, invalid, or mismatched"):
        service.record_verified_outcome(
            fingerprint,
            candidate,
            fake,
            "A caller supplied only an unproven digest.",
        )


def test_online_confirmation_is_revoked_when_tool_evidence_changes(tmp_path) -> None:
    adb = tmp_path / "adb"
    adb.write_bytes(b"verified platform tool")
    adb.chmod(0o755)
    tool_receipt = ToolchainVerificationStore(tmp_path).record(
        (ToolStatus("ADB", True, str(adb), "1.0.41", "Ready"),),
        ("ADB",),
    )
    evidence = TypedLocalActionEvidence(
        "verify-platform-tools",
        tool_receipt.receipt_digest,
        tool_receipt.evidence_ref,
        ToolchainVerificationStore.FORMAT,
    )
    fingerprint = ErrorFingerprint.create(
        "platform tools command not found exit code 127",
        category="tools",
    )
    service = OnlineRemediationService(tmp_path)
    researched = service.lookup(fingerprint)
    candidate = next(
        item for item in researched.candidates if item.local_action_id == "verify-platform-tools"
    )
    service.record_verified_outcome(
        fingerprint,
        candidate,
        evidence,
        "Exact Platform Tools verification receipt passed.",
    )

    assert next(
        item
        for item in service.lookup(fingerprint).candidates
        if item.local_action_id == "verify-platform-tools"
    ).confirmed_working

    adb.write_bytes(b"changed after outcome")
    assert service.load(fingerprint) is None


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
