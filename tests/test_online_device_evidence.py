from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from romverse.knowledge.online_evidence import (
    ClaimAuthorityDomain,
    ClaimKind,
    EvidenceConsumer,
    EvidenceFreshness,
    EvidenceHistoryEntry,
    EvidenceLifecycleStatus,
    EvidenceScope,
    EvidenceSourceRegistry,
    EvidenceState,
    OnlineEvidenceError,
    OnlineEvidenceStore,
    SourceCategory,
    claim_from_registered_content,
    claim_source_authority_mapping,
    compare_with_later_evidence,
    create_claim,
    create_claim_source_authority,
    default_source_adapters,
    evidence_lifecycle_for_claim,
    evidence_lifecycle_mapping,
    freshness_at,
    merge_claims,
    parse_claim_source_authority,
    parse_evidence_lifecycle,
    project_evidence,
    scrub_private_text,
)

NOW = datetime(2026, 9, 8, 1, 0, tzinfo=UTC)
DIGEST = hashlib.sha256(b"source").hexdigest()


def _claim(
    value: str,
    *,
    source_id: str = "android.docs",
    publisher: str = "Google Android",
    category: SourceCategory = SourceCategory.OFFICIAL_ANDROID,
    state: EvidenceState = EvidenceState.OFFICIALLY_DOCUMENTED,
    confidence: int = 80,
    claim_key: str = "device.slot-layout",
):
    return create_claim(
        claim_key=claim_key,
        scope=EvidenceScope(codenames=("nebula",), firmware_versions=("OS1.2",)),
        source_id=source_id,
        url=f"https://example.com/{source_id}",
        publisher=publisher,
        category=category,
        retrieved_at=NOW,
        content_digest=DIGEST,
        parser_id="romverse.test-parser",
        parser_version="1",
        structured_value=value,
        freshness=EvidenceFreshness.CURRENT,
        state=state,
        confidence=confidence,
    )


def test_strict_claim_archive_round_trip_is_private_and_authority_free(tmp_path) -> None:
    store = OnlineEvidenceStore(tmp_path)
    saved = store.merge((_claim("a/b"),), now=NOW)

    assert store.load() == saved
    assert saved.execution_authority == "none"
    assert not saved.phone_action_allowed
    assert not saved.bootloader_relock_allowed
    assert saved.claims[0].source.content_digest == DIGEST
    assert saved.claims[0].source.parser_id == "romverse.test-parser"
    if os.name != "nt":
        assert store.path.stat().st_mode & 0o777 == 0o600


def test_store_rejects_extra_fields_oversize_and_tampering(tmp_path, monkeypatch) -> None:
    store = OnlineEvidenceStore(tmp_path)
    store.merge((_claim("a-only"),), now=NOW)
    raw = json.loads(store.path.read_text(encoding="utf-8"))
    raw["unexpected"] = True
    store.path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(OnlineEvidenceError, match="fields"):
        store.load()

    store.path.unlink()
    store.merge((_claim("a-only"),), now=NOW)
    raw = json.loads(store.path.read_text(encoding="utf-8"))
    raw["phone_action_allowed"] = True
    store.path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(OnlineEvidenceError, match="phone action"):
        store.load()

    monkeypatch.setattr(OnlineEvidenceStore, "MAXIMUM_BYTES", 16)
    with pytest.raises(OnlineEvidenceError, match="size boundary"):
        OnlineEvidenceStore(tmp_path / "other").merge((_claim("a-only"),), now=NOW)


def test_store_rejects_symlink_target(tmp_path) -> None:
    if os.name == "nt":
        pytest.skip("POSIX symbolic-link boundary")
    store = OnlineEvidenceStore(tmp_path)
    store.root.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    store.path.symlink_to(outside)

    with pytest.raises(OnlineEvidenceError):
        store.merge((_claim("a-only"),), now=NOW)


