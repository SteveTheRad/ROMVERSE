"""Interface-only persistence boundary for Device Intelligence evidence.

This module intentionally contains no filesystem, database, object-store, network, or migration
implementation.  It describes the minimum contracts future adapters must satisfy while keeping
evidence unable to grant consequential authority.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable


class EvidenceRecordKind(StrEnum):
    CANONICAL_DEVICE = "canonical-device"
    CANONICAL_FIRMWARE = "canonical-firmware"
    SOURCE_AUTHORITY = "source-authority"
    EVIDENCE_LIFECYCLE = "evidence-lifecycle"


@dataclass(frozen=True, slots=True)
class EvidencePersistenceRecord:
    schema_version: int
    record_id: str
    kind: EvidenceRecordKind
    payload_digest: str
    recorded_at: str
    execution_authority: str = "none"
    phone_action_allowed: bool = False
    guardian_approval: bool = False
    bootloader_relock_allowed: bool = False

    def __post_init__(self) -> None:
        if (
            self.execution_authority != "none"
            or self.phone_action_allowed
            or self.guardian_approval
            or self.bootloader_relock_allowed
        ):
            raise ValueError("Evidence persistence cannot grant execution authority")
        if (
            type(self.schema_version) is not int
            or self.schema_version != 1
            or not isinstance(self.kind, EvidenceRecordKind)
            or any(
                re.fullmatch(r"[0-9a-f]{64}", value) is None
                for value in (self.record_id, self.payload_digest)
            )
        ):
            raise ValueError("Evidence persistence requires exact schema-one digests")
        try:
            recorded = datetime.fromisoformat(self.recorded_at)
        except (TypeError, ValueError) as exc:
            raise ValueError("Evidence persistence timestamp is invalid") from exc
        if recorded.tzinfo is None or recorded.utcoffset() is None:
            raise ValueError("Evidence persistence timestamp requires a timezone")


@runtime_checkable
class EvidencePersistence(Protocol):
    """Future structured storage must preserve exact immutable record history."""

    def load_record(self, record_id: str) -> Mapping[str, object] | None: ...

    def append_record(
        self,
        record: EvidencePersistenceRecord,
        payload: Mapping[str, object],
    ) -> None: ...

    def history(self, record_id: str) -> tuple[EvidencePersistenceRecord, ...]: ...


@runtime_checkable
class EvidenceArtifactPersistence(Protocol):
    """Future content-addressed storage interface; it does not authorize upload or execution."""

    def has_exact_artifact(self, sha256: str, size_bytes: int) -> bool: ...

    def reference_exact_artifact(
        self,
        *,
        sha256: str,
        size_bytes: int,
        media_type: str,
    ) -> str: ...
