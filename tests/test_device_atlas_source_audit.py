import hashlib
import json
from datetime import date
from importlib.resources import files

from romverse.device_packs.registry import DevicePackRegistry
from romverse.device_packs.source_audit import (
    build_source_audit_manifest,
    export_source_audit,
    summarize_sources,
)


def _registry() -> DevicePackRegistry:
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    assert registry.issues == ()
    return registry


def test_source_audit_is_privacy_safe_and_reports_catalog_health() -> None:
    registry = _registry()
    summary = summarize_sources(registry, as_of=date(2026, 12, 1))
    manifest = build_source_audit_manifest(registry, as_of=date(2026, 12, 1))

    assert summary.pack_count == len(registry.packs)
    assert summary.sourced_pack_count >= 8
    assert summary.source_reference_count >= summary.sourced_pack_count
    assert summary.review_due_count == 0
    assert "xiaomi.popsicle.hyperos4.os4.0.0.23" in summary.unsourced_pack_ids
    assert manifest["catalog"]["execution_authority"] == "none"
    rendered = json.dumps(manifest)
    assert "serial" not in rendered.casefold()
    assert "imei" not in rendered.casefold()


def test_source_audit_export_is_content_addressed(tmp_path) -> None:
    exported = export_source_audit(_registry(), tmp_path, as_of=date(2026, 12, 1))
    payload = exported.output_path.read_bytes()
    document = json.loads(payload)

    assert hashlib.sha256(payload).hexdigest() == exported.sha256
    assert exported.sha256[:12] in exported.output_path.name
    assert document["catalog_digest"] == exported.catalog_digest
    assert document["format"] == "romverse.device-atlas-source-audit"
