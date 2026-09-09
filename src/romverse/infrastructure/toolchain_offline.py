from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import shutil
import stat
import zipfile
from collections.abc import Callable, Iterable
from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from time import time
from uuid import uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_bytes,
    atomic_write_json,
    ensure_private_directory,
    read_regular_bytes,
    sha256_regular_file,
)


class OfflineToolchainError(ValueError):
    """An offline toolchain kit failed its integrity or filesystem contract."""


@dataclass(frozen=True, slots=True)
class OfflineToolFile:
    package: str
    path: str
    size_bytes: int
    sha256: str
    executable: bool


@dataclass(frozen=True, slots=True)
class OfflineToolchainInspection:
    schema_version: int
    bundle_sha256: str
    manifest_digest: str
    signer_fingerprint: str
    packages: tuple[str, ...]
    files: tuple[OfflineToolFile, ...]
    content_bytes: int
    phone_changed: bool
    execution_authority: str


@dataclass(frozen=True, slots=True)
class OfflineToolchainImportReceipt:
    schema_version: int
    imported_at_epoch_ms: int
    bundle_sha256: str
    manifest_digest: str
    signer_fingerprint: str
    packages: tuple[str, ...]
    file_count: int
    content_bytes: int
    source_receipts_validated: bool
    phone_changed: bool
    execution_authority: str
    receipt_digest: str


