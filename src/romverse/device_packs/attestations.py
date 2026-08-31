from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from romverse.device.models import AndroidDevice
from romverse.device_packs.models import DevicePack
from romverse.infrastructure.local_store import atomic_write_bytes, ensure_private_directory
from romverse.infrastructure.process import CommandRunner


@dataclass(frozen=True, slots=True)
class PublisherTrustKey:
    signer_id: str
    public_key_path: Path
    public_key_sha256: str
    revoked: bool = False


@dataclass(frozen=True, slots=True)
class PhysicalRecoveryAttestationReport:
    verified: bool
    signer_id: str
    pack_id: str
    pack_sha256: str
    source_build_id: str
    model: str
    product: str
    scenarios: tuple[str, ...]
    report_sha256: str
    issued_at: str
    expires_at: str
    envelope_sha256: str
    reason: str


@dataclass(frozen=True, slots=True)
class AttestationImportResult:
    report: PhysicalRecoveryAttestationReport
    stored_path: str


class DevicePackAttestationVerifier:
    """Verify detached physical-test evidence; this service grants no execution authority."""

    FORMAT = "romverse.device-pack-physical-attestation"
    REQUIRED_SCENARIOS = frozenset(
        {
            "stock_restore",
            "failed_flash_recovery",
            "slot_recovery",
            "first_boot_validation",
        }
    )

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
        pack: DevicePack,
        envelope_path: Path,
        now: datetime | None = None,
    ) -> PhysicalRecoveryAttestationReport:
        timestamp = (now or datetime.now(UTC)).astimezone(UTC)
        try:
            raw = envelope_path.read_bytes()
            data = json.loads(raw)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return self._failed(pack, "Attestation envelope is unreadable")
        envelope_digest = hashlib.sha256(raw).hexdigest()
        signer_id = str(data.get("signer_id", ""))
        common = {
            "signer_id": signer_id,
            "pack_id": str(data.get("pack_id", "")),
            "pack_sha256": str(data.get("pack_sha256", "")),
            "source_build_id": str(data.get("source_build_id", "")),
            "model": str(data.get("model", "")),
            "product": str(data.get("product", "")),
            "scenarios": tuple(map(str, data.get("scenarios", ()))),
            "report_sha256": str(data.get("report_sha256", "")),
            "issued_at": str(data.get("issued_at", "")),
            "expires_at": str(data.get("expires_at", "")),
            "envelope_sha256": envelope_digest,
        }

        def failed(reason: str) -> PhysicalRecoveryAttestationReport:
            return PhysicalRecoveryAttestationReport(False, **common, reason=reason)

        if data.get("format") != self.FORMAT or data.get("schema_version") != 1:
            return failed("Unsupported physical attestation format")
        if data.get("signature_algorithm") != "ed25519":
            return failed("Only Ed25519 physical attestations are accepted")
        if pack.build_contract is None:
            return failed("Device Pack has no exact build contract")
        if (
            common["pack_id"] != pack.pack_id
            or str(data.get("pack_version", "")) != pack.version
            or common["pack_sha256"] != pack.sha256
            or common["source_build_id"] != pack.build_contract.source.build_id
        ):
            return failed("Attestation does not bind the exact current Pack and firmware")
        if not common["model"] or not common["product"]:
            return failed("Attestation hardware identity is incomplete")
        if set(common["scenarios"]) != self.REQUIRED_SCENARIOS:
            return failed("Attestation does not cover every required recovery scenario")
        if data.get("result") != "pass":
            return failed("Physical recovery test result is not pass")
        if not _sha256(common["report_sha256"]):
            return failed("Physical test report SHA-256 is invalid")
        try:
            issued = _timestamp(common["issued_at"])
            expires = _timestamp(common["expires_at"])
        except ValueError:
            return failed("Attestation validity timestamps are invalid")
        if issued > timestamp + timedelta(minutes=5):
            return failed("Attestation issue time is in the future")
        if expires <= timestamp or expires <= issued:
            return failed("Attestation has expired or has an invalid validity window")
        trust = self.trust_keys.get(signer_id)
        if trust is None or trust.revoked:
            return failed("Publisher signing key is unknown or revoked")
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
            return failed("Attestation signature is malformed")
        if len(signature) != 64:
            return failed("Attestation Ed25519 signature has an invalid length")
        if not self.openssl.is_file() or self.openssl.is_symlink():
            return failed("Verified OpenSSL executable is unavailable")
        unsigned = dict(data)
        unsigned.pop("signature", None)
        message = self.canonical_bytes(unsigned)
        with TemporaryDirectory(prefix="romverse-attestation-") as directory:
            root = Path(directory)
            message_path = root / "message.json"
            signature_path = root / "signature.bin"
            message_path.write_bytes(message)
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
            return failed("Publisher signature verification failed")
        return PhysicalRecoveryAttestationReport(
            True,
            **common,
            reason="Exact Pack and physical recovery attestation signature verified",
        )

    @staticmethod
    def canonical_bytes(payload: dict[str, object]) -> bytes:
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @staticmethod
    def _failed(pack: DevicePack, reason: str) -> PhysicalRecoveryAttestationReport:
        return PhysicalRecoveryAttestationReport(
            False,
            "",
            pack.pack_id,
            pack.sha256,
            pack.build_contract.source.build_id if pack.build_contract else "",
            "",
            "",
            (),
            "",
            "",
            "",
            "",
            reason,
        )


