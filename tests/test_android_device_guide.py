from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta

import pytest

from romverse.knowledge.android_device_guide import (
    ANDROID_DEVICE_GUIDE_URL,
    AndroidDeviceGuideAcquirer,
    AndroidGuideError,
    GuideOutcome,
    GuideRequest,
    GuideResponse,
)
from romverse.knowledge.online_evidence import (
    ClaimKind,
    EvidenceConsumer,
    EvidenceFreshness,
    EvidenceState,
)

NOW = datetime(2026, 9, 8, 3, 0, tzinfo=UTC)


def _html(
    *,
    assistant_heading: str = "Troubleshoot with the Connection Assistant",
    usb_heading: str = "Resolve USB connection issues",
    assistant: str = (
        "The Connection Assistant provides step-by-step instructions to help you set up and use "
        "a device over a USB connection."
    ),
    cable: str = "To check whether the issue is being caused by a faulty USB cable, review this section.",
    debugging: str = "On the device, open Developer options and then enable USB debugging.",
    extra_usb: str = "",
    language: str = "en",
    canonical: str = ANDROID_DEVICE_GUIDE_URL,
    modified: str = "2026-09-01T00:00:00Z",
    malicious: str = "",
) -> bytes:
    return f"""<!doctype html>
<html lang="{language}">
<head>
  <link rel="canonical" href="{canonical}">
  <meta charset="utf-8">
  <meta itemprop="dateModified" content="{modified}">
  <title>Run apps on a hardware device</title>
  <script>USB cable adb shell PRIVATE-SCRIPT</script>
</head>
<body>
  <nav>USB debugging navigation must not be retained</nav>
  <main>
    <h1>Run apps on a hardware device</h1>
    <h2>Set up a device for development</h2>
    <ul><li>{debugging}</li></ul>
    <h2>Troubleshoot device connection</h2>
    <h2>{assistant_heading}</h2>
    <p>{assistant}</p>
    <pre>adb devices PRIVATE-CODE</pre>
    <h2>{usb_heading}</h2>
    <h4>Check the USB cable</h4>
    <p>{cable}</p>
    <ul>{extra_usb}</ul>
    {malicious}
  </main>
</body>
</html>""".encode()


class FixtureTransport:
    def __init__(self, response: GuideResponse | Exception) -> None:
        self.response = response
        self.requests: list[GuideRequest] = []

    def fetch(self, request: GuideRequest) -> GuideResponse:
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _response(
    body: bytes,
    *,
    status: int = 200,
    url: str = ANDROID_DEVICE_GUIDE_URL,
    headers: dict[str, str] | None = None,
) -> GuideResponse:
    return GuideResponse(
        status,
        url,
        headers
        or {
            "Content-Type": "text/html; charset=utf-8",
            "Content-Length": str(len(body)),
            "ETag": '"guide-v1"',
            "Last-Modified": "Tue, 01 Sep 2026 00:00:00 GMT",
        },
        body,
    )


def _acquirer(tmp_path, response):
    transport = FixtureTransport(response)
    return AndroidDeviceGuideAcquirer(tmp_path, transport=transport), transport