def test_duplicate_evidence_is_deterministically_deduplicated(tmp_path) -> None:
    claim = _claim("a/b")
    saved = OnlineEvidenceStore(tmp_path).merge((claim, claim), now=NOW)

    assert saved.claims == (claim,)


def test_registry_is_deterministic_closed_by_default_and_has_small_public_set() -> None:
    registry = EvidenceSourceRegistry()

    assert registry.adapters == tuple(sorted(registry.adapters, key=lambda item: item.adapter_id))
    assert {item.adapter_id for item in registry.adapters} == {
        "android.developer-docs",
        "android.aosp-build-numbers",
        "android.google-play-device-catalog",
        "aosp.kernel-tree",
        "aosp.source-tree",
        "google.pixel-factory-index",
    }
    assert all(not item.requires_authentication for item in registry.adapters)
    assert all(not item.allow_redirects for item in registry.adapters)
    with pytest.raises(OnlineEvidenceError, match="exactly one"):
        registry.resolve("https://private.example/device")


def test_registry_rejects_duplicate_or_ambiguous_adapters() -> None:
    adapter = default_source_adapters()[0]
    with pytest.raises(OnlineEvidenceError, match="unique"):
        EvidenceSourceRegistry((adapter, adapter))

    overlapping = replace(adapter, adapter_id="android.overlap")
    registry = EvidenceSourceRegistry((adapter, overlapping))
    with pytest.raises(OnlineEvidenceError, match="exactly one"):
        registry.resolve("https://developer.android.com/topic/architecture")


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        ({"final_url": "https://developer.android.com/redirected"}, "redirected"),
        ({"status": 429}, "non-success"),
        ({"content_type": "application/zip"}, "content type"),
        ({"content_encoding": "gzip"}, "Compressed"),
    ),
)
def test_registered_content_rejects_bad_transport(changes, message) -> None:
    values = {
        "requested_url": "https://developer.android.com/topic/architecture",
        "final_url": "https://developer.android.com/topic/architecture",
        "status": 200,
        "content_type": "text/html",
        "content_encoding": "identity",
    }
    values.update(changes)

    with pytest.raises(OnlineEvidenceError, match=message):
        claim_from_registered_content(
            EvidenceSourceRegistry(),
            b"This device uses virtual A/B updates.",
            retrieved_at=NOW,
            claim_key="device.slot-layout",
            scope=EvidenceScope(codenames=("nebula",)),
            supporting_excerpt="virtual A/B updates",
            confidence=75,
            **values,
        )


def test_registered_content_is_bounded_and_excerpt_must_be_exact() -> None:
    adapter = replace(default_source_adapters()[0], maximum_bytes=8)
    registry = EvidenceSourceRegistry((adapter,))
    kwargs = {
        "requested_url": "https://developer.android.com/topic/architecture",
        "final_url": "https://developer.android.com/topic/architecture",
        "status": 200,
        "content_type": "text/html",
        "retrieved_at": NOW,
        "claim_key": "device.slot-layout",
        "scope": EvidenceScope(codenames=("nebula",)),
        "supporting_excerpt": "virtual A/B",
        "confidence": 75,
    }
    with pytest.raises(OnlineEvidenceError, match="byte boundary"):
        claim_from_registered_content(registry, b"This device uses virtual A/B updates.", **kwargs)

    registry = EvidenceSourceRegistry()
    with pytest.raises(OnlineEvidenceError, match="not present"):
        claim_from_registered_content(registry, b"No matching statement.", **kwargs)


