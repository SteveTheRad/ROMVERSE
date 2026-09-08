from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta

import pytest

from romverse.knowledge.online_evidence import (
    EvidenceConsumer,
    EvidenceFreshness,
    EvidenceState,
)
from romverse.knowledge.pixel_factory_index import (
    PIXEL_FACTORY_INDEX_URL,
    FactoryIndexOutcome,
    FactoryIndexRequest,
    FactoryIndexResponse,
    PixelFactoryIndexAcquirer,
    PixelFactoryIndexError,
)

NOW = datetime(2026, 9, 8, 4, 0, tzinfo=UTC)
HASH_A = "a" * 64
HASH_B = "b" * 64
URL_A = "https://dl.google.com/dl/android/aosp/oriole-bp2a-factory-a1.zip"
URL_B = "https://dl.google.com/dl/android/aosp/oriole-bp3a-factory-b2.zip"


def _row(
    release: str = "16.0.0 (BP2A.250805.005, Aug 2026)",
    image_url: str = URL_A,
    sha256: str = HASH_A,
    *,
    extra_download_link: str = "",
) -> str:
    extra = f'<a href="{extra_download_link}">Other</a>' if extra_download_link else ""
    return f"""
      <tr>
        <td>{release}</td>
        <td><button>Flash</button></td>
        <td><a href="{image_url}">Link</a>{extra}</td>
        <td>{sha256}</td>
      </tr>"""


def _html(
    *,
    target_heading: str = '"oriole" for Pixel 6',
    rows: str | None = None,
    headers: str = "<th>Version</th><th>Flash</th><th>Download</th><th>SHA-256 Checksum</th>",
    canonical: str = PIXEL_FACTORY_INDEX_URL,
    language: str = "en",
    modified: str = "2026-09-01T00:00:00Z",
    malicious: str = "",
) -> bytes:
    rows = _row() if rows is None else rows
    return f"""<!doctype html>
<html lang="{language}">
<head>
  <link rel="canonical" href="{canonical}">
  <meta itemprop="dateModified" content="{modified}">
  <title>Factory Images for Nexus and Pixel Devices</title>
  <script>fastboot flashing lock PRIVATE-SCRIPT</script>
</head>
<body>
  <nav>Download navigation</nav>
  <main>
    <h1>Factory Images for Nexus and Pixel Devices</h1>
    <form><input name="terms"><button>I agree</button></form>
    <p>Accept terms before downloading. Relock the bootloader after flashing.</p>
    <h2>{target_heading}</h2>
    <table><tr>{headers}</tr>{rows}</table>
    {malicious}
    <h2>"raven" for Pixel 6 Pro</h2>
    <table><tr>{headers}</tr>{_row(image_url=URL_B, sha256=HASH_B)}</table>
  </main>
</body>
</html>""".encode()


class FixtureTransport:
    def __init__(self, response: FactoryIndexResponse | Exception) -> None:
        self.response = response
        self.requests: list[FactoryIndexRequest] = []

    def fetch(self, request: FactoryIndexRequest) -> FactoryIndexResponse:
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _response(
    body: bytes,
    *,
    status: int = 200,
    url: str = PIXEL_FACTORY_INDEX_URL,
    headers: dict[str, str] | None = None,
) -> FactoryIndexResponse:
    return FactoryIndexResponse(
        status,
        url,
        headers
        or {
            "Content-Type": "text/html; charset=utf-8",
            "Content-Length": str(len(body)),
            "ETag": '"factory-v1"',
            "Last-Modified": "Tue, 01 Sep 2026 00:00:00 GMT",
        },
        body,
    )


def _acquirer(tmp_path, response):
    transport = FixtureTransport(response)
    return PixelFactoryIndexAcquirer(tmp_path, transport=transport), transport


