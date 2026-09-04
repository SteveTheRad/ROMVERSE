from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from romverse.device_packs.attestations import PublisherTrustKey
from romverse.device_packs.foundry import FoundryDraftRevision
from romverse.infrastructure.local_store import atomic_write_bytes, ensure_private_directory
from romverse.infrastructure.process import CommandRunner


@dataclass(frozen=True, slots=True)
class DevicePackContributionReport:
    verified: bool
    signer_id: str
    contributor_role: str
    pack_id: str
    pack_version: str
    draft_sha256: str
    evidence_scopes: tuple[str, ...]
    review_report_sha256: str
    issued_at: str
    expires_at: str
    envelope_sha256: str
    reason: str
    publication_authority: str = "none"
    production_registry_changed: bool = False
    review_required: bool = True


@dataclass(frozen=True, slots=True)
class DevicePackContributionImportResult:
    report: DevicePackContributionReport
    stored_path: str


class DevicePackContributionVerifier:
    """Verify role-scoped Foundry evidence without promoting an experimental Pack."""

    FORMAT = "romverse.device-pack-foundry-contribution"
    STATEMENT = (
        "I attest that the attached review report accurately supports only the declared "
        "evidence scopes for this exact experimental Device Pack revision."
    )
    CONTRIBUTOR_ROLES = frozenset({"manufacturer", "qualified-expert"})
    EVIDENCE_SCOPES = frozenset(
        {
            "identity",
            "variant",
            "factory-firmware",
            "partitions-avb",
            "flash-rollback-contract",
            "simulation",
            "physical-device-test",
        }
    )
    REQUIRED_FIELDS = frozenset(
        {
            "format",
            "schema_version",
            "signature_algorithm",
            "signer_id",
            "contributor_role",
            "pack_id",
            "pack_version",
            "draft_sha256",
            "evidence_scope",
            "review_report_sha256",
            "issued_at",
            "expires_at",
            "statement",
            "signature",
        }
    )
    MAX_VALIDITY = timedelta(days=366)

    def __init__(
        self,
        openssl: Path,
        runner: CommandRunner,
        trust_keys: tuple[PublisherTrustKey, ...],
    ) -> None:
        self.openssl = openssl.resolve()
        self.runner = runner
        self.trust_keys = {key.signer_id: key for key in trust_keys}

    def verify(
        self,
        revision: FoundryDraftRevision,
        envelope_path: Path,
        *,
        now: datetime | None = None,
    ) -> DevicePackContributionReport:
        timestamp = (now or datetime.now(UTC)).astimezone(UTC)
        try:
            raw = envelope_path.read_bytes()
            data = json.loads(raw)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return self._failed(revision, "Contribution envelope is unreadable")
        if not isinstance(data, dict):
            return self._failed(revision, "Contribution envelope must be a JSON object")
        envelope_digest = hashlib.sha256(raw).hexdigest()
        raw_scopes = data.get("evidence_scope")
        scopes = (
            tuple(raw_scopes)
            if isinstance(raw_scopes, list) and all(isinstance(scope, str) for scope in raw_scopes)
            else ()
        )
        common = {
            "signer_id": str(data.get("signer_id", "")),
            "contributor_role": str(data.get("contributor_role", "")),
            "pack_id": str(data.get("pack_id", "")),
            "pack_version": str(data.get("pack_version", "")),
            "draft_sha256": str(data.get("draft_sha256", "")),
            "evidence_scopes": scopes,
            "review_report_sha256": str(data.get("review_report_sha256", "")),
            "issued_at": str(data.get("issued_at", "")),
            "expires_at": str(data.get("expires_at", "")),
            "envelope_sha256": envelope_digest,
        }

        def failed(reason: str) -> DevicePackContributionReport:
            return DevicePackContributionReport(False, **common, reason=reason)

        if set(data) != self.REQUIRED_FIELDS:
            return failed("Contribution envelope fields are incomplete or unsupported")
        if raw != self.canonical_bytes(data) + b"\n":
            return failed("Contribution envelope is not the canonical signed artifact")
        if data.get("format") != self.FORMAT or data.get("schema_version") != 1:
            return failed("Unsupported Device Pack contribution format")
        if data.get("signature_algorithm") != "ed25519":
            return failed("Only Ed25519 Device Pack contributions are accepted")
        if data.get("statement") != self.STATEMENT:
            return failed("Contribution statement is missing or altered")
        if (
            common["pack_id"] != revision.pack_id
            or common["pack_version"] != revision.version
            or common["draft_sha256"] != revision.sha256
        ):
            return failed("Contribution does not bind the exact current Foundry revision")
        if (
            not scopes
            or tuple(sorted(scopes)) != scopes
            or len(set(scopes)) != len(scopes)
            or not set(scopes).issubset(self.EVIDENCE_SCOPES)
        ):
            return failed("Contribution evidence scopes are invalid or not canonical")
        if not _sha256(common["review_report_sha256"]):
            return failed("Contribution review report SHA-256 is invalid")
        try:
            issued = _timestamp(common["issued_at"])
            expires = _timestamp(common["expires_at"])
        except ValueError:
            return failed("Contribution validity timestamps are invalid")
        if issued > timestamp + timedelta(minutes=5):
            return failed("Contribution issue time is in the future")
        if expires <= timestamp or expires <= issued or expires - issued > self.MAX_VALIDITY:
            return failed("Contribution has expired or has an invalid validity window")
        role = common["contributor_role"]
        if role not in self.CONTRIBUTOR_ROLES:
            return failed("Contribution role is unsupported")
        trust = self.trust_keys.get(common["signer_id"])
        if trust is None or trust.revoked:
            return failed("Publisher signing key is unknown or revoked")
        if role not in trust.contribution_roles:
            return failed("Publisher signing key is not trusted for the claimed contribution role")
        try:
            public_key = trust.public_key_path.resolve(strict=True)
            if (
                trust.public_key_path.is_symlink()
                or not public_key.is_file()
                or _file_sha256(public_key) != trust.public_key_sha256
            ):
                return failed("Publisher public key integrity check failed")
            signature = base64.b64decode(str(data["signature"]), validate=True)
        except (OSError, ValueError, TypeError, KeyError):
            return failed("Contribution signature is malformed")
        if len(signature) != 64:
            return failed("Contribution Ed25519 signature has an invalid length")
        if not self.openssl.is_file() or self.openssl.is_symlink():
            return failed("Verified OpenSSL executable is unavailable")
        unsigned = dict(data)
        unsigned.pop("signature")
        with TemporaryDirectory(prefix="romverse-contribution-") as directory:
            root = Path(directory)
            message_path = root / "message.json"
            signature_path = root / "signature.bin"
            message_path.write_bytes(self.canonical_bytes(unsigned))
            signature_path.write_bytes(signature)
            result = self.runner.run(
                (
                    str(self.openssl),
                    "pkeyutl",
                    "-verify",
                    "-pubin",
                    "-inkey",
                    str(public_key),
                    "-rawin",
                    "-in",
                    str(message_path),
                    "-sigfile",
                    str(signature_path),
                ),
                timeout=15,
            )
        if not result.ok:
            return failed("Publisher contribution signature verification failed")
        return DevicePackContributionReport(
            True,
            **common,
            reason="Role, exact Foundry revision, review report and publisher signature verified",
        )

    @staticmethod
    def canonical_bytes(payload: dict[str, object]) -> bytes:
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @staticmethod
    def _failed(
        revision: FoundryDraftRevision,
        reason: str,
    ) -> DevicePackContributionReport:
        return DevicePackContributionReport(
            False,
            "",
            "",
            revision.pack_id,
            revision.version,
            revision.sha256,
            (),
            "",
            "",
            "",
            "",
            reason,
        )