class DevicePackAttestationStore:
    """Persist only verified envelopes and reverify them on every authority check."""

    MAX_ENVELOPE_BYTES = 1024 * 1024
    MAX_PACK_ENVELOPES = 128

    def __init__(self, workspace: Path, verifier: DevicePackAttestationVerifier) -> None:
        self.workspace = workspace.resolve()
        self.root = self.workspace / "device_pack_attestations"
        self.verifier = verifier

    def import_envelope(
        self,
        pack: DevicePack,
        source: Path,
        *,
        now: datetime | None = None,
    ) -> AttestationImportResult:
        try:
            if source.is_symlink():
                return AttestationImportResult(
                    self.verifier._failed(pack, "Attestation source cannot be a symbolic link"),
                    "",
                )
            resolved = source.resolve(strict=True)
            if not resolved.is_file():
                raise OSError("not a regular file")
            if resolved.stat().st_size > self.MAX_ENVELOPE_BYTES:
                return AttestationImportResult(
                    self.verifier._failed(pack, "Attestation envelope exceeds the safe size limit"),
                    "",
                )
            raw = resolved.read_bytes()
        except OSError:
            return AttestationImportResult(
                self.verifier._failed(pack, "Attestation source is unreadable"),
                "",
            )
        if len(raw) > self.MAX_ENVELOPE_BYTES:
            return AttestationImportResult(
                self.verifier._failed(pack, "Attestation envelope exceeds the safe size limit"),
                "",
            )
        try:
            ensure_private_directory(self.root, boundary=self.workspace)
        except OSError:
            return AttestationImportResult(
                self.verifier._failed(pack, "Attestation store is unavailable or unsafe"),
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
            report = self.verifier.verify(pack, temporary, now=now)
            if not report.verified:
                return AttestationImportResult(report, "")
            pack_root = self.root / _safe_name(pack.pack_id)
            ensure_private_directory(pack_root, boundary=self.workspace)
            destination = pack_root / f"{report.envelope_sha256}.romverse.json"
            atomic_write_bytes(
                destination,
                raw,
                boundary=self.workspace,
                maximum_bytes=self.MAX_ENVELOPE_BYTES,
            )
            relative = destination.relative_to(self.workspace).as_posix()
            return AttestationImportResult(report, relative)
        except OSError:
            return AttestationImportResult(
                self.verifier._failed(pack, "Attestation store is unavailable or unsafe"),
                "",
            )
        finally:
            temporary.unlink(missing_ok=True)

    def load_exact(
        self,
        pack: DevicePack,
        device: AndroidDevice,
        *,
        now: datetime | None = None,
    ) -> PhysicalRecoveryAttestationReport | None:
        pack_root = self.root / _safe_name(pack.pack_id)
        if not pack_root.is_dir() or pack_root.is_symlink():
            return None
        candidates: list[PhysicalRecoveryAttestationReport] = []
        for path in sorted(pack_root.glob("*.romverse.json"))[: self.MAX_PACK_ENVELOPES]:
            try:
                if path.is_symlink() or not path.is_file():
                    continue
                if path.stat().st_size > self.MAX_ENVELOPE_BYTES:
                    continue
            except OSError:
                continue
            report = self.verifier.verify(pack, path, now=now)
            if not report.verified or not _matches_device(report, device):
                continue
            if path.name != f"{report.envelope_sha256}.romverse.json":
                continue
            candidates.append(report)
        if not candidates:
            return None
        return max(candidates, key=lambda item: _timestamp(item.expires_at))


def load_publisher_trust_keys(root: Path) -> tuple[PublisherTrustKey, ...]:
    """Load immutable release trust anchors; malformed catalogs fail closed."""
    trusted_root = root.resolve(strict=True)
    index_path = trusted_root / "index.json"
    if index_path.is_symlink() or not index_path.is_file():
        raise ValueError("Publisher trust index is unavailable")
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Publisher trust index is unreadable") from exc
    if data.get("schema_version") != 1 or not isinstance(data.get("keys"), list):
        raise ValueError("Unsupported publisher trust index")
    if len(data["keys"]) > 64:
        raise ValueError("Publisher trust index contains too many keys")
    keys: list[PublisherTrustKey] = []
    signer_ids: set[str] = set()
    for item in data["keys"]:
        if not isinstance(item, dict):
            raise ValueError("Publisher trust entry must be an object")
        signer_id = str(item.get("signer_id", ""))
        filename = str(item.get("file", ""))
        digest = str(item.get("sha256", "")).casefold()
        revoked = item.get("revoked", False)
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", signer_id):
            raise ValueError("Publisher signer id is invalid")
        if signer_id in signer_ids:
            raise ValueError("Publisher signer id is duplicated")
        if Path(filename).name != filename or not filename.endswith(".pem"):
            raise ValueError("Publisher key filename is unsafe")
        if not _sha256(digest) or not isinstance(revoked, bool):
            raise ValueError("Publisher key metadata is invalid")
        key_path = trusted_root / filename
        try:
            resolved = key_path.resolve(strict=True)
        except OSError as exc:
            raise ValueError("Publisher public key is missing") from exc
        if (
            key_path.is_symlink()
            or not resolved.is_relative_to(trusted_root)
            or not resolved.is_file()
            or resolved.stat().st_size > 64 * 1024
            or _file_sha256(resolved) != digest
        ):
            raise ValueError("Publisher public key integrity check failed")
        keys.append(PublisherTrustKey(signer_id, resolved, digest, revoked))
        signer_ids.add(signer_id)
    return tuple(keys)


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


def _matches_device(
    report: PhysicalRecoveryAttestationReport,
    device: AndroidDevice,
) -> bool:
    model = (device.model or "").casefold().strip()
    product = (device.product or "").casefold().strip()
    codename = (device.codename or "").casefold().strip()
    return bool(
        model
        and report.model.casefold().strip() == model
        and report.product.casefold().strip() in {product, codename}
    )