def test_registered_content_retains_exact_provenance_and_no_command_authority() -> None:
    body = b"This device uses virtual A/B updates."
    claim = claim_from_registered_content(
        EvidenceSourceRegistry(),
        body,
        requested_url="https://developer.android.com/topic/architecture",
        final_url="https://developer.android.com/topic/architecture",
        status=200,
        content_type="text/html; charset=utf-8",
        retrieved_at=NOW,
        claim_key="device.slot-layout",
        scope=EvidenceScope(codenames=("nebula",)),
        supporting_excerpt="virtual A/B updates",
        confidence=75,
    )

    assert claim.supporting_excerpt == "virtual A/B updates"
    assert claim.source.content_digest == hashlib.sha256(body).hexdigest()
    assert claim.state is EvidenceState.OFFICIALLY_DOCUMENTED
    assert claim.source.freshness is EvidenceFreshness.UNCONFIRMED
    assert claim.execution_authority == "none"
    assert not claim.phone_action_allowed
    assert not claim.guardian_approval


def test_deterministic_merge_corroborates_independent_matching_sources() -> None:
    claims = (
        _claim("a/b", source_id="android.docs", publisher="Google Android", confidence=82),
        _claim(
            "a/b",
            source_id="maintainer.docs",
            publisher="Device Maintainer",
            category=SourceCategory.MAINTAINER_DOCUMENTATION,
            state=EvidenceState.SOURCE_REPORTED,
            confidence=70,
        ),
    )

    first = merge_claims(claims)
    second = merge_claims(tuple(reversed(claims)))

    assert first == second
    assert first[0].state is EvidenceState.INDEPENDENTLY_CORROBORATED
    assert first[0].confidence == 82
    assert not first[0].conflict
    assert len(first[0].claim_ids) == 2


def test_conflicting_claims_are_both_retained_and_trigger_investigation() -> None:
    online = _claim("a/b", confidence=85)
    live = _claim(
        "a-only",
        source_id="local.live-read-only",
        publisher="ROMVERSE read-only Device Engine",
        category=SourceCategory.LIVE_DEVICE,
        state=EvidenceState.LIVE_CONFIRMED,
        confidence=100,
    )

    merged = compare_with_later_evidence((online,), (live,))

    assert merged[0].values == ("a-only", "a/b")
    assert merged[0].state is EvidenceState.CONFLICTING
    assert merged[0].confidence == 85
    assert merged[0].conflict
    assert merged[0].investigation_required


def test_matching_live_and_firmware_evidence_strengthen_without_replacing_sources() -> None:
    online = _claim("a/b", confidence=75)
    firmware = _claim(
        "a/b",
        source_id="local.firmware",
        publisher="ROMVERSE firmware inspection",
        category=SourceCategory.FIRMWARE,
        state=EvidenceState.FIRMWARE_DERIVED,
        confidence=90,
    )
    live = _claim(
        "a/b",
        source_id="local.live-read-only",
        publisher="ROMVERSE read-only Device Engine",
        category=SourceCategory.LIVE_DEVICE,
        state=EvidenceState.LIVE_CONFIRMED,
        confidence=100,
    )

    merged = compare_with_later_evidence((online,), (firmware, live))

    assert merged[0].state is EvidenceState.LIVE_CONFIRMED
    assert merged[0].confidence == 100
    assert len(merged[0].source_ids) == 3


def test_unknown_device_projects_to_investigation_never_unsupported() -> None:
    for consumer in EvidenceConsumer:
        projection = project_evidence((), consumer)
        assert projection.compatibility_hint == "UNCONFIRMED"
        assert projection.investigation_required
        assert projection.next_action.startswith("Gather bounded read-only")
        assert projection.execution_authority == "none"
        assert not projection.phone_action_allowed
        assert not projection.guardian_approval
        assert not projection.bootloader_relock_allowed
        assert projection.workflow == (
            "connect-device-read-only",
            "gather-evidence",
            "research-gaps",
            "show-identity-and-confidence",
            "present-one-next-action",
        )


