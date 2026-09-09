from __future__ import annotations

import hashlib

import pytest

from romverse.knowledge.evidence_persistence import (
    EvidenceArtifactPersistence,
    EvidencePersistence,
    EvidencePersistenceRecord,
    EvidenceRecordKind,
)


def test_persistence_contract_is_interface_only_and_authority_free() -> None:
    record = EvidencePersistenceRecord(
        schema_version=1,
        record_id=hashlib.sha256(b"record").hexdigest(),
        kind=EvidenceRecordKind.CANONICAL_DEVICE,
        payload_digest=hashlib.sha256(b"payload").hexdigest(),
        recorded_at="2026-09-09T00:00:00+00:00",
    )

    assert record.execution_authority == "none"
    assert not record.phone_action_allowed
    assert not record.guardian_approval
    assert not record.bootloader_relock_allowed
    assert not hasattr(EvidencePersistence, "__dict__") or not hasattr(
        EvidencePersistence, "workspace"
    )
    with pytest.raises(ValueError, match="execution authority"):
        EvidencePersistenceRecord(
            schema_version=1,
            record_id="a" * 64,
            kind=EvidenceRecordKind.CANONICAL_DEVICE,
            payload_digest="b" * 64,
            recorded_at="2026-09-09T00:00:00+00:00",
            guardian_approval=True,
        )
    with pytest.raises(ValueError, match="digests"):
        EvidencePersistenceRecord(
            schema_version=1,
            record_id="not-a-digest",
            kind=EvidenceRecordKind.CANONICAL_FIRMWARE,
            payload_digest="b" * 64,
            recorded_at="2026-09-09T00:00:00+00:00",
        )


def test_future_storage_can_satisfy_interfaces_without_a_bundled_backend() -> None:
    class ContractOnlyStore:
        def load_record(self, record_id):
            return None

        def append_record(self, record, payload):
            return None

        def history(self, record_id):
            return ()

    class ContractOnlyArtifacts:
        def has_exact_artifact(self, sha256, size_bytes):
            return False

        def reference_exact_artifact(self, *, sha256, size_bytes, media_type):
            return f"sha256:{sha256}"

    assert isinstance(ContractOnlyStore(), EvidencePersistence)
    assert isinstance(ContractOnlyArtifacts(), EvidenceArtifactPersistence)
