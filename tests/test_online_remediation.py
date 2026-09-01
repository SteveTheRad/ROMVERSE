import hashlib
import json
import stat
from datetime import UTC, datetime, timedelta

import pytest

from romverse.infrastructure.local_store import LocalStoreError
from romverse.intelligence.action_evidence import TypedLocalActionEvidence
from romverse.intelligence.online_remediation import (
    ErrorFingerprint,
    EvidenceFreshness,
    GoogleProgrammableSearchProvider,
    OfficialCatalogProvider,
    OnlineFixCandidate,
    OnlineRemediationService,
    RedditSearchProvider,
    SourceAuthority,
)


class AcceptingTestEvidenceVerifier:
    def verify(self, evidence: TypedLocalActionEvidence) -> bool:
        return evidence.evidence_ref == f"tests/{evidence.receipt_digest}.romverse"


def evidenced_service(tmp_path, providers=()) -> OnlineRemediationService:
    return OnlineRemediationService(
        tmp_path,
        providers,
        AcceptingTestEvidenceVerifier(),
    )


def action_evidence(action_id: str, digest: str) -> TypedLocalActionEvidence:
    return TypedLocalActionEvidence(
        action_id,
        digest,
        f"tests/{digest}.romverse",
        "romverse.test-action",
    )


def test_official_guidance_is_content_addressed_and_remote_text_has_no_authority(tmp_path):
    fingerprint = ErrorFingerprint.create(
        "avbtool failed while parsing vbmeta",
        category="rom-build",
        manufacturer="Xiaomi",
        model="2509FPN0BC",
        marketing_name="Xiaomi 17 Pro Max",
        codename="popsicle",
        build_id="OS4.0.0.23.XPBCNXM",
        tool_name="AVBTool",
    )
    service = OnlineRemediationService(tmp_path)

    receipt = service.lookup(fingerprint)

    assert receipt.candidates
    assert receipt.candidates[0].authority is SourceAuthority.OFFICIAL
    assert not receipt.candidates[0].confirmed_working
    assert receipt.execution_authority == "guidance-only"
    assert service.load(fingerprint) == receipt
    assert (
        tmp_path / "knowledge" / "online-remediation" / f"{fingerprint.fingerprint_id}.romverse"
    ).is_file()


def test_error_fingerprint_scrubs_paths_contacts_credentials_ips_and_serials() -> None:
    fingerprint = ErrorFingerprint.create(
        "Failure at /home/steve/private/file.img for person@example.com "
        "token=top-secret 192.168.1.50 serial=private-serial-1234"
    )

    normalized = fingerprint.normalized_error
    assert "/home/steve" not in normalized
    assert "person@example.com" not in normalized
    assert "top-secret" not in normalized
    assert "192.168.1.50" not in normalized
    assert "private-serial-1234" not in normalized
    assert "<path>" in normalized
    assert "<email>" in normalized
    assert "<credential>" in normalized
    assert "<ip>" in normalized
    assert "<identifier>" in normalized


def test_reddit_results_stay_unconfirmed_without_independent_corroboration(tmp_path):
    payload = {
        "data": {
            "children": [
                {
                    "data": {
                        "id": "abc",
                        "title": "2509FPN0BC popsicle payload extraction fix",
                        "selftext": "Worked on OS4.0.0.23.XPBCNXM after verifying the payload hash.",
                        "permalink": "/r/AndroidQuestions/comments/abc/example/",
                    }
                }
            ]
        }
    }
    provider = RedditSearchProvider(lambda _url, _headers, _maximum: json.dumps(payload).encode())
    fingerprint = ErrorFingerprint.create(
        "payload.bin extraction failed",
        category="source",
        model="2509FPN0BC",
        codename="popsicle",
        build_id="OS4.0.0.23.XPBCNXM",
    )

    receipt = OnlineRemediationService(tmp_path, (provider,)).lookup(fingerprint)

    assert len(receipt.candidates) == 1
    assert receipt.candidates[0].authority is SourceAuthority.COMMUNITY
    assert not receipt.candidates[0].confirmed_working