def test_privacy_scrubbing_excludes_device_account_secret_and_path_data() -> None:
    unsafe = (
        "IMEI=123456789012345 serial:ABC123 account id=user-7 "
        "api_key=hunter2 bearer abc.def user@example.com /home/alice/firmware/private.zip"
    )
    scrubbed = scrub_private_text(unsafe)

    assert "123456789012345" not in scrubbed
    assert "ABC123" not in scrubbed
    assert "user-7" not in scrubbed
    assert "hunter2" not in scrubbed
    assert "abc.def" not in scrubbed
    assert "user@example.com" not in scrubbed
    assert "/home/alice" not in scrubbed
    assert scrubbed.count("[private]") >= 7

    claim = create_claim(
        claim_key="device.report",
        scope=EvidenceScope(scope_note=unsafe),
        source_id="community.report",
        url="https://example.com/report",
        publisher="Technical report",
        category=SourceCategory.TECHNICAL_COMMUNITY,
        retrieved_at=NOW,
        content_digest=DIGEST,
        parser_id="romverse.report-parser",
        parser_version="1",
        supporting_excerpt=unsafe,
        confidence=30,
    )
    encoded = json.dumps({"claim": str(claim)})
    assert "123456789012345" not in encoded
    assert "/home/alice" not in encoded


def test_private_source_urls_are_rejected() -> None:
    with pytest.raises(OnlineEvidenceError, match="credentials"):
        _ = create_claim(
            claim_key="device.identity",
            scope=EvidenceScope(),
            source_id="unsafe.source",
            url="https://user:password@example.com/report",
            publisher="Example",
            category=SourceCategory.TECHNICAL_COMMUNITY,
            retrieved_at=NOW,
            content_digest=DIGEST,
            parser_id="romverse.test",
            parser_version="1",
            structured_value="nebula",
        )
    with pytest.raises(OnlineEvidenceError, match="private query"):
        EvidenceSourceRegistry().resolve("https://developer.android.com/topic?serial=ABC123")


def test_freshness_is_explicit_for_current_aged_stale_and_future_evidence() -> None:
    assert freshness_at(NOW, NOW + timedelta(days=29), 30) is EvidenceFreshness.CURRENT
    assert freshness_at(NOW, NOW + timedelta(days=45), 30) is EvidenceFreshness.AGED
    assert freshness_at(NOW, NOW + timedelta(days=90), 30) is EvidenceFreshness.STALE
    assert freshness_at(NOW, NOW - timedelta(seconds=1), 30) is EvidenceFreshness.UNCONFIRMED


def test_stale_or_unconfirmed_freshness_requests_more_investigation() -> None:
    stale = replace(
        _claim("a/b"),
        source=replace(_claim("a/b").source, freshness=EvidenceFreshness.STALE),
    )
    unknown = replace(
        _claim("a/b"),
        source=replace(_claim("a/b").source, freshness=EvidenceFreshness.UNCONFIRMED),
    )

    assert merge_claims((stale,))[0].state is EvidenceState.OUTDATED
    assert project_evidence((stale,), EvidenceConsumer.DEVICE_DNA).investigation_required
    assert project_evidence((unknown,), EvidenceConsumer.DEVICE_DNA).investigation_required


@pytest.mark.parametrize("state", tuple(EvidenceState))
def test_all_approved_claim_states_round_trip(tmp_path, state) -> None:
    store = OnlineEvidenceStore(tmp_path / state.value)
    claim = _claim(state.value, state=state, claim_key=f"state.{state.value}")

    assert store.merge((claim,), now=NOW).claims[0].state is state


def test_legacy_schema_one_identity_archive_remains_readable_and_migrates_without_promotion(
    tmp_path,
) -> None:
    repository = Path(__file__).resolve().parents[1]
    legacy_path = (
        repository
        / "docs/sync/evidence/google-play-live/knowledge/online-device-evidence/claims.romverse"
    )
    legacy = OnlineEvidenceStore(legacy_path.parents[2]).load()

    assert (
        legacy.archive_digest == "9f5d9e29ed16cd4362ee7e382b469462711afd90f8ea0eafff4fd4913ce54c61"
    )
    assert all(claim.knowledge_kind is ClaimKind.IDENTITY for claim in legacy.claims)
    assert all(not claim.symptoms and not claim.remedy_description for claim in legacy.claims)
    before = tuple(
        sorted((claim.claim_key, claim.structured_value, claim.state) for claim in legacy.claims)
    )

    migrated = OnlineEvidenceStore(tmp_path).save(legacy)

    assert migrated.archive_digest != legacy.archive_digest
    assert (
        tuple(
            sorted(
                (claim.claim_key, claim.structured_value, claim.state) for claim in migrated.claims
            )
        )
        == before
    )
    assert all(claim.knowledge_kind is ClaimKind.IDENTITY for claim in migrated.claims)


