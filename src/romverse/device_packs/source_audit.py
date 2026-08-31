from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from uuid import uuid4

from romverse.device_packs.registry import DevicePackRegistry


@dataclass(frozen=True, slots=True)
class SourceAuditSummary:
    pack_count: int
    sourced_pack_count: int
    source_reference_count: int
    unique_source_count: int
    current_source_count: int
    review_due_count: int
    unsourced_pack_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SourceAuditExport:
    output_path: Path
    sha256: str
    catalog_digest: str
    size_bytes: int


def summarize_sources(
    registry: DevicePackRegistry,
    *,
    as_of: date | None = None,
) -> SourceAuditSummary:
    checked_on = as_of or date.today()
    sourced = tuple(pack for pack in registry.packs if pack.knowledge_sources)
    references = tuple(source for pack in registry.packs for source in pack.knowledge_sources)
    review_due = sum(source.is_stale(checked_on) for source in references)
    return SourceAuditSummary(
        pack_count=len(registry.packs),
        sourced_pack_count=len(sourced),
        source_reference_count=len(references),
        unique_source_count=len({source.source_id for source in references}),
        current_source_count=len(references) - review_due,
        review_due_count=review_due,
        unsourced_pack_ids=tuple(
            sorted(pack.pack_id for pack in registry.packs if not pack.knowledge_sources)
        ),
    )


def build_source_audit_manifest(
    registry: DevicePackRegistry,
    *,
    as_of: date | None = None,
) -> dict[str, object]:
    """Build a privacy-safe catalog audit; this grants no execution authority."""

    checked_on = as_of or date.today()
    summary = summarize_sources(registry, as_of=checked_on)
    catalog: dict[str, object] = {
        "checked_on": checked_on.isoformat(),
        "execution_authority": "none",
        "pack_count": summary.pack_count,
        "sourced_pack_count": summary.sourced_pack_count,
        "source_reference_count": summary.source_reference_count,
        "unique_source_count": summary.unique_source_count,
        "current_source_count": summary.current_source_count,
        "review_due_count": summary.review_due_count,
        "unsourced_pack_ids": list(summary.unsourced_pack_ids),
        "load_issues": [
            {"filename": issue.filename, "reason": issue.reason} for issue in registry.issues
        ],
        "packs": [
            {
                "pack_id": pack.pack_id,
                "pack_version": pack.version,
                "pack_sha256": pack.sha256,
                "priority": pack.priority,
                "knowledge_scope": (
                    "exact-build"
                    if pack.build_contract is not None
                    else "exact-identity"
                    if pack.model_patterns or pack.product_patterns
                    else "oem-wide"
                ),
                "sources": [
                    {
                        "source_id": source.source_id,
                        "label": source.label,
                        "authority": source.authority,
                        "scope": source.scope,
                        "url": source.url,
                        "verified_on": source.verified_on,
                        "review_status": (
                            "review-due" if source.is_stale(checked_on) else "current"
                        ),
                    }
                    for source in pack.knowledge_sources
                ],
            }
            for pack in sorted(registry.packs, key=lambda item: item.pack_id)
        ],
    }
    catalog_digest = hashlib.sha256(_canonical(catalog)).hexdigest()
    return {
        "format": "romverse.device-atlas-source-audit",
        "schema_version": 1,
        "catalog_digest": catalog_digest,
        "catalog": catalog,
    }


def export_source_audit(
    registry: DevicePackRegistry,
    workspace: Path,
    *,
    as_of: date | None = None,
) -> SourceAuditExport:
    manifest = build_source_audit_manifest(registry, as_of=as_of)
    payload = _canonical(manifest) + b"\n"
    digest = hashlib.sha256(payload).hexdigest()
    output_dir = workspace / "device_atlas_audits"
    output_dir.mkdir(parents=True, exist_ok=True)
    checked_on = str(manifest["catalog"]["checked_on"])
    output_path = output_dir / f"device-atlas-source-audit-{checked_on}-{digest[:12]}.json"
    temporary = output_dir / f".{output_path.name}.{uuid4().hex}.tmp"
    temporary.write_bytes(payload)
    os.replace(temporary, output_path)
    return SourceAuditExport(
        output_path=output_path,
        sha256=digest,
        catalog_digest=str(manifest["catalog_digest"]),
        size_bytes=len(payload),
    )


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
