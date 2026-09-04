from __future__ import annotations

import base64
import hashlib
import json
import shutil
import stat
import subprocess
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from romverse.device_packs.attestations import PublisherTrustKey
from romverse.device_packs.contributions import (
    DevicePackContributionStore,
    DevicePackContributionVerifier,
)
from romverse.device_packs.drafts import DevicePackDraftService
from romverse.device_packs.foundry import DevicePackFoundryService, FoundryDraftRevision
from romverse.infrastructure.process import SubprocessRunner


def _draft_request() -> dict[str, object]:
    return {
        "format": "romverse.device-pack-draft-request",
        "schema_version": 1,
        "pack_id": "example.contributed-device",
        "version": "0.1.0",
        "display_name": "Example Contributed Device",
        "priority": 220,
        "match": {
            "manufacturers": ["Example OEM"],
            "model_patterns": ["Example Phone 1"],
            "product_patterns": ["example_product"],
        },
        "knowledge_sources": [
            {
                "source_id": "example.official-device",
                "label": "Official device reference",
                "url": "https://example.com/device",
                "authority": "Example OEM",
                "scope": "Published identity",
                "verified_on": "2026-09-01",
            }
        ],
        "notes": ["Read-only draft evidence."],
    }


@pytest.fixture
def contribution_context(tmp_path: Path):
    openssl = shutil.which("openssl")
    if openssl is None:
        pytest.skip("OpenSSL is unavailable")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    drafts = workspace / "device_pack_drafts"
    DevicePackDraftService().export(_draft_request(), drafts, boundary=workspace)
    revision = (
        DevicePackFoundryService()
        .inspect(
            drafts,
            boundary=workspace,
        )
        .revisions[0]
    )
    private = tmp_path / "manufacturer-private.pem"
    public = tmp_path / "manufacturer-public.pem"
    subprocess.run(
        (openssl, "genpkey", "-algorithm", "ed25519", "-out", str(private)),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        (openssl, "pkey", "-in", str(private), "-pubout", "-out", str(public)),
        check=True,
        capture_output=True,
    )
    key = PublisherTrustKey(
        "example.manufacturer",
        public,
        hashlib.sha256(public.read_bytes()).hexdigest(),
        contribution_roles=("manufacturer",),
    )
    issued = datetime(2026, 9, 1, tzinfo=UTC)
    return workspace, revision, Path(openssl), private, key, issued


def _signed_envelope(
    root: Path,
    openssl: Path,
    private: Path,
    revision: FoundryDraftRevision,
    issued: datetime,
    *,
    role: str = "manufacturer",
    scopes: tuple[str, ...] = ("identity", "partitions-avb"),
    expires_in_days: int = 90,
    name: str = "contribution.romverse",
) -> Path:
    payload: dict[str, object] = {
        "format": DevicePackContributionVerifier.FORMAT,
        "schema_version": 1,
        "signature_algorithm": "ed25519",
        "signer_id": "example.manufacturer",
        "contributor_role": role,
        "pack_id": revision.pack_id,
        "pack_version": revision.version,
        "draft_sha256": revision.sha256,
        "evidence_scope": sorted(scopes),
        "review_report_sha256": "9" * 64,
        "issued_at": issued.isoformat(),
        "expires_at": (issued + timedelta(days=expires_in_days)).isoformat(),
        "statement": DevicePackContributionVerifier.STATEMENT,
    }
    message = root / f"{name}.message"
    signature = root / f"{name}.signature"
    message.write_bytes(DevicePackContributionVerifier.canonical_bytes(payload))
    subprocess.run(
        (
            str(openssl),
            "pkeyutl",
            "-sign",
            "-inkey",
            str(private),
            "-rawin",
            "-in",
            str(message),
            "-out",
            str(signature),
        ),
        check=True,
        capture_output=True,
    )
    payload["signature"] = base64.b64encode(signature.read_bytes()).decode("ascii")
    envelope = root / name
    envelope.write_bytes(DevicePackContributionVerifier.canonical_bytes(payload) + b"\n")
    return envelope