def test_typed_guide_fields_round_trip_as_non_executable_official_guidance(tmp_path) -> None:
    guide = create_claim(
        claim_key="diagnostic.usb-connection",
        scope=EvidenceScope(scope_note="Android devices connected to a development host."),
        source_id="android.device-guide",
        url="https://developer.android.com/studio/run/device",
        publisher="Google Android",
        category=SourceCategory.OFFICIAL_ANDROID,
        retrieved_at=NOW,
        content_digest=DIGEST,
        parser_id="romverse.android-device-guide",
        parser_version="1",
        supporting_excerpt="Check the USB cable if the device is not detected.",
        state=EvidenceState.OFFICIALLY_DOCUMENTED,
        confidence=80,
        knowledge_kind=ClaimKind.GUIDE,
        symptoms=("Device is not detected over USB.",),
        error_identifiers=("adb-not-detected",),
        prerequisites=("Use a data-capable USB connection.",),
        affected_builds=("Android development devices; exact build unconfirmed.",),
        diagnostic_description="Review cable and host connection evidence.",
        remedy_description="Try another data-capable cable and reconnect for a read-only scan.",
        expected_result="The intended device becomes visible for read-only inspection.",
        rollback_recovery_route="Disconnect the cable and preserve the prior device state.",
    )

    saved = OnlineEvidenceStore(tmp_path).merge((guide,), now=NOW)
    loaded = saved.claims[0]

    assert loaded.knowledge_kind is ClaimKind.GUIDE
    assert loaded.state is EvidenceState.OFFICIALLY_DOCUMENTED
    assert loaded.symptoms == ("Device is not detected over USB.",)
    assert loaded.execution_authority == "none"
    assert not loaded.phone_action_allowed
    assert not loaded.guardian_approval


@pytest.mark.parametrize(
    "instruction",
    (
        "adb devices",
        "fastboot reboot",
        "sudo install-driver",
        "Run `tool --force`.",
        "<script>alert('unsafe')</script>",
    ),
)
def test_typed_guidance_rejects_executable_instructions(instruction) -> None:
    with pytest.raises(OnlineEvidenceError, match="executable"):
        create_claim(
            claim_key="diagnostic.unsafe",
            scope=EvidenceScope(),
            source_id="android.device-guide",
            url="https://developer.android.com/studio/run/device",
            publisher="Google Android",
            category=SourceCategory.OFFICIAL_ANDROID,
            retrieved_at=NOW,
            content_digest=DIGEST,
            parser_id="romverse.android-device-guide",
            parser_version="1",
            supporting_excerpt="Review the connection state.",
            knowledge_kind=ClaimKind.GUIDE,
            remedy_description=instruction,
        )


def test_source_authority_is_claim_specific_and_never_execution_authority() -> None:
    authority = create_claim_source_authority(
        source_id="xiaomi.official-specification",
        domains=(ClaimAuthorityDomain.MODEL_IDENTITY, ClaimAuthorityDomain.CODENAME),
        applicable_claim_keys=("device.codename", "device.model"),
        evidence_claim_ids=("a" * 64,),
    )
    fixture = (
        Path(__file__).resolve().parent
        / "fixtures/device_intelligence/claim-source-authority-v1.json"
    )
    loaded = parse_claim_source_authority(json.loads(fixture.read_text(encoding="utf-8")))

    assert loaded == authority
    assert parse_claim_source_authority(claim_source_authority_mapping(authority)) == authority
    assert authority.applies_to(ClaimAuthorityDomain.CODENAME, "device.codename")
    assert not authority.applies_to(
        ClaimAuthorityDomain.PARTITION_LAYOUT, "device.partition-layout"
    )
    assert authority.execution_authority == "none"
    assert not authority.guardian_approval
    assert not authority.bootloader_relock_allowed