def test_provider_cannot_self_confirm_a_fix_or_inject_an_action_identifier(tmp_path):
    fingerprint = ErrorFingerprint.create(
        "payload.bin extraction failed",
        model="2509FPN0BC",
        codename="popsicle",
    )

    class Provider:
        def search(self, _fingerprint):
            return (
                OnlineFixCandidate(
                    "official.claim",
                    SourceAuthority.OFFICIAL,
                    "2509FPN0BC popsicle payload guidance",
                    "https://source.android.com/docs/core/ota/ab",
                    "An upstream page cannot declare a local ROMVERSE result successful.",
                    local_action_id="inspect-payload-source",
                    confidence=95,
                    confirmed_working=True,
                ),
                OnlineFixCandidate(
                    "hostile.action",
                    SourceAuthority.OFFICIAL,
                    "Injected action",
                    "https://source.android.com/docs/core/ota/ab",
                    "Remote actions are not part of the typed local allowlist.",
                    local_action_id="run-remote-shell",
                    confidence=99,
                ),
            )

    receipt = OnlineRemediationService(tmp_path, (Provider(),)).lookup(fingerprint)

    assert len(receipt.candidates) == 1
    assert receipt.candidates[0].source_id == "official.claim"
    assert not receipt.candidates[0].confirmed_working
    assert OnlineRemediationService(tmp_path).load(fingerprint) == receipt


def test_invalid_remote_source_identity_cannot_control_outcome_path(tmp_path):
    fingerprint = ErrorFingerprint.create("payload.bin extraction failed", category="source")
    service = OnlineRemediationService(tmp_path)
    candidate = OnlineFixCandidate(
        "../../outside",
        SourceAuthority.OFFICIAL,
        "Payload guidance",
        "https://source.android.com/docs/core/ota/ab",
        "Invalid source identifier.",
        local_action_id="inspect-payload-source",
        confidence=90,
    )

    with pytest.raises(ValueError, match="no trusted typed"):
        service.record_verified_outcome(
            fingerprint,
            candidate,
            action_evidence(candidate.local_action_id, "f" * 64),
            "Typed payload inspection completed.",
        )

    assert not (tmp_path / "outside").exists()


def test_google_provider_rejects_non_https_and_labels_unknown_hosts_discovery_only(tmp_path):
    payload = {
        "items": [
            {"title": "Unsafe", "link": "http://example.com/fix", "snippet": "skip"},
            {
                "title": "popsicle AVB repair notes",
                "link": "https://example.com/fix",
                "snippet": "2509FPN0BC OS4.0.0.23.XPBCNXM",
            },
        ]
    }
    provider = GoogleProgrammableSearchProvider(
        "key",
        "engine",
        lambda _url, _headers, _maximum: json.dumps(payload).encode(),
    )
    fingerprint = ErrorFingerprint.create(
        "AVB mismatch",
        model="2509FPN0BC",
        codename="popsicle",
        build_id="OS4.0.0.23.XPBCNXM",
    )

    receipt = OnlineRemediationService(tmp_path, (provider,)).lookup(fingerprint)

    assert len(receipt.candidates) == 1
    assert receipt.candidates[0].authority is SourceAuthority.DISCOVERY
    assert not receipt.candidates[0].confirmed_working


def test_candidate_cannot_point_to_local_network(tmp_path):
    class Provider:
        def search(self, _fingerprint):
            return (
                OnlineFixCandidate(
                    "bad",
                    SourceAuthority.COMMUNITY,
                    "Bad",
                    "https://127.0.0.1/fix",
                    "Do not fetch this.",
                    confidence=99,
                ),
            )

    receipt = OnlineRemediationService(tmp_path, (Provider(),)).lookup(
        ErrorFingerprint.create("failure")
    )

    assert receipt.candidates == ()


def test_only_successful_typed_local_outcome_promotes_fix_to_confirmed(tmp_path):
    fingerprint = ErrorFingerprint.create(
        "avbtool failed while parsing vbmeta",
        category="avb",
        model="2509FPN0BC",
        codename="popsicle",
    )
    service = evidenced_service(tmp_path)
    first = service.lookup(fingerprint)
    candidate = next(
        item for item in first.candidates if item.local_action_id == "inspect-avb-topology"
    )
    assert not candidate.confirmed_working

    outcome = service.record_verified_outcome(
        fingerprint,
        candidate,
        action_evidence(candidate.local_action_id, "a" * 64),
        "Typed AVB inspection completed and its descriptor receipt verified.",
    )
    second = service.lookup(fingerprint)

    assert outcome.success
    assert outcome.schema_version == 2
    assert not outcome.phone_changed
    assert outcome.action_evidence_ref == f"tests/{'a' * 64}.romverse"
    assert next(
        item for item in second.candidates if item.source_id == candidate.source_id
    ).confirmed_working