def test_exact_pixel_6_rows_become_metadata_only_claims(tmp_path) -> None:
    rows = _row() + _row("16.0.0 (BP3A.250901.001, Sep 2026, Verizon)", URL_B, HASH_B)
    body = _html(rows=rows)
    acquirer, transport = _acquirer(tmp_path, _response(body))

    receipt = acquirer.acquire(now=NOW)

    assert receipt.outcome is FactoryIndexOutcome.SUCCESS
    assert receipt.parsed_release_count == 2
    assert receipt.matched_claim_ids == receipt.retained_claim_ids
    assert receipt.evidence_state == "officially-documented"
    assert receipt.compatibility_hint == "UNCONFIRMED"
    assert receipt.execution_authority == "none"
    assert not receipt.phone_action_allowed
    assert not receipt.guardian_approval
    assert not receipt.bootloader_relock_allowed
    assert not receipt.terms_accepted
    assert not receipt.binary_downloaded
    assert not receipt.raw_response_retained
    claims = acquirer.evidence.load().claims
    assert len(claims) == 2
    assert all(claim.state is EvidenceState.OFFICIALLY_DOCUMENTED for claim in claims)
    metadata = [json.loads(claim.structured_value) for claim in claims]
    assert {item["build_id"] for item in metadata} == {
        "BP2A.250805.005",
        "BP3A.250901.001",
    }
    assert {item["carrier_region_scope"] for item in metadata} == {"", "Verizon"}
    assert {item["image_url"] for item in metadata} == {URL_A, URL_B}
    assert all(item["sha256"] in {HASH_A, HASH_B} for item in metadata)
    retained = json.dumps(metadata)
    assert "fastboot" not in retained.casefold()
    assert "relock" not in retained.casefold()
    assert "terms" not in retained.casefold()
    assert "PRIVATE-SCRIPT" not in retained
    assert not any(path.suffix in {".html", ".zip"} for path in tmp_path.rglob("*"))
    request = transport.requests[0]
    assert request.url == PIXEL_FACTORY_INDEX_URL
    assert dict(request.headers) == {
        "Accept": "text/html",
        "Accept-Encoding": "identity",
        "User-Agent": PixelFactoryIndexAcquirer.USER_AGENT,
    }
    if os.name != "nt":
        assert acquirer.receipts.path.stat().st_mode & 0o777 == 0o600


def test_projections_are_read_only_and_compatibility_stays_unconfirmed(tmp_path) -> None:
    acquirer, _transport = _acquirer(tmp_path, _response(_html()))
    receipt = acquirer.acquire(now=NOW)

    projections = acquirer.projections(receipt)

    assert tuple(item.consumer for item in projections) == (
        EvidenceConsumer.DEVICE_DNA,
        EvidenceConsumer.COMPATIBILITY_MATRIX,
        EvidenceConsumer.PATHFINDER,
        EvidenceConsumer.NEXUS,
        EvidenceConsumer.FORESIGHT,
        EvidenceConsumer.KNOWLEDGE_ARCHIVES,
    )
    assert all(item.compatibility_hint == "UNCONFIRMED" for item in projections)
    assert all(item.investigation_required for item in projections)
    assert all(item.execution_authority == "none" for item in projections)
    assert all(not item.phone_action_allowed for item in projections)
    assert all(not item.guardian_approval for item in projections)
    assert all(not item.bootloader_relock_allowed for item in projections)


@pytest.mark.parametrize(
    ("manufacturer", "model", "codename"),
    (
        ("Google", "Pixel 6 Pro", "raven"),
        ("Google", "Pixel 6", "raven"),
        ("user@example.com", "Pixel 6", "oriole"),
    ),
)
def test_only_approved_public_identity_can_be_queried(
    tmp_path, manufacturer, model, codename
) -> None:
    acquirer, transport = _acquirer(tmp_path, _response(_html()))

    receipt = acquirer.acquire(manufacturer, model, codename, now=NOW)

    assert receipt.outcome is FactoryIndexOutcome.VALIDATION_FAILURE
    assert not transport.requests
    assert "user@example.com" not in receipt.reason


