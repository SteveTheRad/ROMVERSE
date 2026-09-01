from __future__ import annotations

import os
import ssl
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID, SignatureAlgorithmOID


class LinkSecurityError(RuntimeError):
    """Raised when the local Link identity cannot be created or revalidated safely."""


@dataclass(frozen=True, slots=True)
class LinkTlsIdentity:
    certificate_path: Path
    private_key_path: Path
    certificate_sha256: str
    safety_code: str
    not_after: str

    CERTIFICATE_NAME = "romverse-link-certificate.pem"
    PRIVATE_KEY_NAME = "romverse-link-private-key.pem"
    LIFETIME = timedelta(days=365)

    @classmethod
    def load_or_create(cls, root: Path) -> LinkTlsIdentity:
        root = root.resolve()
        if root.exists() and (root.is_symlink() or not root.is_dir()):
            raise LinkSecurityError("ROMVERSE Link identity root is not a safe directory")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with suppress(PermissionError):
            root.chmod(0o700)
        if os.name != "nt" and root.stat().st_mode & 0o077:
            raise LinkSecurityError("ROMVERSE Link identity directory permissions are too broad")
        try:
            certificate_path = root / cls.CERTIFICATE_NAME
            private_key_path = root / cls.PRIVATE_KEY_NAME
            if certificate_path.exists() or private_key_path.exists():
                if not certificate_path.is_file() or not private_key_path.is_file():
                    raise LinkSecurityError("ROMVERSE Link identity is incomplete")
                return cls._load(certificate_path, private_key_path)
            return cls._create(certificate_path, private_key_path)
        except LinkSecurityError:
            raise
        except OSError as exc:
            raise LinkSecurityError("ROMVERSE Link identity could not be accessed safely") from exc

    @classmethod
    def _create(cls, certificate_path: Path, private_key_path: Path) -> LinkTlsIdentity:
        now = datetime.now(UTC)
        key = ec.generate_private_key(ec.SECP256R1())
        subject = x509.Name(
            [
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "RadForge Labs"),
                x509.NameAttribute(NameOID.COMMON_NAME, "ROMVERSE Local Link"),
            ]
        )
        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + cls.LIFETIME)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
                critical=False,
            )
            .add_extension(
                x509.SubjectAlternativeName([x509.DNSName("romverse.local")]),
                critical=False,
            )
            .sign(key, hashes.SHA256())
        )
        key_bytes = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        certificate_bytes = certificate.public_bytes(serialization.Encoding.PEM)
        _atomic_bytes(private_key_path, key_bytes, 0o600)
        try:
            _atomic_bytes(certificate_path, certificate_bytes, 0o644)
        except Exception:
            private_key_path.unlink(missing_ok=True)
            raise
        return cls._load(certificate_path, private_key_path)

    @classmethod
    def _load(cls, certificate_path: Path, private_key_path: Path) -> LinkTlsIdentity:
        try:
            if certificate_path.is_symlink() or private_key_path.is_symlink():
                raise LinkSecurityError("ROMVERSE Link identity cannot use symbolic links")
            if os.name != "nt" and private_key_path.stat().st_mode & 0o077:
                raise LinkSecurityError("ROMVERSE Link private key permissions are too broad")
            certificate = x509.load_pem_x509_certificate(certificate_path.read_bytes())
            key = serialization.load_pem_private_key(private_key_path.read_bytes(), password=None)
            if not isinstance(key, ec.EllipticCurvePrivateKey):
                raise LinkSecurityError("ROMVERSE Link private key type is unsupported")
            public = key.public_key().public_bytes(
                serialization.Encoding.DER,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            certificate_key = certificate.public_key()
            if not isinstance(certificate_key, ec.EllipticCurvePublicKey) or not isinstance(
                certificate_key.curve, ec.SECP256R1
            ):
                raise LinkSecurityError("ROMVERSE Link certificate key type is unsupported")
            certificate_public = certificate_key.public_bytes(
                serialization.Encoding.DER,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            if public != certificate_public or certificate.issuer != certificate.subject:
                raise LinkSecurityError("ROMVERSE Link certificate and private key do not match")
            common_names = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
            if len(common_names) != 1 or common_names[0].value != "ROMVERSE Local Link":
                raise LinkSecurityError("ROMVERSE Link certificate identity is invalid")
            basic = certificate.extensions.get_extension_for_class(x509.BasicConstraints).value
            extended = certificate.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
            alternative = certificate.extensions.get_extension_for_class(
                x509.SubjectAlternativeName
            ).value
            if (
                basic.ca
                or tuple(extended) != (ExtendedKeyUsageOID.SERVER_AUTH,)
                or alternative.get_values_for_type(x509.DNSName) != ["romverse.local"]
                or certificate.signature_algorithm_oid != SignatureAlgorithmOID.ECDSA_WITH_SHA256
            ):
                raise LinkSecurityError("ROMVERSE Link certificate policy is invalid")
            now = datetime.now(UTC)
            if not certificate.not_valid_before_utc <= now < certificate.not_valid_after_utc:
                raise LinkSecurityError("ROMVERSE Link certificate is expired or not yet valid")
            certificate_key.verify(
                certificate.signature,
                certificate.tbs_certificate_bytes,
                ec.ECDSA(certificate.signature_hash_algorithm),
            )
        except LinkSecurityError:
            raise
        except (OSError, ValueError, TypeError, InvalidSignature, x509.ExtensionNotFound) as exc:
            raise LinkSecurityError("ROMVERSE Link identity failed validation") from exc
        fingerprint = certificate.fingerprint(hashes.SHA256()).hex()
        return cls(
            certificate_path.resolve(strict=True),
            private_key_path.resolve(strict=True),
            fingerprint,
            safety_code(fingerprint),
            certificate.not_valid_after_utc.isoformat(),
        )

    def server_context(self) -> ssl.SSLContext:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(self.certificate_path, self.private_key_path)
        return context


def safety_code(certificate_sha256: str) -> str:
    normalized = certificate_sha256.casefold()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise LinkSecurityError("ROMVERSE Link certificate fingerprint is invalid")
    visible = normalized[:24].upper()
    return "-".join(visible[index : index + 4] for index in range(0, len(visible), 4))


def _atomic_bytes(path: Path, content: bytes, mode: int) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        with suppress(PermissionError):
            path.chmod(mode)
    finally:
        temporary.unlink(missing_ok=True)