def test_outcome_candidate_must_belong_to_the_exact_persisted_fingerprint(tmp_path):
    service = evidenced_service(tmp_path)
    adb_fingerprint = ErrorFingerprint.create("ADB device offline", category="adb")
    adb_receipt = service.lookup(adb_fingerprint)
    adb_candidate = next(
        item for item in adb_receipt.candidates if item.local_action_id == "refresh-adb-evidence"
    )
    avb_fingerprint = ErrorFingerprint.create("AVB vbmeta mismatch", category="avb")
    service.lookup(avb_fingerprint)

    with pytest.raises(ValueError, match="not bound to this persisted error fingerprint"):
        service.record_verified_outcome(
            avb_fingerprint,
            adb_candidate,
            action_evidence(adb_candidate.local_action_id, "9" * 64),
            "A successful action cannot be attached to a different error fingerprint.",
        )


def test_tampered_verified_outcome_does_not_promote_candidate(tmp_path):
    fingerprint = ErrorFingerprint.create("payload.bin extraction failed", category="source")
    service = evidenced_service(tmp_path)
    first = service.lookup(fingerprint)
    candidate = next(
        item for item in first.candidates if item.local_action_id == "inspect-payload-source"
    )
    outcome = service.record_verified_outcome(
        fingerprint,
        candidate,
        action_evidence(candidate.local_action_id, "b" * 64),
        "Source-bound payload inspection succeeded.",
    )
    path = next((service.outcomes_root / fingerprint.fingerprint_id).glob("*.romverse"))
    payload = json.loads(path.read_text())
    payload["verification_summary"] = "tampered"
    path.write_text(json.dumps(payload))

    second = service.lookup(fingerprint)

    assert outcome.success
    assert not next(
        item for item in second.candidates if item.source_id == candidate.source_id
    ).confirmed_working


def test_cached_confirmation_is_rejected_when_matching_outcome_becomes_invalid(tmp_path):
    fingerprint = ErrorFingerprint.create("payload.bin extraction failed", category="source")
    service = evidenced_service(tmp_path)
    first = service.lookup(fingerprint)
    candidate = next(
        item for item in first.candidates if item.local_action_id == "inspect-payload-source"
    )
    service.record_verified_outcome(
        fingerprint,
        candidate,
        action_evidence(candidate.local_action_id, "c" * 64),
        "Source-bound payload inspection succeeded.",
    )
    confirmed = service.lookup(fingerprint)
    assert next(
        item for item in confirmed.candidates if item.source_id == candidate.source_id
    ).confirmed_working

    outcome_path = next((service.outcomes_root / fingerprint.fingerprint_id).glob("*.romverse"))
    outcome_path.write_text('{"format":"damaged"}', encoding="utf-8")

    assert service.load(fingerprint) is None


def test_legacy_digest_only_outcome_cannot_promote_a_fix(tmp_path):
    fingerprint = ErrorFingerprint.create("payload.bin extraction failed", category="source")
    service = OnlineRemediationService(tmp_path)
    receipt = service.lookup(fingerprint)
    candidate = next(
        item for item in receipt.candidates if item.local_action_id == "inspect-payload-source"
    )
    unsigned = {
        "schema_version": 1,
        "outcome_id": "1" * 32,
        "created_at": datetime.now(UTC).isoformat(),
        "fingerprint_id": fingerprint.fingerprint_id,
        "source_id": candidate.source_id,
        "source_url": candidate.url,
        "local_action_id": candidate.local_action_id,
        "action_receipt_digest": "2" * 64,
        "verification_summary": "Legacy digest-only claim.",
        "success": True,
        "phone_changed": False,
    }
    digest = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    root = service.outcomes_root / fingerprint.fingerprint_id
    root.mkdir(parents=True)
    (root / "legacy.romverse").write_text(
        json.dumps(
            {
                "format": "romverse.verified-fix-outcome",
                **unsigned,
                "outcome_digest": digest,
            }
        ),
        encoding="utf-8",
    )

    refreshed = service.lookup(fingerprint)

    assert not next(
        item for item in refreshed.candidates if item.source_id == candidate.source_id
    ).confirmed_working