@pytest.mark.parametrize(
    "rows",
    (
        _row() + _row(),
        _row() + _row("16.0.0 (BP2A.250805.005, Aug 2026)", URL_B, HASH_B),
        _row(sha256=""),
        _row(release="16.0.0 (BP2A.250805.005)"),
        _row(extra_download_link=URL_B),
        _row(image_url="https://evil.example/oriole.zip"),
    ),
)
def test_duplicate_ambiguous_incomplete_or_untrusted_rows_fail_closed(tmp_path, rows) -> None:
    acquirer, _transport = _acquirer(tmp_path, _response(_html(rows=rows)))

    receipt = acquirer.acquire(now=NOW)

    assert receipt.outcome is FactoryIndexOutcome.VALIDATION_FAILURE
    assert not receipt.matched_claim_ids


@pytest.mark.parametrize(
    "changes",
    (
        {"target_heading": '"oriole" for Pixel Six'},
        {"headers": "<th>Release</th><th>Download</th><th>SHA-256 Checksum</th>"},
        {"headers": "<th>Version</th><th>Download</th><th>SHA-256</th>"},
    ),
)
def test_missing_section_and_changed_layout_fail_closed(tmp_path, changes) -> None:
    acquirer, _transport = _acquirer(tmp_path, _response(_html(**changes)))
    assert acquirer.acquire(now=NOW).outcome is FactoryIndexOutcome.VALIDATION_FAILURE


@pytest.mark.parametrize(
    "response",
    (
        _response(_html(), url="https://developers.google.com/android/images?hl=fr"),
        _response(_html(language="fr")),
        _response(_html(canonical="https://developers.google.com/android/images?hl=en")),
        _response(_html(), headers={"Content-Type": "application/javascript"}),
        _response(_html(), headers={"Content-Type": "text/html", "Content-Encoding": "gzip"}),
        _response(_html(), headers={"Content-Type": "text/html", "Content-Length": "1"}),
    ),
)
def test_redirect_localization_type_compression_and_truncation_fail(tmp_path, response) -> None:
    acquirer, _transport = _acquirer(tmp_path, response)
    assert acquirer.acquire(now=NOW).outcome is FactoryIndexOutcome.VALIDATION_FAILURE


@pytest.mark.parametrize(
    "release",
    (
        "16.0.0 (BP2A.250805.005, Aug 2026, relock bootloader)",
        "16.0.0 (BP2A.250805.005, Aug 2026, adb reboot)",
        "16.0.0 (BP2A.250805.005, Aug 2026, user@example.com)",
        "16.0.0 (BP2A.250805.005, Aug 2026, " + "x" * 250 + ")",
    ),
)
def test_executable_relock_private_and_oversized_metadata_cannot_enter_claims(
    tmp_path, release
) -> None:
    acquirer, _transport = _acquirer(tmp_path, _response(_html(rows=_row(release=release))))

    receipt = acquirer.acquire(now=NOW)

    assert receipt.outcome is FactoryIndexOutcome.VALIDATION_FAILURE
    assert not receipt.retained_claim_ids
    assert "user@example.com" not in receipt.reason


def test_page_scripts_commands_relock_and_terms_are_ignored_not_retained(tmp_path) -> None:
    malicious = """
      <script>adb shell; fastboot flashing lock</script>
      <pre>flash-all.sh</pre>
      <form><button>Accept terms</button></form>
      <p>Relock the bootloader and wipe the device.</p>
    """
    acquirer, _transport = _acquirer(tmp_path, _response(_html(malicious=malicious)))

    receipt = acquirer.acquire(now=NOW)
    claims = acquirer.evidence.load().claims
    retained_claim_content = json.dumps(
        [
            {
                "structured_value": claim.structured_value,
                "supporting_excerpt": claim.supporting_excerpt,
                "diagnostic_description": claim.diagnostic_description,
                "remedy_description": claim.remedy_description,
                "expected_result": claim.expected_result,
                "rollback_recovery_route": claim.rollback_recovery_route,
            }
            for claim in claims
        ]
    ).casefold()

    assert receipt.outcome is FactoryIndexOutcome.SUCCESS
    assert all(
        token not in retained_claim_content
        for token in ("fastboot", "relock", "flash-all", "accept terms")
    )
    assert not receipt.terms_accepted
    assert not receipt.binary_downloaded