def test_source_authority_rejects_empty_malformed_or_promoted_contracts() -> None:
    with pytest.raises(OnlineEvidenceError, match="exact evidence"):
        create_claim_source_authority(
            source_id="source.empty",
            domains=(),
            applicable_claim_keys=("device.model",),
            evidence_claim_ids=("a" * 64,),
        )
    authority = create_claim_source_authority(
        source_id="source.exact",
        domains=(ClaimAuthorityDomain.MODEL_IDENTITY,),
        applicable_claim_keys=("device.model",),
        evidence_claim_ids=("a" * 64,),
    )
    raw = json.loads(json.dumps(claim_source_authority_mapping(authority)))
    raw["guardian_approval"] = True
    with pytest.raises(OnlineEvidenceError, match="execution authority"):
        parse_claim_source_authority(raw)


def test_evidence_lifecycle_retains_scope_conflicts_freshness_and_history(tmp_path) -> None:
    first = _claim("a/b", source_id="source.one")
    second = _claim("a-only", source_id="source.two")
    linked = OnlineEvidenceStore(tmp_path).merge((first, second), now=NOW).claims[0]
    history = (
        EvidenceHistoryEntry(
            NOW.isoformat(), EvidenceLifecycleStatus.ACTIVE, "Initial retained evidence."
        ),
        EvidenceHistoryEntry(
            (NOW + timedelta(days=1)).isoformat(),
            EvidenceLifecycleStatus.SUPERSEDED,
            "A newer exact claim exists; the original remains retained.",
        ),
    )
    lifecycle = evidence_lifecycle_for_claim(
        linked,
        observed_at=NOW - timedelta(hours=1),
        revalidated_at=NOW + timedelta(days=1),
        status=EvidenceLifecycleStatus.SUPERSEDED,
        history=history,
    )
    loaded = parse_evidence_lifecycle(evidence_lifecycle_mapping(lifecycle))

    assert loaded == lifecycle
    assert loaded.artifact_digest == DIGEST
    assert loaded.scope.codenames == ("nebula",)
    assert loaded.contradicting_claim_ids
    assert loaded.status is EvidenceLifecycleStatus.SUPERSEDED
    assert loaded.history == history
    assert loaded.execution_authority == "none"
    assert not loaded.phone_action_allowed
    assert not loaded.guardian_approval
    assert not loaded.bootloader_relock_allowed


def test_evidence_lifecycle_represents_stale_quarantine_and_expiry_without_deletion() -> None:
    stale_claim = replace(
        _claim("a/b"),
        source=replace(_claim("a/b").source, freshness=EvidenceFreshness.STALE),
    )
    quarantined = evidence_lifecycle_for_claim(
        stale_claim,
        observed_at=NOW,
        status=EvidenceLifecycleStatus.QUARANTINED,
        history=(
            EvidenceHistoryEntry(
                NOW.isoformat(),
                EvidenceLifecycleStatus.QUARANTINED,
                "Conflicting applicability requires review.",
            ),
        ),
    )
    expired = evidence_lifecycle_for_claim(
        stale_claim,
        observed_at=NOW,
        status=EvidenceLifecycleStatus.EXPIRED,
        history=(
            EvidenceHistoryEntry(
                NOW.isoformat(), EvidenceLifecycleStatus.EXPIRED, "Freshness window elapsed."
            ),
        ),
    )

    assert quarantined.freshness is EvidenceFreshness.STALE
    assert quarantined.claim_id == stale_claim.claim_id
    assert expired.claim_id == stale_claim.claim_id
    assert quarantined.evidence_id != expired.evidence_id