def test_role_scoped_contribution_is_stored_and_reverified_without_pack_authority(
    contribution_context,
    tmp_path: Path,
) -> None:
    workspace, revision, openssl, private, key, issued = contribution_context
    envelope = _signed_envelope(tmp_path, openssl, private, revision, issued)
    verifier = DevicePackContributionVerifier(openssl, SubprocessRunner(), (key,))
    store = DevicePackContributionStore(workspace, verifier)

    imported = store.import_envelope(revision, envelope, now=issued + timedelta(days=1))
    loaded = store.load_exact(revision, now=issued + timedelta(days=2))

    assert imported.report.verified
    assert imported.report.contributor_role == "manufacturer"
    assert imported.report.evidence_scopes == ("identity", "partitions-avb")
    assert imported.report.publication_authority == "none"
    assert not imported.report.production_registry_changed
    assert imported.report.review_required
    assert imported.stored_path.startswith("device_pack_contributions/example.contributed-device/")
    assert len(loaded) == 1
    assert loaded[0].envelope_sha256 == imported.report.envelope_sha256
    stored = workspace / imported.stored_path
    assert stat.S_IMODE(store.root.stat().st_mode) == 0o700
    assert stat.S_IMODE(stored.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(stored.stat().st_mode) == 0o600

    stored.write_bytes(stored.read_bytes().replace(b"partitions-avb", b"simulation----"))
    assert store.load_exact(revision, now=issued + timedelta(days=2)) == ()


def test_role_cannot_be_self_assigned_and_revoked_or_expired_evidence_fails_closed(
    contribution_context,
    tmp_path: Path,
) -> None:
    workspace, revision, openssl, private, key, issued = contribution_context
    claimed_expert = _signed_envelope(
        tmp_path,
        openssl,
        private,
        revision,
        issued,
        role="qualified-expert",
        name="expert.romverse",
    )
    verifier = DevicePackContributionVerifier(openssl, SubprocessRunner(), (key,))

    role_report = verifier.verify(revision, claimed_expert, now=issued + timedelta(days=1))
    revoked_report = DevicePackContributionVerifier(
        openssl,
        SubprocessRunner(),
        (replace(key, revoked=True),),
    ).verify(revision, claimed_expert, now=issued + timedelta(days=1))
    expired_report = verifier.verify(revision, claimed_expert, now=issued + timedelta(days=91))

    assert not role_report.verified
    assert "not trusted for the claimed" in role_report.reason
    assert not revoked_report.verified
    assert "revoked" in revoked_report.reason
    assert not expired_report.verified
    assert "expired" in expired_report.reason
    assert not (workspace / "device_pack_contributions").exists()


def test_tampering_or_wrong_foundry_revision_is_never_persisted(
    contribution_context,
    tmp_path: Path,
) -> None:
    workspace, revision, openssl, private, key, issued = contribution_context
    envelope = _signed_envelope(tmp_path, openssl, private, revision, issued)
    data = json.loads(envelope.read_bytes())
    data["review_report_sha256"] = "8" * 64
    envelope.write_bytes(DevicePackContributionVerifier.canonical_bytes(data) + b"\n")
    verifier = DevicePackContributionVerifier(openssl, SubprocessRunner(), (key,))
    store = DevicePackContributionStore(workspace, verifier)

    tampered = store.import_envelope(revision, envelope, now=issued + timedelta(days=1))
    wrong = verifier.verify(
        replace(revision, sha256="0" * 64),
        envelope,
        now=issued + timedelta(days=1),
    )

    assert not tampered.report.verified
    assert "signature verification failed" in tampered.report.reason
    assert tampered.stored_path == ""
    assert not wrong.verified
    assert "exact current Foundry revision" in wrong.reason
    assert not tuple((workspace / "device_pack_contributions").rglob("*.romverse.json"))