def test_reviewed_official_guide_retains_three_non_executable_claims_only(tmp_path) -> None:
    body = _html()
    acquirer, transport = _acquirer(tmp_path, _response(body))

    receipt = acquirer.acquire(now=NOW)

    assert receipt.outcome is GuideOutcome.SUCCESS
    assert receipt.source_url == ANDROID_DEVICE_GUIDE_URL
    assert receipt.published_at == "2026-09-01T00:00:00+00:00"
    assert receipt.content_bytes == len(body)
    assert len(receipt.matched_claim_ids) == 3
    assert receipt.evidence_state == "officially-documented"
    assert receipt.raw_response_retained is False
    assert receipt.execution_authority == "none"
    assert not receipt.phone_action_allowed
    assert not receipt.guardian_approval
    assert not receipt.bootloader_relock_allowed
    claims = acquirer.evidence.load().claims
    assert len(claims) == 3
    assert all(claim.knowledge_kind is ClaimKind.GUIDE for claim in claims)
    assert all(claim.state is EvidenceState.OFFICIALLY_DOCUMENTED for claim in claims)
    assert {claim.supporting_excerpt for claim in claims} == {
        "step-by-step instructions",
        "faulty USB cable",
        "enable USB debugging",
    }
    retained = json.dumps([claim.supporting_excerpt for claim in claims])
    assert "PRIVATE-SCRIPT" not in retained
    assert "PRIVATE-CODE" not in retained
    assert "navigation" not in retained
    assert "adb devices" not in retained
    assert not any(path.suffix == ".html" for path in tmp_path.rglob("*"))
    request = transport.requests[0]
    assert request.url == ANDROID_DEVICE_GUIDE_URL
    assert request.connect_timeout_seconds == 8.0
    assert request.read_timeout_seconds == 12.0
    assert request.overall_timeout_seconds == 30.0
    assert "Authorization" not in dict(request.headers)
    assert "Cookie" not in dict(request.headers)
    if os.name != "nt":
        assert acquirer.receipts.path.stat().st_mode & 0o777 == 0o600


def test_guide_projects_to_only_the_four_approved_read_only_consumers(tmp_path) -> None:
    acquirer, _transport = _acquirer(tmp_path, _response(_html()))
    receipt = acquirer.acquire(now=NOW)

    projections = acquirer.projections(receipt)

    assert tuple(item.consumer for item in projections) == (
        EvidenceConsumer.KNOWLEDGE_ARCHIVES,
        EvidenceConsumer.DEVICE_DNA,
        EvidenceConsumer.NEXUS,
        EvidenceConsumer.INSIGHT,
    )
    assert all(item.execution_authority == "none" for item in projections)
    assert all(not item.phone_action_allowed for item in projections)
    assert all(not item.guardian_approval for item in projections)


@pytest.mark.parametrize(
    "changes",
    (
        {"assistant_heading": "Changed assistant heading"},
        {"usb_heading": "Changed USB heading"},
        {"assistant": "General connection information only."},
        {"cable": "General host information only."},
        {"debugging": "General device information only."},
    ),
)
def test_missing_or_changed_reviewed_sections_fail_closed(tmp_path, changes) -> None:
    acquirer, _transport = _acquirer(tmp_path, _response(_html(**changes)))

    receipt = acquirer.acquire(now=NOW)

    assert receipt.outcome is GuideOutcome.VALIDATION_FAILURE
    assert not receipt.retained_claim_ids


def test_scripts_code_navigation_and_event_attributes_cannot_supply_evidence(tmp_path) -> None:
    body = _html(
        assistant="General connection information only.",
        malicious=(
            "<script>Connection Assistant over USB connection.</script>"
            "<code>Connection Assistant over USB connection.</code>"
            '<p onclick="adb shell">Harmless unrelated paragraph.</p>'
        ),
    )
    acquirer, _transport = _acquirer(tmp_path, _response(body))

    receipt = acquirer.acquire(now=NOW)

    assert receipt.outcome is GuideOutcome.VALIDATION_FAILURE
    assert not receipt.matched_claim_ids


def test_oversized_reviewed_section_conflicting_guidance_and_private_text_fail(tmp_path) -> None:
    oversized, _transport = _acquirer(
        tmp_path / "oversized",
        _response(_html(cable="A faulty USB cable " + "x" * 400 + ".")),
    )
    conflicting, _transport = _acquirer(
        tmp_path / "conflict",
        _response(_html(extra_usb="<li>A faulty USB cable can also cause this symptom.</li>")),
    )
    private, _transport = _acquirer(
        tmp_path / "private",
        _response(_html(cable="A faulty USB cable was reported by user@example.com.")),
    )

    assert oversized.acquire(now=NOW).outcome is GuideOutcome.VALIDATION_FAILURE
    assert conflicting.acquire(now=NOW).outcome is GuideOutcome.VALIDATION_FAILURE
    private_receipt = private.acquire(now=NOW)
    assert private_receipt.outcome is GuideOutcome.VALIDATION_FAILURE
    assert "user@example.com" not in json.dumps(private_receipt.reason)