def test_evidence_lifecycle_rejects_impossible_chronology_and_status_history() -> None:
    claim = _claim("a/b")
    with pytest.raises(OnlineEvidenceError, match="observation"):
        evidence_lifecycle_for_claim(claim, observed_at=NOW + timedelta(seconds=1))
    with pytest.raises(OnlineEvidenceError, match="revalidation"):
        evidence_lifecycle_for_claim(
            claim,
            observed_at=NOW - timedelta(hours=1),
            revalidated_at=NOW - timedelta(seconds=1),
        )
    with pytest.raises(OnlineEvidenceError, match="predates"):
        evidence_lifecycle_for_claim(
            claim,
            observed_at=NOW,
            history=(
                EvidenceHistoryEntry(
                    (NOW - timedelta(seconds=1)).isoformat(),
                    EvidenceLifecycleStatus.ACTIVE,
                    "Impossible early history.",
                ),
            ),
        )
    with pytest.raises(OnlineEvidenceError, match="does not match"):
        evidence_lifecycle_for_claim(
            claim,
            observed_at=NOW,
            status=EvidenceLifecycleStatus.ACTIVE,
            history=(
                EvidenceHistoryEntry(
                    NOW.isoformat(),
                    EvidenceLifecycleStatus.SUPERSEDED,
                    "Mismatched final state.",
                ),
            ),
        )

    valid = evidence_lifecycle_for_claim(
        claim,
        observed_at=NOW - timedelta(hours=1),
        revalidated_at=NOW + timedelta(hours=1),
        status=EvidenceLifecycleStatus.ACTIVE,
        history=(
            EvidenceHistoryEntry(
                NOW.isoformat(), EvidenceLifecycleStatus.ACTIVE, "Evidence retained."
            ),
        ),
    )
    mapping = evidence_lifecycle_mapping(valid)
    impossible_observation = dict(mapping)
    impossible_observation["observed_at"] = (NOW + timedelta(seconds=1)).isoformat()
    with pytest.raises(OnlineEvidenceError, match="observation"):
        parse_evidence_lifecycle(impossible_observation)
    impossible_revalidation = dict(mapping)
    impossible_revalidation["revalidated_at"] = (NOW - timedelta(seconds=1)).isoformat()
    with pytest.raises(OnlineEvidenceError, match="revalidation"):
        parse_evidence_lifecycle(impossible_revalidation)
    early_history = json.loads(json.dumps(mapping))
    early_history["history"][0]["recorded_at"] = (NOW - timedelta(hours=2)).isoformat()
    with pytest.raises(OnlineEvidenceError, match="predates"):
        parse_evidence_lifecycle(early_history)
    mismatched_status = json.loads(json.dumps(mapping))
    mismatched_status["status"] = EvidenceLifecycleStatus.EXPIRED.value
    with pytest.raises(OnlineEvidenceError, match="does not match"):
        parse_evidence_lifecycle(mismatched_status)


def test_lifecycle_tampering_and_additional_private_identifiers_fail_closed() -> None:
    lifecycle = evidence_lifecycle_for_claim(_claim("a/b"), observed_at=NOW)
    raw = json.loads(json.dumps(evidence_lifecycle_mapping(lifecycle)))
    raw["evidence_id"] = "f" * 64
    with pytest.raises(OnlineEvidenceError, match="identity"):
        parse_evidence_lifecycle(raw)

    unsafe = (
        "username=alice user id=person-7 auth=credential cookie=session-cookie "
        "C:\\Users\\alice\\Documents\\personal.txt"
    )
    scrubbed = scrub_private_text(unsafe)
    assert "alice" not in scrubbed
    assert "person-7" not in scrubbed
    assert "credential" not in scrubbed
    assert "session-cookie" not in scrubbed
    assert "personal.txt" not in scrubbed
