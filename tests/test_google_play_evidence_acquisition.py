from __future__ import annotations

import csv
import io
import json
import os
from datetime import UTC, datetime, timedelta

import pytest

from romverse.knowledge.google_play_acquisition import (
    GOOGLE_PLAY_CATALOG_URL,
    AcquisitionOutcome,
    CatalogAcquisitionError,
    CatalogRequest,
    CatalogResponse,
    GooglePlayEvidenceAcquirer,
)
from romverse.knowledge.online_evidence import EvidenceConsumer

NOW = datetime(2026, 9, 8, 2, 0, tzinfo=UTC)


def _payload(*rows: tuple[str, str, str, str]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(GooglePlayEvidenceAcquirer.HEADER)
    writer.writerows(rows)
    return output.getvalue().encode("utf-16")


class FixtureTransport:
    def __init__(self, response: CatalogResponse | Exception) -> None:
        self.response = response
        self.requests: list[CatalogRequest] = []

    def fetch(self, request: CatalogRequest) -> CatalogResponse:
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _response(
    payload: bytes,
    *,
    status: int = 200,
    url: str = GOOGLE_PLAY_CATALOG_URL,
    headers: dict[str, str] | None = None,
) -> CatalogResponse:
    return CatalogResponse(
        status,
        url,
        headers
        or {
            "Content-Type": "text/csv; charset=utf-16",
            "Content-Length": str(len(payload)),
            "ETag": '"fixture-v1"',
            "Last-Modified": "Tue, 08 Sep 2026 00:00:00 GMT",
        },
        payload,
    )


def _acquirer(tmp_path, response: CatalogResponse | Exception):
    transport = FixtureTransport(response)
    return GooglePlayEvidenceAcquirer(tmp_path, transport=transport), transport


def test_exact_lookup_retains_only_identity_claims_receipt_and_digest(tmp_path) -> None:
    payload = _payload(
        ("Google", "Pixel 6", "oriole", "Pixel 6"),
        ("Example", "Private Other", "other", "OTHER-1"),
    )
    acquirer, transport = _acquirer(tmp_path, _response(payload))

    receipt = acquirer.acquire("Google", "Pixel 6", "oriole", now=NOW)

    assert receipt.outcome is AcquisitionOutcome.SUCCESS
    assert receipt.source_url == GOOGLE_PLAY_CATALOG_URL
    assert receipt.content_bytes == len(payload)
    assert receipt.parsed_row_count == 2
    assert len(receipt.matched_claim_ids) == 4
    assert receipt.retained_claim_ids == receipt.matched_claim_ids
    assert receipt.parser_id == "romverse.google-play-supported-devices"
    assert receipt.raw_response_retained is False
    assert receipt.compatibility_hint == "UNCONFIRMED"
    assert receipt.execution_authority == "none"
    assert not receipt.phone_action_allowed
    assert not receipt.guardian_approval
    assert not receipt.bootloader_relock_allowed
    archive = acquirer.evidence.load()
    assert len(archive.claims) == 4
    assert {claim.structured_value for claim in archive.claims} == {
        "Google",
        "Pixel 6",
        "oriole",
    }
    assert "Private Other" not in json.dumps([claim.structured_value for claim in archive.claims])
    assert not any(path.suffix == ".csv" for path in tmp_path.rglob("*"))
    request = transport.requests[0]
    headers = dict(request.headers)
    assert request.url == GOOGLE_PLAY_CATALOG_URL
    assert headers["Accept-Encoding"] == "identity"
    assert "Authorization" not in headers
    assert "Cookie" not in headers
    assert request.connect_timeout_seconds == 8.0
    assert request.read_timeout_seconds == 12.0
    assert request.overall_timeout_seconds == 30.0
    assert request.maximum_bytes == 16 * 1024 * 1024
    if os.name != "nt":
        assert (
            acquirer.receipts.path_for(receipt.lookup.lookup_digest).stat().st_mode & 0o777 == 0o600
        )


def test_authorized_xiaomi_popsicle_lookup_retains_only_exact_identity_evidence(tmp_path) -> None:
    acquirer, _transport = _acquirer(
        tmp_path,
        _response(
            _payload(
                ("Xiaomi", "Xiaomi 17 Pro Max", "popsicle", "2509FPN0BC"),
                ("Xiaomi", "Adjacent device", "pudding", "2509FPN0CC"),
            )
        ),
    )

    receipt = acquirer.acquire("Xiaomi", "2509FPN0BC", "popsicle", now=NOW)

    assert receipt.outcome is AcquisitionOutcome.SUCCESS
    archive = acquirer.evidence.load()
    assert {claim.claim_key for claim in archive.claims} == {
        "device.identity.manufacturer",
        "device.identity.marketing-name",
        "device.identity.model",
        "device.identity.codename",
    }
    assert {claim.structured_value for claim in archive.claims} == {
        "Xiaomi",
        "Xiaomi 17 Pro Max",
        "2509FPN0BC",
        "popsicle",
    }
    assert receipt.compatibility_hint == "UNCONFIRMED"
    assert receipt.execution_authority == "none"
    assert not receipt.phone_action_allowed
    assert not receipt.guardian_approval
    assert not receipt.bootloader_relock_allowed
    assert not receipt.raw_response_retained


def test_request_contract_rejects_cookie_auth_alternate_url_and_unbounded_timeouts() -> None:
    base = {
        "url": GOOGLE_PLAY_CATALOG_URL,
        "headers": (
            ("Accept", "text/csv"),
            ("Accept-Encoding", "identity"),
            ("User-Agent", GooglePlayEvidenceAcquirer.USER_AGENT),
        ),
        "connect_timeout_seconds": 8.0,
        "read_timeout_seconds": 12.0,
        "overall_timeout_seconds": 30.0,
        "maximum_bytes": 16 * 1024 * 1024,
    }
    for changes in (
        {"url": "https://example.com/catalog.csv"},
        {"headers": (*base["headers"], ("Cookie", "session=private"))},
        {"headers": (*base["headers"], ("Authorization", "Bearer private"))},
        {"overall_timeout_seconds": 600.0},
    ):
        with pytest.raises(CatalogAcquisitionError, match="fixed transport"):
            CatalogRequest(**{**base, **changes})


def test_existing_read_only_projections_remain_unconfirmed_and_authority_free(tmp_path) -> None:
    acquirer, _transport = _acquirer(
        tmp_path,
        _response(_payload(("Google", "Pixel 6", "oriole", "Pixel 6"))),
    )
    receipt = acquirer.acquire("Google", "Pixel 6", "oriole", now=NOW)

    projections = acquirer.projections(receipt)

    assert tuple(item.consumer for item in projections) == (
        EvidenceConsumer.DEVICE_DNA,
        EvidenceConsumer.COMPATIBILITY_MATRIX,
        EvidenceConsumer.KNOWLEDGE_ARCHIVES,
    )
    assert all(item.compatibility_hint == "EVIDENCE_AVAILABLE" for item in projections)
    assert all(item.execution_authority == "none" for item in projections)
    assert all(not item.phone_action_allowed for item in projections)
    assert all(not item.guardian_approval for item in projections)
    assert all(not item.bootloader_relock_allowed for item in projections)


def test_no_match_and_ambiguous_match_remain_unconfirmed_without_claims(tmp_path) -> None:
    no_match, _transport = _acquirer(
        tmp_path / "none",
        _response(_payload(("Google", "Pixel 7", "panther", "Pixel 7"))),
    )
    absent = no_match.acquire("Google", "Pixel 6", "oriole", now=NOW)

    ambiguous, _transport = _acquirer(
        tmp_path / "ambiguous",
        _response(
            _payload(
                ("Google", "Pixel 6", "oriole", "Pixel 6"),
                ("Google", "Pixel 6 Carrier", "oriole", "Pixel 6"),
            )
        ),
    )
    multiple = ambiguous.acquire("Google", "Pixel 6", "oriole", now=NOW)

    assert absent.outcome is AcquisitionOutcome.NO_EXACT_MATCH
    assert multiple.outcome is AcquisitionOutcome.NO_EXACT_MATCH
    assert "ambiguous" in multiple.reason
    assert not absent.retained_claim_ids
    assert not multiple.retained_claim_ids
    assert not (
        tmp_path / "none" / "knowledge" / "online-device-evidence" / "claims.romverse"
    ).exists()


def test_http_failure_and_timeout_produce_durable_zero_authority_receipts(tmp_path) -> None:
    status_client, _transport = _acquirer(tmp_path / "status", _response(b"failure", status=503))
    timeout_client, _transport = _acquirer(tmp_path / "timeout", TimeoutError("socket timed out"))

    failure = status_client.acquire("Google", "Pixel 6", "oriole", now=NOW)
    timeout = timeout_client.acquire("Google", "Pixel 6", "oriole", now=NOW)

    assert failure.outcome is AcquisitionOutcome.HTTP_FAILURE
    assert failure.http_status == 503
    assert timeout.outcome is AcquisitionOutcome.HTTP_FAILURE
    assert "TimeoutError" in timeout.reason
    assert status_client.receipts.load(failure.lookup.lookup_digest) == failure
    assert timeout_client.receipts.load(timeout.lookup.lookup_digest) == timeout
    assert not failure.phone_action_allowed and not timeout.phone_action_allowed


@pytest.mark.parametrize(
    ("response", "reason"),
    (
        (
            _response(
                _payload(("Google", "Pixel 6", "oriole", "Pixel 6")),
                url="https://example.com/redirect.csv",
            ),
            "validation",
        ),
        (
            _response(
                _payload(("Google", "Pixel 6", "oriole", "Pixel 6")),
                headers={"Content-Type": "text/html"},
            ),
            "validation",
        ),
        (
            _response(
                _payload(("Google", "Pixel 6", "oriole", "Pixel 6")),
                headers={"Content-Type": "text/csv", "Content-Encoding": "gzip"},
            ),
            "validation",
        ),
        (
            _response(
                _payload(("Google", "Pixel 6", "oriole", "Pixel 6")),
                headers={"Content-Type": "text/csv", "Content-Length": "999999"},
            ),
            "validation",
        ),
    ),
)
def test_redirect_unexpected_content_compression_and_truncation_are_rejected(
    tmp_path, response, reason
) -> None:
    acquirer, _transport = _acquirer(tmp_path, response)

    receipt = acquirer.acquire("Google", "Pixel 6", "oriole", now=NOW)

    assert receipt.outcome is AcquisitionOutcome.VALIDATION_FAILURE
    assert reason in receipt.reason.casefold()
    assert not receipt.matched_claim_ids


@pytest.mark.parametrize(
    "bad_row",
    (
        ("Google", '=HYPERLINK("bad")', "oriole", "Pixel 6"),
        ("Google", "Pixel\x00 6", "oriole", "Pixel 6"),
        ("Google", "Pixel 6", "oriole", "Pixel 6", "extra"),
    ),
)
def test_formula_control_characters_and_malformed_rows_are_rejected(tmp_path, bad_row) -> None:
    acquirer, _transport = _acquirer(tmp_path, _response(_payload(bad_row)))

    receipt = acquirer.acquire("Google", "Pixel 6", "oriole", now=NOW)

    assert receipt.outcome is AcquisitionOutcome.VALIDATION_FAILURE
    assert not receipt.retained_claim_ids


def test_blank_optional_catalog_cells_do_not_become_matching_claims(tmp_path) -> None:
    acquirer, _transport = _acquirer(
        tmp_path,
        _response(
            _payload(
                ("", "", "unrelated", ""),
                ("Google", "Pixel 6", "oriole", "Pixel 6"),
            )
        ),
    )

    receipt = acquirer.acquire("Google", "Pixel 6", "oriole", now=NOW)

    assert receipt.outcome is AcquisitionOutcome.SUCCESS
    assert len(receipt.matched_claim_ids) == 4


def test_duplicate_and_oversized_rows_are_rejected(tmp_path, monkeypatch) -> None:
    row = ("Google", "Pixel 6", "oriole", "Pixel 6")
    duplicate, _transport = _acquirer(tmp_path / "duplicate", _response(_payload(row, row)))
    duplicated = duplicate.acquire("Google", "Pixel 6", "oriole", now=NOW)
    assert duplicated.outcome is AcquisitionOutcome.VALIDATION_FAILURE

    monkeypatch.setattr(GooglePlayEvidenceAcquirer, "MAXIMUM_ROWS", 1)
    oversized, _transport = _acquirer(
        tmp_path / "rows",
        _response(_payload(row, ("Google", "Pixel 7", "panther", "Pixel 7"))),
    )
    too_many = oversized.acquire("Google", "Pixel 6", "oriole", now=NOW)
    assert too_many.outcome is AcquisitionOutcome.VALIDATION_FAILURE


def test_duplicate_rows_outside_exact_query_are_never_promoted(tmp_path) -> None:
    target = ("Google", "Pixel 6", "oriole", "Pixel 6")
    unrelated = ("Example", "Example One", "example", "EX-1")
    acquirer, _transport = _acquirer(
        tmp_path,
        _response(_payload(unrelated, unrelated, target)),
    )

    receipt = acquirer.acquire("Google", "Pixel 6", "oriole", now=NOW)

    assert receipt.outcome is AcquisitionOutcome.SUCCESS
    assert len(receipt.matched_claim_ids) == 4


def test_oversized_body_is_rejected_without_claim_formation(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(GooglePlayEvidenceAcquirer, "MAXIMUM_BYTES", 64)
    payload = _payload(("Google", "Pixel 6", "oriole", "Pixel 6"))
    acquirer, _transport = _acquirer(
        tmp_path,
        _response(payload, headers={"Content-Type": "text/csv"}),
    )

    receipt = acquirer.acquire("Google", "Pixel 6", "oriole", now=NOW)

    assert receipt.outcome is AcquisitionOutcome.VALIDATION_FAILURE
    assert not receipt.retained_claim_ids


def test_privacy_unsafe_lookup_is_rejected_before_transport_and_not_retained(tmp_path) -> None:
    transport = FixtureTransport(AssertionError("transport must not run"))
    acquirer = GooglePlayEvidenceAcquirer(tmp_path, transport=transport)

    receipt = acquirer.acquire(
        "Google IMEI=123456789012345",
        "user@example.com",
        "/home/alice/private",
        now=NOW,
    )

    assert receipt.outcome is AcquisitionOutcome.VALIDATION_FAILURE
    assert receipt.lookup.manufacturer == ""
    assert receipt.lookup.model == ""
    assert receipt.lookup.codename == ""
    assert not transport.requests
    serialized = json.dumps(asdict_for_test(receipt))
    assert "123456789012345" not in serialized
    assert "user@example.com" not in serialized
    assert "/home/alice" not in serialized


def test_conditional_cache_not_modified_retains_only_prior_claim_references(tmp_path) -> None:
    payload = _payload(("Google", "Pixel 6", "oriole", "Pixel 6"))
    transport = FixtureTransport(_response(payload))
    acquirer = GooglePlayEvidenceAcquirer(tmp_path, transport=transport)
    first = acquirer.acquire("Google", "Pixel 6", "oriole", now=NOW)
    transport.response = _response(
        b"",
        status=304,
        headers={"ETag": '"fixture-v1"', "Last-Modified": "Tue, 08 Sep 2026 00:00:00 GMT"},
    )

    second = acquirer.acquire("Google", "Pixel 6", "oriole", now=NOW + timedelta(seconds=3))

    assert second.outcome is AcquisitionOutcome.CACHE_NOT_MODIFIED
    assert second.content_digest == first.content_digest
    assert second.retained_claim_ids == first.retained_claim_ids
    request_headers = dict(transport.requests[-1].headers)
    assert request_headers["If-None-Match"] == '"fixture-v1"'
    assert request_headers["If-Modified-Since"] == "Tue, 08 Sep 2026 00:00:00 GMT"
    assert len(acquirer.projections(second)) == 3


def test_cache_not_modified_preserves_a_prior_no_match_without_inventing_claims(tmp_path) -> None:
    transport = FixtureTransport(_response(_payload(("Google", "Pixel 7", "panther", "Pixel 7"))))
    acquirer = GooglePlayEvidenceAcquirer(tmp_path, transport=transport)
    first = acquirer.acquire("Google", "Pixel 6", "oriole", now=NOW)
    transport.response = _response(b"", status=304, headers={"ETag": '"fixture-v1"'})

    second = acquirer.acquire("Google", "Pixel 6", "oriole", now=NOW + timedelta(seconds=3))

    assert first.outcome is AcquisitionOutcome.NO_EXACT_MATCH
    assert second.outcome is AcquisitionOutcome.CACHE_NOT_MODIFIED
    assert not second.retained_claim_ids
    assert all(item.investigation_required for item in acquirer.projections(second))


def test_minimum_spacing_blocks_repeat_without_second_network_request(tmp_path) -> None:
    transport = FixtureTransport(_response(_payload(("Google", "Pixel 6", "oriole", "Pixel 6"))))
    acquirer = GooglePlayEvidenceAcquirer(tmp_path, transport=transport)
    first = acquirer.acquire("Google", "Pixel 6", "oriole", now=NOW)
    second = acquirer.acquire("Google", "Pixel 6", "oriole", now=NOW + timedelta(seconds=1))

    assert first.outcome is AcquisitionOutcome.SUCCESS
    assert second.outcome is AcquisitionOutcome.VALIDATION_FAILURE
    assert "spacing" in second.reason
    assert len(transport.requests) == 1
    assert second.retained_claim_ids == first.retained_claim_ids


def test_receipt_tampering_and_symlink_are_rejected(tmp_path) -> None:
    acquirer, _transport = _acquirer(
        tmp_path,
        _response(_payload(("Google", "Pixel 6", "oriole", "Pixel 6"))),
    )
    receipt = acquirer.acquire("Google", "Pixel 6", "oriole", now=NOW)
    path = acquirer.receipts.path_for(receipt.lookup.lookup_digest)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["guardian_approval"] = True
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(CatalogAcquisitionError):
        acquirer.receipts.load(receipt.lookup.lookup_digest)

    if os.name != "nt":
        path.unlink()
        outside = tmp_path / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        path.symlink_to(outside)
        with pytest.raises(CatalogAcquisitionError):
            acquirer.receipts.load(receipt.lookup.lookup_digest)


def asdict_for_test(receipt):
    # Kept local so production exposes no generic serialization helper beyond its sealed receipt.
    from dataclasses import asdict

    return asdict(receipt)