def test_connected_service_can_exclude_community_research(tmp_path):
    official_only = OnlineRemediationService.connected(
        tmp_path,
        include_community=False,
    )
    community_enabled = OnlineRemediationService.connected(
        tmp_path,
        include_community=True,
    )

    assert tuple(type(provider) for provider in official_only.providers) == (
        OfficialCatalogProvider,
    )
    assert any(
        isinstance(provider, RedditSearchProvider) for provider in community_enabled.providers
    )


def test_receipt_explains_freshness_scope_corroboration_and_confidence(tmp_path):
    published = datetime.now(UTC) - timedelta(days=12)
    fingerprint = ErrorFingerprint.create(
        "payload.bin extraction failed",
        category="source",
        model="2509FPN0BC",
        codename="popsicle",
        build_id="OS4.0.0.23.XPBCNXM",
    )

    class Provider:
        def search(self, _fingerprint):
            common = {
                "title": "2509FPN0BC popsicle payload repair",
                "summary": "Verified against OS4.0.0.23.XPBCNXM payload.bin.",
                "exact_tokens": (),
                "corroboration_key": "payload-repair",
                "confidence": 60,
                "published_at": published.isoformat(),
            }
            return (
                OnlineFixCandidate(
                    "official.payload",
                    SourceAuthority.OFFICIAL,
                    url="https://source.android.com/docs/core/ota/ab",
                    **common,
                ),
                OnlineFixCandidate(
                    "community.payload",
                    SourceAuthority.COMMUNITY,
                    url="https://www.reddit.com/r/android/comments/example/payload/",
                    **common,
                ),
            )

    receipt = OnlineRemediationService(tmp_path, (Provider(),)).lookup(fingerprint)
    candidate = receipt.candidates[0]

    assert receipt.schema_version == 2
    assert candidate.freshness is EvidenceFreshness.CURRENT
    assert candidate.corroboration_count == 2
    assert set(candidate.corroborating_authorities) == {
        SourceAuthority.OFFICIAL,
        SourceAuthority.COMMUNITY,
    }
    assert candidate.scope_match == "exact build, exact device"
    assert "freshness current" in candidate.confidence_reason
    assert "2 independent source(s)" in candidate.confidence_reason
    assert candidate.retrieved_at == receipt.created_at
    assert OnlineRemediationService(tmp_path).load(fingerprint) == receipt


def test_stale_community_evidence_is_labelled_and_confidence_is_reduced(tmp_path):
    payload = {
        "data": {
            "children": [
                {
                    "data": {
                        "id": "old",
                        "title": "2509FPN0BC popsicle payload extraction fix",
                        "selftext": "Worked for OS4.0.0.23.XPBCNXM.",
                        "permalink": "/r/AndroidQuestions/comments/old/example/",
                        "created_utc": (datetime.now(UTC) - timedelta(days=900)).timestamp(),
                    }
                }
            ]
        }
    }
    provider = RedditSearchProvider(lambda _url, _headers, _maximum: json.dumps(payload).encode())
    fingerprint = ErrorFingerprint.create(
        "payload.bin extraction failed",
        model="2509FPN0BC",
        codename="popsicle",
        build_id="OS4.0.0.23.XPBCNXM",
    )

    candidate = OnlineRemediationService(tmp_path, (provider,)).lookup(fingerprint).candidates[0]

    assert candidate.freshness is EvidenceFreshness.STALE
    assert candidate.confidence == 38
    assert not candidate.confirmed_working


