from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta

import pytest

from romverse.knowledge.aosp_build_numbers import (
    AOSP_BUILD_NUMBERS_URL,
    AOSPBuildNumbersAcquirer,
    AOSPBuildNumbersError,
    AOSPBuildOutcome,
    AOSPBuildRequest,
    AOSPBuildResponse,
)
from romverse.knowledge.online_evidence import (
    EvidenceConsumer,
    EvidenceFreshness,
    EvidenceState,
)

NOW = datetime(2026, 9, 8, 5, 0, tzinfo=UTC)


def _row(
    build: str = "BP2A.250805.005",
    tag: str = "android-16.0.0_r2",
    version: str = "Android 16",
    devices: str = "Pixel 6, Pixel 6 Pro, Pixel 6a",
    patch: str = "2026-08-05",
) -> str:
    return (
        f"<tr><td>{build}</td><td>{tag}</td><td>{version}</td>"
        f"<td>{devices}</td><td>{patch}</td></tr>"
    )


def _html(
    *,
    rows: str | None = None,
    headers: str = (
        "<th>Build ID</th><th>Tag</th><th>Version</th>"
        "<th>Supported devices</th><th>Security patch level</th>"
    ),
    canonical: str = AOSP_BUILD_NUMBERS_URL,
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
  <title>Codenames, tags, and build numbers</title>
  <script>adb shell PRIVATE-SCRIPT</script>
</head>
<body><nav>Download navigation</nav><main>
  <h1>Codenames, tags, and build numbers</h1>
  <p>Run fastboot and relock instructions must not be retained.</p>
  <table><tr>{headers}</tr>{rows}</table>
  <table><tr><th>Codename</th><th>Version</th></tr><tr><td>oriole</td><td>16</td></tr></table>
  {malicious}
</main></body></html>""".encode()


class FixtureTransport:
    def __init__(self, response: AOSPBuildResponse | Exception) -> None:
        self.response = response
        self.requests: list[AOSPBuildRequest] = []

    def fetch(self, request: AOSPBuildRequest) -> AOSPBuildResponse:
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _response(
    body: bytes,
    *,
    status: int = 200,
    url: str = AOSP_BUILD_NUMBERS_URL,
    headers: dict[str, str] | None = None,
) -> AOSPBuildResponse:
    return AOSPBuildResponse(
        status,
        url,
        headers
        or {
            "Content-Type": "text/html; charset=utf-8",
            "Content-Length": str(len(body)),
            "ETag": '"aosp-v1"',
            "Last-Modified": "Tue, 01 Sep 2026 00:00:00 GMT",
        },
        body,
    )


def _acquirer(tmp_path, response):
    transport = FixtureTransport(response)
    return AOSPBuildNumbersAcquirer(tmp_path, transport=transport), transport


def test_only_explicit_pixel_6_rows_become_metadata_claims(tmp_path) -> None:
    rows = (
        _row()
        + _row(
            "BP3A.250901.001",
            "android-16.0.0_r3",
            "16.0.0",
            "Pixel 6, Pixel 7",
            "2026-09-01",
        )
        + _row(
            "BP4A.251001.001",
            "android-16.0.0_r4",
            devices="Pixel 6 Pro, Pixel 7",
            patch="2026-10-01",
        )
    )
    body = _html(rows=rows)
    acquirer, transport = _acquirer(tmp_path, _response(body))

    receipt = acquirer.acquire(now=NOW)

    assert receipt.outcome is AOSPBuildOutcome.SUCCESS
    assert receipt.parsed_matching_row_count == 2
    assert receipt.compatibility_hint == "UNCONFIRMED"
    assert not receipt.codename_mapping_inferred
    assert not receipt.package_hash_available
    assert receipt.execution_authority == "none"
    assert not receipt.phone_action_allowed
    assert not receipt.guardian_approval
    assert not receipt.bootloader_relock_allowed
    assert not receipt.raw_response_retained
    claims = acquirer.evidence.load().claims
    assert len(claims) == 2
    assert all(claim.state is EvidenceState.OFFICIALLY_DOCUMENTED for claim in claims)
    assert all(not claim.scope.codenames for claim in claims)
    metadata = [json.loads(claim.structured_value) for claim in claims]
    assert {item["build_id"] for item in metadata} == {
        "BP2A.250805.005",
        "BP3A.250901.001",
    }
    assert all("Pixel 6" in item["supported_devices"] for item in metadata)
    retained = json.dumps(metadata).casefold()
    assert all(token not in retained for token in ("oriole", "fastboot", "relock", "private"))
    assert not any(path.suffix == ".html" for path in tmp_path.rglob("*"))
    assert dict(transport.requests[0].headers) == {
        "Accept": "text/html",
        "Accept-Encoding": "identity",
        "User-Agent": AOSPBuildNumbersAcquirer.USER_AGENT,
    }
    if os.name != "nt":
        assert acquirer.receipts.path.stat().st_mode & 0o777 == 0o600


def test_read_only_projections_never_promote_compatibility(tmp_path) -> None:
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
    "rows",
    (
        _row() + _row(),
        _row() + _row(tag="android-16.0.0_r99"),
        _row(tag=""),
        _row(version=""),
        _row(devices=""),
        _row(patch=""),
    ),
)
def test_duplicate_conflicting_and_missing_required_metadata_fail_closed(tmp_path, rows) -> None:
    acquirer, _transport = _acquirer(tmp_path, _response(_html(rows=rows)))
    receipt = acquirer.acquire(now=NOW)
    assert receipt.outcome is AOSPBuildOutcome.VALIDATION_FAILURE
    assert not receipt.matched_claim_ids


@pytest.mark.parametrize(
    "headers",
    (
        "<th>Build</th><th>Tag</th><th>Version</th><th>Devices</th><th>Patch</th>",
        "<th>Build ID</th><th>Version</th><th>Supported devices</th><th>Security patch level</th>",
    ),
)
def test_changed_layout_fails_closed(tmp_path, headers) -> None:
    acquirer, _transport = _acquirer(tmp_path, _response(_html(headers=headers)))
    assert acquirer.acquire(now=NOW).outcome is AOSPBuildOutcome.VALIDATION_FAILURE


@pytest.mark.parametrize(
    "response",
    (
        _response(_html(), url=AOSP_BUILD_NUMBERS_URL + "?hl=fr"),
        _response(_html(language="fr")),
        _response(_html(canonical=AOSP_BUILD_NUMBERS_URL + "?hl=en")),
        _response(_html(), headers={"Content-Type": "application/javascript"}),
        _response(_html(), headers={"Content-Type": "text/html", "Content-Encoding": "gzip"}),
        _response(_html(), headers={"Content-Type": "text/html", "Content-Length": "1"}),
    ),
)
def test_redirect_localization_type_compression_and_truncation_fail(tmp_path, response) -> None:
    acquirer, _transport = _acquirer(tmp_path, response)
    assert acquirer.acquire(now=NOW).outcome is AOSPBuildOutcome.VALIDATION_FAILURE


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("build", "adb-shell"),
        ("tag", "android-16.0.0_r2 && sudo"),
        ("version", "fastboot 16"),
        ("devices", "Pixel 6, user@example.com"),
        ("patch", "relock"),
        ("devices", "Pixel 6, " + "x" * 510),
    ),
)
def test_executable_private_and_oversized_matching_fields_fail(tmp_path, field, value) -> None:
    values = {
        "build": "BP2A.250805.005",
        "tag": "android-16.0.0_r2",
        "version": "Android 16",
        "devices": "Pixel 6, Pixel 6 Pro",
        "patch": "2026-08-05",
    }
    values[field] = value
    acquirer, _transport = _acquirer(tmp_path, _response(_html(rows=_row(**values))))
    receipt = acquirer.acquire(now=NOW)
    assert receipt.outcome is AOSPBuildOutcome.VALIDATION_FAILURE
    assert "user@example.com" not in receipt.reason


def test_scripts_code_navigation_and_unrelated_rows_are_not_retained(tmp_path) -> None:
    malicious = """
      <script>adb shell</script><pre>fastboot flash</pre><nav>private nav</nav>
      <p>Relock instructions and downloads.</p>
    """
    acquirer, _transport = _acquirer(
        tmp_path,
        _response(_html(rows=_row() + _row(devices="Pixel 7"), malicious=malicious)),
    )
    receipt = acquirer.acquire(now=NOW)
    claims = acquirer.evidence.load().claims
    content = json.dumps([claim.structured_value for claim in claims]).casefold()
    assert receipt.outcome is AOSPBuildOutcome.SUCCESS
    assert len(claims) == 1
    assert all(token not in content for token in ("adb", "fastboot", "relock", "pixel 7"))


def test_response_and_matching_row_limits_fail_closed(tmp_path) -> None:
    oversized_body = _html(malicious="<p>" + "x" * (4 * 1024 * 1024) + "</p>")
    oversized, _transport = _acquirer(tmp_path / "oversized", _response(oversized_body))
    rows = "".join(
        _row(
            build=f"BP2A.{index:06d}",
            tag=f"android-16.0.0_r{index + 1}",
            patch="2026-08-05",
        )
        for index in range(AOSPBuildNumbersAcquirer.MAXIMUM_MATCHES + 1)
    )
    excessive, _transport = _acquirer(tmp_path / "rows", _response(_html(rows=rows)))
    assert oversized.acquire(now=NOW).outcome is AOSPBuildOutcome.VALIDATION_FAILURE
    assert excessive.acquire(now=NOW).outcome is AOSPBuildOutcome.VALIDATION_FAILURE


def test_stale_page_remains_official_and_investigable(tmp_path) -> None:
    acquirer, _transport = _acquirer(tmp_path, _response(_html(modified="2024-01-01T00:00:00Z")))
    receipt = acquirer.acquire(now=NOW)
    claim = acquirer.evidence.load().claims[0]
    assert receipt.outcome is AOSPBuildOutcome.SUCCESS
    assert claim.state is EvidenceState.OFFICIALLY_DOCUMENTED
    assert claim.source.freshness is EvidenceFreshness.STALE
    assert all(item.investigation_required for item in acquirer.projections(receipt))


def test_http_timeout_cache_and_spacing_are_durable(tmp_path) -> None:
    failed, _transport = _acquirer(tmp_path / "http", _response(b"failure", status=503))
    timed_out, _transport = _acquirer(tmp_path / "timeout", TimeoutError("timeout"))
    assert failed.acquire(now=NOW).outcome is AOSPBuildOutcome.HTTP_FAILURE
    assert timed_out.acquire(now=NOW).outcome is AOSPBuildOutcome.HTTP_FAILURE

    transport = FixtureTransport(_response(_html()))
    cached = AOSPBuildNumbersAcquirer(tmp_path / "cached", transport=transport)
    first = cached.acquire(now=NOW)
    too_soon = cached.acquire(now=NOW + timedelta(seconds=1))
    transport.response = _response(b"", status=304, headers={"ETag": '"aosp-v1"'})
    unchanged = cached.acquire(now=NOW + timedelta(seconds=3))
    assert first.outcome is AOSPBuildOutcome.SUCCESS
    assert too_soon.outcome is AOSPBuildOutcome.VALIDATION_FAILURE
    assert unchanged.outcome is AOSPBuildOutcome.CACHE_NOT_MODIFIED
    assert unchanged.retained_claim_ids == first.retained_claim_ids
    assert dict(transport.requests[-1].headers)["If-None-Match"] == '"aosp-v1"'


def test_receipt_tampering_and_symlink_are_rejected(tmp_path) -> None:
    acquirer, _transport = _acquirer(tmp_path, _response(_html()))
    acquirer.acquire(now=NOW)
    raw = json.loads(acquirer.receipts.path.read_text(encoding="utf-8"))
    raw["codename_mapping_inferred"] = True
    acquirer.receipts.path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(AOSPBuildNumbersError, match="codename inference|digest"):
        acquirer.receipts.load()
    if os.name != "nt":
        acquirer.receipts.path.unlink()
        outside = tmp_path / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        acquirer.receipts.path.symlink_to(outside)
        with pytest.raises(AOSPBuildNumbersError):
            acquirer.receipts.load()