@pytest.mark.parametrize(
    "response",
    (
        _response(_html(), url="https://developer.android.com/studio/run/device?hl=fr"),
        _response(_html(language="fr")),
        _response(_html(canonical="https://developer.android.com/studio/run/device?hl=en")),
        _response(_html(), headers={"Content-Type": "application/javascript"}),
        _response(_html(), headers={"Content-Type": "text/html", "Content-Encoding": "gzip"}),
        _response(_html(), headers={"Content-Type": "text/html", "Content-Length": "1"}),
    ),
)
def test_redirect_localization_content_type_compression_and_truncation_fail(
    tmp_path, response
) -> None:
    acquirer, _transport = _acquirer(tmp_path, response)

    receipt = acquirer.acquire(now=NOW)

    assert receipt.outcome is GuideOutcome.VALIDATION_FAILURE
    assert not receipt.matched_claim_ids


def test_http_failure_timeout_and_cache_not_modified_are_durable(tmp_path) -> None:
    failed, _transport = _acquirer(tmp_path / "http", _response(b"failure", status=503))
    timed_out, _transport = _acquirer(tmp_path / "timeout", TimeoutError("read timeout"))
    assert failed.acquire(now=NOW).outcome is GuideOutcome.HTTP_FAILURE
    assert timed_out.acquire(now=NOW).outcome is GuideOutcome.HTTP_FAILURE

    transport = FixtureTransport(_response(_html()))
    cached = AndroidDeviceGuideAcquirer(tmp_path / "cached", transport=transport)
    first = cached.acquire(now=NOW)
    transport.response = _response(b"", status=304, headers={"ETag": '"guide-v1"'})
    second = cached.acquire(now=NOW + timedelta(seconds=3))

    assert first.outcome is GuideOutcome.SUCCESS
    assert second.outcome is GuideOutcome.CACHE_NOT_MODIFIED
    assert second.content_digest == first.content_digest
    assert second.retained_claim_ids == first.retained_claim_ids
    assert dict(transport.requests[-1].headers)["If-None-Match"] == '"guide-v1"'


def test_stale_revision_remains_official_but_requires_investigation(tmp_path) -> None:
    acquirer, _transport = _acquirer(
        tmp_path,
        _response(_html(modified="2024-01-01T00:00:00Z")),
    )

    receipt = acquirer.acquire(now=NOW)
    claims = acquirer.evidence.load().claims

    assert receipt.outcome is GuideOutcome.SUCCESS
    assert all(claim.state is EvidenceState.OFFICIALLY_DOCUMENTED for claim in claims)
    assert all(claim.source.freshness is EvidenceFreshness.STALE for claim in claims)
    assert all(item.investigation_required for item in acquirer.projections(receipt))


def test_receipt_tampering_and_symlink_are_rejected(tmp_path) -> None:
    acquirer, _transport = _acquirer(tmp_path, _response(_html()))
    acquirer.acquire(now=NOW)
    raw = json.loads(acquirer.receipts.path.read_text(encoding="utf-8"))
    raw["evidence_state"] = "live-confirmed"
    acquirer.receipts.path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(AndroidGuideError, match="evidence state|digest"):
        acquirer.receipts.load()

    if os.name != "nt":
        acquirer.receipts.path.unlink()
        outside = tmp_path / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        acquirer.receipts.path.symlink_to(outside)
        with pytest.raises(AndroidGuideError):
            acquirer.receipts.load()
