from __future__ import annotations

import re
from pathlib import Path

from romverse.core.durable_schemas import (
    AUTHORITY_AUDIT,
    AUTHORITY_GUARDIAN,
    DURABLE_SCHEMA_INVENTORY,
    FAIL_CLOSED,
    DurableSchemaDomain,
    schema_by_format,
    schemas_for_domain,
)

ROOT = Path(__file__).resolve().parents[1]


def test_inventory_is_complete_well_formed_and_source_bound() -> None:
    assert len(DURABLE_SCHEMA_INVENTORY) == 189
    assert len({item.format_id for item in DURABLE_SCHEMA_INVENTORY}) == len(
        DURABLE_SCHEMA_INVENTORY
    )
    assert {item.domain for item in DURABLE_SCHEMA_INVENTORY} == set(DurableSchemaDomain)

    for item in DURABLE_SCHEMA_INVENTORY:
        assert item.format_id and not item.format_id.isspace()
        assert type(item.current_version) is int and item.current_version > 0
        assert item.supported_read_versions
        assert tuple(sorted(set(item.supported_read_versions))) == item.supported_read_versions
        assert all(
            type(version) is int and 0 < version <= item.current_version
            for version in item.supported_read_versions
        )
        assert item.current_version in item.supported_read_versions
        assert item.migration_or_rederivation.strip()
        assert item.failure_behavior.strip()
        assert item.authority_effect.strip()
        assert item.compatibility_tests

        implementation = ROOT / item.implementation_file
        assert implementation.is_file(), item.format_id
        assert item.implementation_marker in implementation.read_text(encoding="utf-8"), (
            item.format_id
        )
        for test_path in item.compatibility_tests:
            assert (ROOT / test_path).is_file(), (item.format_id, test_path)


def test_inventory_covers_every_required_retention_family() -> None:
    required = {
        ".romverse-workspace.json",
        "settings.json",
        "romverse.project",
        "romverse.device-dna",
        "romverse.activity-ledger",
        "romverse.guardian-execution-plan",
        "romverse.guardian-recovery-step-result",
        "romverse.recovery-autopilot",
        "romverse.offline-knowledge-archive",
        "romverse.desktop-update-stage",
        "romverse.companion-link.remembered-session",
        "romverse.companion.link-token-vault",
    }
    assert required <= {item.format_id for item in DURABLE_SCHEMA_INVENTORY}
    assert all(schemas_for_domain(domain) for domain in DurableSchemaDomain)
    assert schema_by_format("romverse.guardian-recovery-step-result") is not None
    assert schema_by_format("missing") is None


def test_every_source_format_identifier_has_an_inventory_decision() -> None:
    source_formats: set[str] = set()
    for path in (ROOT / "src" / "romverse").rglob("*.py"):
        if path.name == "durable_schemas.py":
            continue
        source_formats.update(
            re.findall(r'["\'](romverse\.[a-z0-9._-]+)["\']', path.read_text(encoding="utf-8"))
        )

    package_namespaces = {"romverse.app", "romverse.assets", "romverse.local"}
    inventoried = {item.format_id for item in DURABLE_SCHEMA_INVENTORY}
    assert source_formats - inventoried == package_namespaces


def test_packaged_json_formats_and_unformatted_trust_roots_are_accounted_for() -> None:
    inventoried = {item.format_id for item in DURABLE_SCHEMA_INVENTORY}
    for path in (ROOT / "src" / "romverse" / "assets").rglob("*.json"):
        payload = path.read_text(encoding="utf-8")
        match = re.search(r'"format"\s*:\s*"([^"]+)"', payload)
        if match is not None:
            assert match.group(1) in inventoried, path
    assert {
        "device_packs/index.json",
        "romverse.device-pack-manifest",
        "device_pack_trust/index.json",
        "desktop_update_trust.json",
        "galaxy_service_trust.json",
    } <= inventoried


def test_audit_records_and_guardian_records_cannot_claim_standalone_authority() -> None:
    for item in DURABLE_SCHEMA_INVENTORY:
        if item.audit_only:
            assert item.authority_effect == AUTHORITY_AUDIT
        if item.domain is DurableSchemaDomain.GUARDIAN:
            assert item.authority_effect in {AUTHORITY_GUARDIAN, AUTHORITY_AUDIT}
            if not item.audit_only:
                assert item.failure_behavior == FAIL_CLOSED
        assert "grants standalone execution authority" not in item.authority_effect.casefold()


def test_absolute_relock_prohibition_is_not_described_as_a_schema_authority() -> None:
    serialized = "\n".join(
        value
        for item in DURABLE_SCHEMA_INVENTORY
        for value in (
            item.format_id,
            item.migration_or_rederivation,
            item.failure_behavior,
            item.authority_effect,
        )
    )
    assert "relock permitted" not in serialized.casefold()
    assert "bootloader lock permitted" not in serialized.casefold()