class OfflineToolchainBundleService:
    """Move hash-bound managed tools between offline ROMVERSE workspaces.

    Each workspace owns a local Ed25519 transfer identity. Importers must compare
    its fingerprint with the exporting computer before accepting a kit. This is
    an integrity and origin-continuity mechanism, not a ROMVERSE release signature.
    """

    SCHEMA_VERSION = 1
    MANIFEST_MEMBER = "ROMVERSE-OFFLINE-TOOLCHAIN.json"
    DOMAIN = b"ROMVERSE-OFFLINE-TOOLCHAIN-V1\0"
    BUNDLE_SUFFIX = ".rvtools"
    MAX_PACKAGES = 32
    MAX_FILES = 512
    MAX_DIRECTORIES = 256
    MAX_FILE_BYTES = 1024 * 1024 * 1024
    MAX_CONTENT_BYTES = 2 * 1024 * 1024 * 1024
    MAX_ARCHIVE_BYTES = MAX_CONTENT_BYTES + 64 * 1024 * 1024
    MAX_MANIFEST_BYTES = 2 * 1024 * 1024
    MAX_RECEIPT_BYTES = 256 * 1024
    CHUNK_SIZE = 4 * 1024 * 1024
    ZIP_TIMESTAMP = (2020, 1, 1, 0, 0, 0)
    SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
    PACKAGE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")
    ALLOWED_COMPRESSION = frozenset({zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED})

    def __init__(self, workspace: Path, *, clock: Callable[[], float] = time) -> None:
        self.workspace = self._safe_workspace(workspace)
        self.clock = clock
        self.managed_root = self.workspace / "tools" / "downloads"
        self.identity_root = self.workspace / "config" / "toolchain" / "offline-identity"
        self.receipt_root = self.workspace / "config" / "toolchain" / "offline-imports"

    def signer_fingerprint(self) -> str:
        _private, public = self._identity()
        return hashlib.sha256(public).hexdigest()

    def create(
        self,
        package_roots: Iterable[Path],
        destination: Path,
        *,
        validate_packages: Callable[[Path, tuple[str, ...]], bool],
        progress: Callable[[int, int], None] | None = None,
    ) -> OfflineToolchainInspection:
        roots = self._package_roots(package_roots)
        packages = tuple(root.name for root in roots)
        if validate_packages(self.managed_root, packages) is not True:
            raise OfflineToolchainError(
                "The managed-source receipts did not pass Forge Arsenal validation"
            )
        files, sources = self._inventory(roots)
        private, public = self._identity()
        manifest = self._signed_manifest(files, public, private)
        manifest_bytes = self._canonical(manifest)
        if len(manifest_bytes) > self.MAX_MANIFEST_BYTES:
            raise OfflineToolchainError("The offline toolchain manifest is too large")
        target, temporary = self._export_paths(destination)
        total = sum(item.size_bytes for item in files)
        completed = 0
        try:
            with zipfile.ZipFile(
                temporary,
                "x",
                compression=zipfile.ZIP_DEFLATED,
                allowZip64=True,
                compresslevel=6,
            ) as archive:
                archive.writestr(self._zip_info(self.MANIFEST_MEMBER, False), manifest_bytes)
                for item in files:
                    source = sources[(item.package, item.path)]
                    member = self._member(item)
                    digest = hashlib.sha256()
                    written = 0
                    before = source.stat()
                    with (
                        source.open("rb") as reader,
                        archive.open(
                            self._zip_info(member, item.executable), "w", force_zip64=True
                        ) as output,
                    ):
                        while chunk := reader.read(self.CHUNK_SIZE):
                            written += len(chunk)
                            if written > item.size_bytes:
                                raise OfflineToolchainError(
                                    f"Managed tool changed while exporting: {item.package}"
                                )
                            digest.update(chunk)
                            output.write(chunk)
                            if progress is not None:
                                progress(completed + written, total)
                    after = source.stat()
                    if (
                        written != item.size_bytes
                        or digest.hexdigest() != item.sha256
                        or not os.path.samestat(before, after)
                        or before.st_size != after.st_size
                        or before.st_mtime_ns != after.st_mtime_ns
                    ):
                        raise OfflineToolchainError(
                            f"Managed tool changed while exporting: {item.package}"
                        )
                    completed += written
            if temporary.stat().st_size > self.MAX_ARCHIVE_BYTES:
                raise OfflineToolchainError("The offline toolchain kit exceeds its size boundary")
            inspection = self.inspect(temporary)
            os.replace(temporary, target)
            if os.name != "nt":
                target.chmod(0o600)
            if progress is not None:
                progress(total, total)
            return inspection
        except OfflineToolchainError:
            raise
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            raise OfflineToolchainError(f"Offline toolchain export failed: {exc}") from exc
        finally:
            temporary.unlink(missing_ok=True)

    def inspect(self, bundle: Path) -> OfflineToolchainInspection:
        source = self._safe_bundle(bundle)
        try:
            before = source.stat()
            bundle_sha256, _size = sha256_regular_file(
                source,
                boundary=source.parent.resolve(strict=True),
                maximum_bytes=self.MAX_ARCHIVE_BYTES,
            )
            with zipfile.ZipFile(source) as archive:
                infos = archive.infolist()
                if not 2 <= len(infos) <= self.MAX_FILES + 1:
                    raise OfflineToolchainError("The offline toolchain member count is invalid")
                if infos[0].filename != self.MANIFEST_MEMBER:
                    raise OfflineToolchainError("The offline toolchain manifest is not first")
                self._validate_zip_infos(infos)
                manifest_bytes = self._read_member(
                    archive,
                    infos[0],
                    self.MAX_MANIFEST_BYTES,
                )
                try:
                    manifest = json.loads(manifest_bytes.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise OfflineToolchainError(
                        "The offline toolchain manifest is malformed"
                    ) from exc
                inspection = self._verify_manifest(manifest, bundle_sha256)
                expected_members = [self.MANIFEST_MEMBER, *map(self._member, inspection.files)]
                if [info.filename for info in infos] != expected_members:
                    raise OfflineToolchainError(
                        "The offline toolchain member order or inventory changed"
                    )
                for info, item in zip(infos[1:], inspection.files, strict=True):
                    if info.file_size != item.size_bytes:
                        raise OfflineToolchainError(
                            f"Offline tool size changed: {item.package}/{item.path}"
                        )
                    payload_digest = self._hash_member(archive, info, item.size_bytes)
                    if payload_digest != item.sha256:
                        raise OfflineToolchainError(
                            f"Offline tool hash changed: {item.package}/{item.path}"
                        )
            after = source.stat()
            if (
                not os.path.samestat(before, after)
                or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
            ):
                raise OfflineToolchainError("The offline toolchain kit changed during inspection")
            return inspection
        except OfflineToolchainError:
            raise
        except (OSError, ValueError, LocalStoreError, zipfile.BadZipFile, RuntimeError) as exc:
            raise OfflineToolchainError(f"Offline toolchain inspection failed: {exc}") from exc

    def import_bundle(
        self,
        bundle: Path,
        *,
        accepted_bundle_sha256: str,
        accepted_signer_fingerprint: str,
        validate_staging: Callable[[Path, tuple[str, ...]], bool],
        progress: Callable[[int, int], None] | None = None,
    ) -> OfflineToolchainImportReceipt:
        inspection = self.inspect(bundle)
        if (
            accepted_bundle_sha256 != inspection.bundle_sha256
            or accepted_signer_fingerprint != inspection.signer_fingerprint
        ):
            raise OfflineToolchainError(
                "The accepted offline kit identity no longer matches the inspected kit"
            )
        ensure_private_directory(self.managed_root, boundary=self.workspace)
        staging = self.managed_root / f".offline-import-{uuid4().hex}"
        backups = self.managed_root / f".offline-backup-{uuid4().hex}"
        ensure_private_directory(staging, boundary=self.workspace)
        total = inspection.content_bytes
        completed = 0
        try:
            source = self._safe_bundle(bundle)
            with zipfile.ZipFile(source) as archive:
                for info, item in zip(archive.infolist()[1:], inspection.files, strict=True):
                    target = staging / item.package / Path(item.path)
                    ensure_private_directory(target.parent, boundary=staging)
                    digest = hashlib.sha256()
                    written = 0
                    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
                    if os.name != "nt":
                        flags |= getattr(os, "O_NOFOLLOW", 0)
                    descriptor = os.open(target, flags, 0o600)
                    try:
                        with (
                            archive.open(info) as reader,
                            os.fdopen(descriptor, "wb", closefd=True) as output,
                        ):
                            while chunk := reader.read(self.CHUNK_SIZE):
                                written += len(chunk)
                                if written > item.size_bytes:
                                    raise OfflineToolchainError(
                                        f"Offline tool expanded beyond its manifest: {item.package}"
                                    )
                                digest.update(chunk)
                                output.write(chunk)
                                if progress is not None:
                                    progress(completed + written, total)
                            output.flush()
                            os.fsync(output.fileno())
                    except Exception:
                        with suppress(OSError):
                            os.close(descriptor)
                        raise
                    if written != item.size_bytes or digest.hexdigest() != item.sha256:
                        raise OfflineToolchainError(
                            f"Offline tool failed extraction verification: {item.package}"
                        )
                    if os.name != "nt":
                        target.chmod(0o700 if item.executable else 0o600)
                    completed += written
            current_bundle_sha256, _current_size = sha256_regular_file(
                source,
                boundary=source.parent.resolve(strict=True),
                maximum_bytes=self.MAX_ARCHIVE_BYTES,
            )
            if current_bundle_sha256 != accepted_bundle_sha256:
                raise OfflineToolchainError("The offline toolchain kit changed after confirmation")
            if validate_staging(staging, inspection.packages) is not True:
                raise OfflineToolchainError(
                    "The imported managed-source receipts did not pass Forge Arsenal validation"
                )
            receipt = self._import_receipt(inspection)
            self._install_transaction(
                staging,
                backups,
                inspection.packages,
                lambda: self._save_import_receipt(receipt),
            )
            if progress is not None:
                progress(total, total)
            return receipt
        except OfflineToolchainError:
            raise
        except (OSError, ValueError, LocalStoreError, zipfile.BadZipFile) as exc:
            raise OfflineToolchainError(f"Offline toolchain import failed: {exc}") from exc
        finally:
            shutil.rmtree(staging, ignore_errors=True)
            shutil.rmtree(backups, ignore_errors=True)

    def _identity(self) -> tuple[Ed25519PrivateKey, bytes]:
        ensure_private_directory(self.identity_root, boundary=self.workspace)
        key_path = self.identity_root / "offline-transfer-ed25519.key"
        if key_path.exists():
            raw = read_regular_bytes(
                key_path,
                boundary=self.workspace,
                maximum_bytes=32,
            )
            if len(raw) != 32:
                raise OfflineToolchainError("The offline transfer identity is invalid")
            try:
                private = Ed25519PrivateKey.from_private_bytes(raw)
            except ValueError as exc:
                raise OfflineToolchainError("The offline transfer identity is invalid") from exc
        else:
            private = Ed25519PrivateKey.generate()
            raw = private.private_bytes(
                serialization.Encoding.Raw,
                serialization.PrivateFormat.Raw,
                serialization.NoEncryption(),
            )
            atomic_write_bytes(
                key_path,
                raw,
                boundary=self.workspace,
                maximum_bytes=32,
            )
        public = private.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        return private, public

    def _signed_manifest(
        self,
        files: tuple[OfflineToolFile, ...],
        public: bytes,
        private: Ed25519PrivateKey,
    ) -> dict[str, object]:
        packages = tuple(dict.fromkeys(item.package for item in files))
        unsigned: dict[str, object] = {
            "format": "romverse.offline-toolchain-bundle",
            "schema_version": self.SCHEMA_VERSION,
            "created_at_epoch_ms": int(self.clock() * 1_000),
            "signer_fingerprint": hashlib.sha256(public).hexdigest(),
            "public_key_base64": base64.b64encode(public).decode("ascii"),
            "packages": list(packages),
            "files": [asdict(item) for item in files],
            "content_bytes": sum(item.size_bytes for item in files),
            "safety": {"phone_changed": False, "execution_authority": "none"},
            "signature_algorithm": "ed25519",
        }
        digest = self._digest(unsigned)
        signed = {**unsigned, "manifest_digest": digest}
        signature = base64.b64encode(private.sign(self.DOMAIN + self._canonical(signed))).decode(
            "ascii"
        )
        return {**signed, "signature": signature}

    def _verify_manifest(
        self,
        payload: object,
        bundle_sha256: str,
    ) -> OfflineToolchainInspection:
        expected = {
            "format",
            "schema_version",
            "created_at_epoch_ms",
            "signer_fingerprint",
            "public_key_base64",
            "packages",
            "files",
            "content_bytes",
            "safety",
            "signature_algorithm",
            "manifest_digest",
            "signature",
        }
        if not isinstance(payload, dict) or set(payload) != expected:
            raise OfflineToolchainError("The offline toolchain manifest shape is invalid")
        packages = payload["packages"]
        raw_files = payload["files"]
        safety = payload["safety"]
        if (
            payload["format"] != "romverse.offline-toolchain-bundle"
            or type(payload["schema_version"]) is not int
            or payload["schema_version"] != self.SCHEMA_VERSION
            or type(payload["created_at_epoch_ms"]) is not int
            or payload["created_at_epoch_ms"] <= 0
            or payload["signature_algorithm"] != "ed25519"
            or not isinstance(packages, list)
            or not isinstance(raw_files, list)
            or not isinstance(safety, dict)
            or safety != {"phone_changed": False, "execution_authority": "none"}
            or not 1 <= len(packages) <= self.MAX_PACKAGES
            or not 1 <= len(raw_files) <= self.MAX_FILES
            or any(not isinstance(name, str) for name in packages)
        ):
            raise OfflineToolchainError("The offline toolchain manifest contract is invalid")
        package_tuple = tuple(self._package_name(name) for name in packages)
        if len(package_tuple) != len(set(package_tuple)):
            raise OfflineToolchainError("The offline toolchain package list is ambiguous")
        file_fields = {"package", "path", "size_bytes", "sha256", "executable"}
        if any(not isinstance(item, dict) or set(item) != file_fields for item in raw_files):
            raise OfflineToolchainError("The offline toolchain file inventory is invalid")
        files = tuple(self._file_record(item, package_tuple) for item in raw_files)
        identities = tuple((item.package, item.path.casefold()) for item in files)
        if len(identities) != len(set(identities)):
            raise OfflineToolchainError("The offline toolchain contains duplicate paths")
        if tuple(sorted(files, key=lambda item: (item.package, item.path))) != files:
            raise OfflineToolchainError("The offline toolchain inventory order is invalid")
        if tuple(dict.fromkeys(item.package for item in files)) != package_tuple:
            raise OfflineToolchainError("The offline toolchain package coverage is invalid")
        content_bytes = sum(item.size_bytes for item in files)
        if (
            type(payload["content_bytes"]) is not int
            or payload["content_bytes"] != content_bytes
            or not 1 <= content_bytes <= self.MAX_CONTENT_BYTES
        ):
            raise OfflineToolchainError("The offline toolchain size claim is invalid")
        fingerprint = self._sha256_text(payload["signer_fingerprint"])
        manifest_digest = self._sha256_text(payload["manifest_digest"])
        if not isinstance(payload["public_key_base64"], str) or not isinstance(
            payload["signature"], str
        ):
            raise OfflineToolchainError("The offline toolchain signature is malformed")
        try:
            public = base64.b64decode(payload["public_key_base64"], validate=True)
            signature = base64.b64decode(payload["signature"], validate=True)
        except (ValueError, binascii.Error) as exc:
            raise OfflineToolchainError("The offline toolchain signature is malformed") from exc
        if len(public) != 32 or len(signature) != 64:
            raise OfflineToolchainError("The offline toolchain signature is malformed")
        if hashlib.sha256(public).hexdigest() != fingerprint:
            raise OfflineToolchainError("The offline toolchain signer fingerprint changed")
        unsigned = dict(payload)
        unsigned.pop("signature")
        digest_payload = dict(unsigned)
        digest_payload.pop("manifest_digest")
        if self._digest(digest_payload) != manifest_digest:
            raise OfflineToolchainError("The offline toolchain manifest digest changed")
        try:
            Ed25519PublicKey.from_public_bytes(public).verify(
                signature,
                self.DOMAIN + self._canonical(unsigned),
            )
        except (InvalidSignature, ValueError) as exc:
            raise OfflineToolchainError("The offline toolchain signature is invalid") from exc
        return OfflineToolchainInspection(
            self.SCHEMA_VERSION,
            bundle_sha256,
            manifest_digest,
            fingerprint,
            package_tuple,
            files,
            content_bytes,
            False,
            "none",
        )

    def _inventory(
        self,
        roots: tuple[Path, ...],
    ) -> tuple[tuple[OfflineToolFile, ...], dict[tuple[str, str], Path]]:
        records: list[OfflineToolFile] = []
        sources: dict[tuple[str, str], Path] = {}
        total = 0
        for root in roots:
            package = self._package_name(root.name)
            package_files = self._regular_package_files(root)
            if not any(
                path.name in {"managed-tool.romverse", "managed-package.romverse"}
                for path in package_files
            ):
                raise OfflineToolchainError(f"{package} has no managed-source receipt")
            for source in package_files:
                relative = source.relative_to(root).as_posix()
                before = source.stat()
                digest, size = sha256_regular_file(
                    source,
                    boundary=root,
                    maximum_bytes=self.MAX_FILE_BYTES,
                )
                after = source.stat()
                if (
                    not os.path.samestat(before, after)
                    or before.st_size != after.st_size
                    or before.st_mtime_ns != after.st_mtime_ns
                ):
                    raise OfflineToolchainError(f"{package} changed during inventory")
                total += size
                if total > self.MAX_CONTENT_BYTES:
                    raise OfflineToolchainError("The offline toolchain exceeds its size boundary")
                item = OfflineToolFile(
                    package,
                    relative,
                    size,
                    digest,
                    bool(before.st_mode & 0o111),
                )
                records.append(item)
                sources[(package, relative)] = source
                if len(records) > self.MAX_FILES:
                    raise OfflineToolchainError("The offline toolchain has too many files")
        records.sort(key=lambda item: (item.package, item.path))
        return tuple(records), sources

    def _regular_package_files(self, root: Path) -> tuple[Path, ...]:
        files: list[Path] = []
        directories = [root]
        visited = 0
        while directories:
            current = directories.pop()
            visited += 1
            if visited > self.MAX_DIRECTORIES:
                raise OfflineToolchainError(f"{root.name} has too many directories")
            try:
                entries = sorted(os.scandir(current), key=lambda entry: entry.name)
            except OSError as exc:
                raise OfflineToolchainError(f"{root.name} could not be inventoried") from exc
            for entry in entries:
                path = Path(entry.path)
                if entry.is_symlink():
                    raise OfflineToolchainError(f"{root.name} contains a symbolic link")
                if entry.is_dir(follow_symlinks=False):
                    directories.append(path)
                elif entry.is_file(follow_symlinks=False):
                    files.append(path)
                else:
                    raise OfflineToolchainError(f"{root.name} contains an unsupported file")
                if len(files) > self.MAX_FILES:
                    raise OfflineToolchainError("The offline toolchain has too many files")
        return tuple(sorted(files, key=lambda path: path.relative_to(root).as_posix()))

    def _package_roots(self, values: Iterable[Path]) -> tuple[Path, ...]:
        try:
            managed = self.managed_root.resolve(strict=True)
            details = self.managed_root.lstat()
        except OSError as exc:
            raise OfflineToolchainError("No managed Forge Arsenal packages are available") from exc
        if self.managed_root.is_symlink() or not stat.S_ISDIR(details.st_mode):
            raise OfflineToolchainError("The managed tool boundary is unsafe")
        roots = []
        for value in values:
            unresolved = Path(os.path.abspath(value))
            try:
                root_details = unresolved.lstat()
                resolved = unresolved.resolve(strict=True)
            except OSError as exc:
                raise OfflineToolchainError("A managed package is unavailable") from exc
            if (
                unresolved.is_symlink()
                or not stat.S_ISDIR(root_details.st_mode)
                or resolved.parent != managed
                or resolved in roots
            ):
                raise OfflineToolchainError("A managed package escaped its exact boundary")
            self._package_name(resolved.name)
            roots.append(resolved)
        roots.sort(key=lambda path: path.name)
        if not 1 <= len(roots) <= self.MAX_PACKAGES:
            raise OfflineToolchainError("Choose at least one verified managed package")
        return tuple(roots)

    def _install_transaction(
        self,
        staging: Path,
        backups: Path,
        packages: tuple[str, ...],
        commit: Callable[[], None],
    ) -> None:
        ensure_private_directory(backups, boundary=self.workspace)
        moved_old: list[str] = []
        installed: list[str] = []
        try:
            for package in packages:
                target = self.managed_root / package
                source = staging / package
                if not source.is_dir() or source.is_symlink():
                    raise OfflineToolchainError(f"Staged package is unavailable: {package}")
                if target.exists() or target.is_symlink():
                    details = target.lstat()
                    if target.is_symlink() or not stat.S_ISDIR(details.st_mode):
                        raise OfflineToolchainError(
                            f"Existing managed package boundary is unsafe: {package}"
                        )
                    os.replace(target, backups / package)
                    moved_old.append(package)
                os.replace(source, target)
                installed.append(package)
            commit()
        except Exception as exc:
            recovery_failed = False
            for package in reversed(installed):
                target = self.managed_root / package
                try:
                    os.replace(target, staging / package)
                except OSError:
                    recovery_failed = True
            for package in reversed(moved_old):
                try:
                    os.replace(backups / package, self.managed_root / package)
                except OSError:
                    recovery_failed = True
            if recovery_failed:
                raise OfflineToolchainError(
                    "Offline import stopped and its prior-package rollback needs manual review"
                ) from exc
            if isinstance(exc, OfflineToolchainError):
                raise
            raise OfflineToolchainError(f"Offline package transaction failed: {exc}") from exc

    def _import_receipt(
        self,
        inspection: OfflineToolchainInspection,
    ) -> OfflineToolchainImportReceipt:
        unsigned: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "imported_at_epoch_ms": int(self.clock() * 1_000),
            "bundle_sha256": inspection.bundle_sha256,
            "manifest_digest": inspection.manifest_digest,
            "signer_fingerprint": inspection.signer_fingerprint,
            "packages": list(inspection.packages),
            "file_count": len(inspection.files),
            "content_bytes": inspection.content_bytes,
            "source_receipts_validated": True,
            "phone_changed": False,
            "execution_authority": "none",
        }
        return OfflineToolchainImportReceipt(
            self.SCHEMA_VERSION,
            unsigned["imported_at_epoch_ms"],
            inspection.bundle_sha256,
            inspection.manifest_digest,
            inspection.signer_fingerprint,
            inspection.packages,
            len(inspection.files),
            inspection.content_bytes,
            True,
            False,
            "none",
            self._digest(unsigned),
        )

    def _save_import_receipt(self, receipt: OfflineToolchainImportReceipt) -> None:
        ensure_private_directory(self.receipt_root, boundary=self.workspace)
        atomic_write_json(
            self.receipt_root / f"{receipt.receipt_digest}.romverse-offline-import.json",
            {"format": "romverse.offline-toolchain-import", **asdict(receipt)},
            boundary=self.workspace,
            maximum_bytes=self.MAX_RECEIPT_BYTES,
        )

    def _export_paths(self, destination: Path) -> tuple[Path, Path]:
        target = Path(destination)
        if target.suffix.casefold() != self.BUNDLE_SUFFIX:
            raise OfflineToolchainError("Choose a .rvtools destination for the offline kit")
        try:
            parent_details = target.parent.lstat()
            parent = target.parent.resolve(strict=True)
            if target.parent.is_symlink() or not stat.S_ISDIR(parent_details.st_mode):
                raise OfflineToolchainError("The offline kit destination is unsafe")
            if target.exists() or target.is_symlink():
                target_details = target.lstat()
                if target.is_symlink() or not stat.S_ISREG(target_details.st_mode):
                    raise OfflineToolchainError("The offline kit destination is unsafe")
            temporary = parent / f".{uuid4().hex}.{target.name}"
            return target, temporary
        except OfflineToolchainError:
            raise
        except OSError as exc:
            raise OfflineToolchainError("The offline kit destination is unavailable") from exc

    def _safe_bundle(self, bundle: Path) -> Path:
        unresolved = Path(os.path.abspath(bundle))
        if unresolved.suffix.casefold() != self.BUNDLE_SUFFIX:
            raise OfflineToolchainError("Choose a ROMVERSE .rvtools offline kit")
        try:
            details = unresolved.lstat()
            resolved = unresolved.resolve(strict=True)
        except OSError as exc:
            raise OfflineToolchainError("The offline toolchain kit is unavailable") from exc
        if (
            unresolved.is_symlink()
            or not stat.S_ISREG(details.st_mode)
            or not 0 < details.st_size <= self.MAX_ARCHIVE_BYTES
        ):
            raise OfflineToolchainError("The offline toolchain kit is unsafe or too large")
        return resolved

    def _validate_zip_infos(self, infos: list[zipfile.ZipInfo]) -> None:
        names = [info.filename for info in infos]
        if len({name.casefold() for name in names}) != len(names):
            raise OfflineToolchainError("The offline toolchain contains duplicate members")
        for info in infos:
            path = PurePosixPath(info.filename)
            if (
                info.is_dir()
                or info.flag_bits & 0x1
                or info.compress_type not in self.ALLOWED_COMPRESSION
                or path.is_absolute()
                or ".." in path.parts
                or "\\" in info.filename
                or not info.filename
                or len(info.filename) > 1_024
                or info.file_size < 0
                or info.file_size > self.MAX_FILE_BYTES
            ):
                raise OfflineToolchainError("The offline toolchain contains an unsafe member")

    def _file_record(
        self,
        payload: dict[str, object],
        packages: tuple[str, ...],
    ) -> OfflineToolFile:
        package = self._package_name(payload["package"])
        path = payload["path"]
        if package not in packages or not isinstance(path, str):
            raise OfflineToolchainError("An offline tool file has invalid package identity")
        relative = PurePosixPath(path)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or "\\" in path
            or not relative.name
            or len(path) > 1_024
            or any(ord(character) < 32 or ord(character) == 127 for character in path)
        ):
            raise OfflineToolchainError("An offline tool file path is unsafe")
        size = payload["size_bytes"]
        executable = payload["executable"]
        digest = payload["sha256"]
        if (
            type(size) is not int
            or not 0 <= size <= self.MAX_FILE_BYTES
            or type(executable) is not bool
            or not isinstance(digest, str)
            or self.SHA256_PATTERN.fullmatch(digest) is None
        ):
            raise OfflineToolchainError("An offline tool file claim is invalid")
        return OfflineToolFile(package, path, size, digest, executable)

    def _read_member(
        self,
        archive: zipfile.ZipFile,
        info: zipfile.ZipInfo,
        maximum: int,
    ) -> bytes:
        with archive.open(info) as stream:
            payload = stream.read(maximum + 1)
        if len(payload) > maximum:
            raise OfflineToolchainError("An offline toolchain member is too large")
        return payload

    def _hash_member(
        self,
        archive: zipfile.ZipFile,
        info: zipfile.ZipInfo,
        expected_size: int,
    ) -> str:
        digest = hashlib.sha256()
        total = 0
        with archive.open(info) as stream:
            while chunk := stream.read(self.CHUNK_SIZE):
                total += len(chunk)
                if total > expected_size:
                    raise OfflineToolchainError("An offline tool expanded beyond its manifest")
                digest.update(chunk)
        if total != expected_size:
            raise OfflineToolchainError("An offline tool size does not match its manifest")
        return digest.hexdigest()

    @classmethod
    def _member(cls, item: OfflineToolFile) -> str:
        return f"packages/{item.package}/{item.path}"

    @classmethod
    def _zip_info(cls, name: str, executable: bool) -> zipfile.ZipInfo:
        info = zipfile.ZipInfo(name, date_time=cls.ZIP_TIMESTAMP)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.create_system = 3
        mode = stat.S_IFREG | (0o700 if executable else 0o600)
        info.external_attr = mode << 16
        return info

    @classmethod
    def _package_name(cls, value: object) -> str:
        if not isinstance(value, str) or cls.PACKAGE_PATTERN.fullmatch(value) is None:
            raise OfflineToolchainError("An offline toolchain package name is invalid")
        return value

    @classmethod
    def _sha256_text(cls, value: object) -> str:
        if not isinstance(value, str) or cls.SHA256_PATTERN.fullmatch(value) is None:
            raise OfflineToolchainError("An offline toolchain digest is invalid")
        return value

    @staticmethod
    def _safe_workspace(workspace: Path) -> Path:
        unresolved = Path(os.path.abspath(workspace))
        try:
            details = unresolved.lstat()
            resolved = unresolved.resolve(strict=True)
        except OSError as exc:
            raise OfflineToolchainError("The ROMVERSE workspace is unavailable") from exc
        if unresolved.is_symlink() or not stat.S_ISDIR(details.st_mode):
            raise OfflineToolchainError("The ROMVERSE workspace boundary is unsafe")
        return resolved

    @staticmethod
    def _canonical(value: object) -> bytes:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    @classmethod
    def _digest(cls, value: object) -> str:
        return hashlib.sha256(cls._canonical(value)).hexdigest()