class DevicePackContributionStore:
    """Persist only verified, exact-revision contributions outside the Pack registry."""

    MAX_ENVELOPE_BYTES = 1024 * 1024
    MAX_PACK_ENVELOPES = 128

    def __init__(self, workspace: Path, verifier: DevicePackContributionVerifier) -> None:
        self.workspace = workspace.resolve()
        self.root = self.workspace / "device_pack_contributions"
        self.verifier = verifier

    def import_envelope(
        self,
        revision: FoundryDraftRevision,
        source: Path,
        *,
        now: datetime | None = None,
    ) -> DevicePackContributionImportResult:
        if not self._revision_is_current(revision):
            return DevicePackContributionImportResult(
                self.verifier._failed(
                    revision,
                    "Foundry revision is missing, altered, linked, or outside this workspace",
                ),
                "",
            )
        try:
            if source.is_symlink():
                raise OSError("symbolic link")
            resolved = source.resolve(strict=True)
            if not resolved.is_file() or resolved.stat().st_size > self.MAX_ENVELOPE_BYTES:
                raise OSError("not a bounded regular file")
            raw = resolved.read_bytes()
        except OSError:
            return DevicePackContributionImportResult(
                self.verifier._failed(revision, "Contribution source is unreadable or unsafe"),
                "",
            )
        try:
            ensure_private_directory(self.root, boundary=self.workspace)
        except OSError:
            return DevicePackContributionImportResult(
                self.verifier._failed(revision, "Contribution store is unavailable or unsafe"),
                "",
            )
        temporary = self.root / f".import-{uuid4().hex}.tmp"
        try:
            atomic_write_bytes(
                temporary,
                raw,
                boundary=self.workspace,
                maximum_bytes=self.MAX_ENVELOPE_BYTES,
            )
            report = self.verifier.verify(revision, temporary, now=now)
            if not report.verified:
                return DevicePackContributionImportResult(report, "")
            pack_root = self.root / _safe_name(revision.pack_id)
            ensure_private_directory(pack_root, boundary=self.workspace)
            destination = pack_root / f"{report.envelope_sha256}.romverse.json"
            existing = tuple(pack_root.iterdir())
            if destination not in existing and len(existing) >= self.MAX_PACK_ENVELOPES:
                return DevicePackContributionImportResult(
                    self.verifier._failed(
                        revision,
                        "Contribution store reached its bounded per-Pack limit",
                    ),
                    "",
                )
            atomic_write_bytes(
                destination,
                raw,
                boundary=self.workspace,
                maximum_bytes=self.MAX_ENVELOPE_BYTES,
            )
            return DevicePackContributionImportResult(
                report,
                destination.relative_to(self.workspace).as_posix(),
            )
        except OSError:
            return DevicePackContributionImportResult(
                self.verifier._failed(revision, "Contribution store is unavailable or unsafe"),
                "",
            )
        finally:
            temporary.unlink(missing_ok=True)

    def load_exact(
        self,
        revision: FoundryDraftRevision,
        *,
        now: datetime | None = None,
    ) -> tuple[DevicePackContributionReport, ...]:
        if not self._revision_is_current(revision):
            return ()
        pack_root = self.root / _safe_name(revision.pack_id)
        if not pack_root.is_dir() or pack_root.is_symlink():
            return ()
        reports: list[DevicePackContributionReport] = []
        for path in sorted(pack_root.glob("*.romverse.json"))[: self.MAX_PACK_ENVELOPES]:
            try:
                if path.is_symlink() or path.stat().st_size > self.MAX_ENVELOPE_BYTES:
                    continue
            except OSError:
                continue
            report = self.verifier.verify(revision, path, now=now)
            if report.verified and path.name == f"{report.envelope_sha256}.romverse.json":
                reports.append(report)
        return tuple(
            sorted(
                reports,
                key=lambda report: (
                    report.contributor_role,
                    report.signer_id,
                    report.envelope_sha256,
                ),
            )
        )

    def _revision_is_current(self, revision: FoundryDraftRevision) -> bool:
        path = Path(os.path.abspath(revision.path))
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(self.workspace)
            raw = resolved.read_bytes()
        except (OSError, RuntimeError, ValueError):
            return False
        return bool(
            not path.is_symlink()
            and resolved.is_file()
            and len(raw) <= self.MAX_ENVELOPE_BYTES
            and hashlib.sha256(raw).hexdigest() == revision.sha256
            and resolved.name == f"{revision.pack_id}-{revision.sha256[:12]}.draft.json"
        )


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("timezone required")
    return parsed.astimezone(UTC)


def _sha256(value: str) -> bool:
    return re.fullmatch(r"[0-9a-f]{64}", value.casefold()) is not None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_name(value: str) -> str:
    safe = "".join(
        character if character.isalnum() or character in ".-_" else "-" for character in value
    )
    return safe.strip(".-") or "device-pack"