def test_schema_one_receipt_remains_readable_without_claiming_new_evidence(tmp_path):
    fingerprint = ErrorFingerprint.create("payload.bin extraction failed", category="source")
    service = evidenced_service(tmp_path)
    service.lookup(fingerprint)
    path = service.cache_root / f"{fingerprint.fingerprint_id}.romverse"
    payload = json.loads(path.read_text())
    payload["schema_version"] = 1
    new_fields = {
        "retrieved_at",
        "published_at",
        "freshness",
        "corroboration_count",
        "corroborating_authorities",
        "scope_match",
        "confidence_reason",
    }
    for candidate in payload["candidates"]:
        for key in new_fields:
            candidate.pop(key, None)
    expected = {
        key: payload[key]
        for key in (
            "schema_version",
            "receipt_id",
            "created_at",
            "fingerprint",
            "candidates",
            "diagnosis",
            "cache_path",
            "execution_authority",
        )
    }
    payload["receipt_digest"] = hashlib.sha256(
        json.dumps(expected, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    path.write_text(json.dumps(payload))

    loaded = service.load(fingerprint)

    assert loaded is not None
    assert loaded.schema_version == 1
    assert loaded.candidates[0].freshness is EvidenceFreshness.UNCONFIRMED
    assert loaded.candidates[0].scope_match == "unconfirmed"


def test_tampered_v2_evidence_assessment_invalidates_the_whole_receipt(tmp_path):
    fingerprint = ErrorFingerprint.create(
        "avbtool failed while parsing vbmeta",
        category="avb",
    )
    service = OnlineRemediationService(tmp_path)
    service.lookup(fingerprint)
    path = service.cache_root / f"{fingerprint.fingerprint_id}.romverse"
    payload = json.loads(path.read_text())
    payload["candidates"][0]["scope_match"] = "exact device and build"
    path.write_text(json.dumps(payload))

    assert service.load(fingerprint) is None


def test_online_receipt_rejects_oversized_symlink_and_extra_field_payloads(tmp_path):
    fingerprint = ErrorFingerprint.create("payload.bin extraction failed", category="source")
    service = OnlineRemediationService(tmp_path)
    service.lookup(fingerprint)
    path = service.cache_root / f"{fingerprint.fingerprint_id}.romverse"

    path.write_bytes(b"{" + b" " * service.MAX_RECEIPT_BYTES + b"}")
    assert service.load(fingerprint) is None

    outside = tmp_path / "outside.json"
    outside.write_text('{"private":"untouched"}', encoding="utf-8")
    path.unlink()
    path.symlink_to(outside)
    assert service.load(fingerprint) is None
    with pytest.raises(LocalStoreError, match="regular file"):
        service.lookup(fingerprint)
    assert outside.read_text(encoding="utf-8") == '{"private":"untouched"}'

    path.unlink()
    service.lookup(fingerprint)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["unexpected"] = "not part of the signed shape"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert service.load(fingerprint) is None


def test_online_receipt_and_verified_outcome_are_private_files(tmp_path):
    fingerprint = ErrorFingerprint.create("payload.bin extraction failed", category="source")
    service = evidenced_service(tmp_path)
    receipt = service.lookup(fingerprint)
    candidate = next(
        item for item in receipt.candidates if item.local_action_id == "inspect-payload-source"
    )
    service.record_verified_outcome(
        fingerprint,
        candidate,
        action_evidence(candidate.local_action_id, "d" * 64),
        "Source-bound payload inspection succeeded.",
    )
    receipt_path = service.cache_root / f"{fingerprint.fingerprint_id}.romverse"
    outcome_path = next((service.outcomes_root / fingerprint.fingerprint_id).glob("*.romverse"))

    assert stat.S_IMODE(receipt_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(outcome_path.stat().st_mode) == 0o600


def test_verified_outcome_loader_ignores_symlinks_oversized_files_and_unsafe_root(tmp_path):
    fingerprint = ErrorFingerprint.create("payload.bin extraction failed", category="source")
    service = evidenced_service(tmp_path)
    first = service.lookup(fingerprint)
    candidate = next(
        item for item in first.candidates if item.local_action_id == "inspect-payload-source"
    )
    service.record_verified_outcome(
        fingerprint,
        candidate,
        action_evidence(candidate.local_action_id, "e" * 64),
        "Source-bound payload inspection succeeded.",
    )
    root = service.outcomes_root / fingerprint.fingerprint_id
    outcome_path = next(root.glob("*.romverse"))
    outside = tmp_path / "outside-outcome.romverse"
    outside.write_text(outcome_path.read_text(encoding="utf-8"), encoding="utf-8")
    outcome_path.unlink()
    outcome_path.symlink_to(outside)
    oversized = root / "oversized.romverse"
    oversized.write_bytes(b"{" + b" " * service.MAX_OUTCOME_BYTES + b"}")

    refreshed = service.lookup(fingerprint)
    assert not next(
        item for item in refreshed.candidates if item.source_id == candidate.source_id
    ).confirmed_working

    for child in tuple(root.iterdir()):
        child.unlink()
    root.rmdir()
    root.symlink_to(tmp_path, target_is_directory=True)
    refreshed = service.lookup(fingerprint)
    assert not next(
        item for item in refreshed.candidates if item.source_id == candidate.source_id
    ).confirmed_working