def test_oversized_page_and_excess_matching_rows_fail(tmp_path) -> None:
    oversized_body = _html(malicious="<p>" + "x" * (4 * 1024 * 1024) + "</p>")
    oversized, _transport = _acquirer(tmp_path / "oversized", _response(oversized_body))
    many_rows = "".join(
        _row(
            f"16.0.0 (BP2A.{index:06d}, Aug 2026)",
            f"https://dl.google.com/dl/android/aosp/oriole-{index}-factory-a.zip",
            f"{index:064x}",
        )
        for index in range(PixelFactoryIndexAcquirer.MAXIMUM_RELEASES + 1)
    )
    excessive, _transport = _acquirer(tmp_path / "excessive", _response(_html(rows=many_rows)))

    assert oversized.acquire(now=NOW).outcome is FactoryIndexOutcome.VALIDATION_FAILURE
    assert excessive.acquire(now=NOW).outcome is FactoryIndexOutcome.VALIDATION_FAILURE


def test_stale_page_remains_official_metadata_but_requires_investigation(tmp_path) -> None:
    acquirer, _transport = _acquirer(tmp_path, _response(_html(modified="2024-01-01T00:00:00Z")))

    receipt = acquirer.acquire(now=NOW)
    claim = acquirer.evidence.load().claims[0]

    assert receipt.outcome is FactoryIndexOutcome.SUCCESS
    assert claim.state is EvidenceState.OFFICIALLY_DOCUMENTED
    assert claim.source.freshness is EvidenceFreshness.STALE
    assert all(item.investigation_required for item in acquirer.projections(receipt))


def test_http_timeout_cache_and_request_spacing_are_durable(tmp_path) -> None:
    failed, _transport = _acquirer(tmp_path / "http", _response(b"failure", status=503))
    timed_out, _transport = _acquirer(tmp_path / "timeout", TimeoutError("timeout"))
    assert failed.acquire(now=NOW).outcome is FactoryIndexOutcome.HTTP_FAILURE
    assert timed_out.acquire(now=NOW).outcome is FactoryIndexOutcome.HTTP_FAILURE

    transport = FixtureTransport(_response(_html()))
    cached = PixelFactoryIndexAcquirer(tmp_path / "cached", transport=transport)
    first = cached.acquire(now=NOW)
    too_soon = cached.acquire(now=NOW + timedelta(seconds=1))
    transport.response = _response(b"", status=304, headers={"ETag": '"factory-v1"'})
    unchanged = cached.acquire(now=NOW + timedelta(seconds=3))

    assert first.outcome is FactoryIndexOutcome.SUCCESS
    assert too_soon.outcome is FactoryIndexOutcome.VALIDATION_FAILURE
    assert unchanged.outcome is FactoryIndexOutcome.CACHE_NOT_MODIFIED
    assert unchanged.retained_claim_ids == first.retained_claim_ids
    assert dict(transport.requests[-1].headers)["If-None-Match"] == '"factory-v1"'


def test_receipt_tampering_and_symlink_are_rejected(tmp_path) -> None:
    acquirer, _transport = _acquirer(tmp_path, _response(_html()))
    acquirer.acquire(now=NOW)
    raw = json.loads(acquirer.receipts.path.read_text(encoding="utf-8"))
    raw["terms_accepted"] = True
    acquirer.receipts.path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(PixelFactoryIndexError, match="terms acceptance|digest"):
        acquirer.receipts.load()

    if os.name != "nt":
        acquirer.receipts.path.unlink()
        outside = tmp_path / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        acquirer.receipts.path.symlink_to(outside)
        with pytest.raises(PixelFactoryIndexError):
            acquirer.receipts.load()
