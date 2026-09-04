from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    ensure_private_directory,
    read_json_object,
    sha256_regular_file,
)
from romverse.infrastructure.toolchain_evidence import (
    ToolchainEvidenceManifest,
    ToolExecutableEvidence,
)


class VersionedToolchainError(ValueError):
    """An exact managed executable could not enter its immutable version slot."""


@dataclass(frozen=True, slots=True)
class VersionedToolReceipt:
    schema_version: int
    tool_name: str
    executable_name: str
    source_sha256: str
    size_bytes: int
    version: str
    source: str
    integrity_scope: str
    phone_changed: bool
    execution_authority: str
    receipt_digest: str


class VersionedToolchainStore:
    """Preserve exact managed executable bytes in content-addressed build slots."""

    SCHEMA_VERSION = 1
    RECEIPT_NAME = "versioned-tool.romverse"
    MAX_RECEIPT_BYTES = 64 * 1024
    MAX_EXECUTABLE_BYTES = 1024 * 1024 * 1024
    CHUNK_SIZE = 4 * 1024 * 1024
    SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
    EXECUTABLE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,159}")

    def __init__(self, workspace: Path) -> None:
        unresolved = Path(os.path.abspath(workspace))
        try:
            details = unresolved.lstat()
            resolved = unresolved.resolve(strict=True)
        except OSError as exc:
            raise VersionedToolchainError("The ROMVERSE workspace is unavailable") from exc
        if unresolved.is_symlink() or not stat.S_ISDIR(details.st_mode):
            raise VersionedToolchainError("The ROMVERSE workspace boundary is unsafe")
        self.workspace = resolved
        self.managed_root = self.workspace / "tools" / "downloads"
        self.versioned_root = self.workspace / "tools" / "versioned"

    def isolate(
        self,
        tools: dict[str, Path],
        manifest: ToolchainEvidenceManifest,
    ) -> dict[str, Path]:
        if (
            not isinstance(manifest, ToolchainEvidenceManifest)
            or not manifest.complete
            or manifest.phone_changed
            or manifest.execution_authority != "none"
        ):
            raise VersionedToolchainError("The exact toolchain manifest is not isolatable")
        evidence = {item.name: item for item in manifest.tools}
        if set(tools) != set(manifest.required_tools) or set(tools) != set(evidence):
            raise VersionedToolchainError("The exact toolchain isolation scope is inconsistent")
        isolated: dict[str, Path] = {}
        for name, path in sorted(tools.items()):
            item = evidence[name]
            if item.origin == "romverse-managed":
                if item.integrity_scope != "managed-source-and-executable":
                    raise VersionedToolchainError(
                        f"Managed build tool lacks a validated source receipt: {name}"
                    )
                slot = self._slot(item)
                if slot.exists() or slot.is_symlink():
                    self._verify_slot(slot, item)
                    isolated[name] = slot / item.executable_name
                else:
                    isolated[name] = self._snapshot(self._exact_source(path, item), item)
            else:
                isolated[name] = self._exact_source(path, item)
        return isolated

    def _snapshot(self, source: Path, item: ToolExecutableEvidence) -> Path:
        slot = self._slot(item)
        executable = slot / item.executable_name
        if slot.exists() or slot.is_symlink():
            self._verify_slot(slot, item)
            return executable
        parent = slot.parent
        staging = parent / f".{item.sha256}.{uuid4().hex}.staging"
        try:
            ensure_private_directory(parent, boundary=self.workspace)
            ensure_private_directory(staging, boundary=self.workspace)
            target = staging / item.executable_name
            before = source.stat()
            digest = hashlib.sha256()
            copied = 0
            input_flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
            output_flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
            if os.name != "nt":
                input_flags |= getattr(os, "O_NOFOLLOW", 0)
                output_flags |= getattr(os, "O_NOFOLLOW", 0)
            input_descriptor = os.open(source, input_flags)
            try:
                output_descriptor = os.open(target, output_flags, 0o500)
                try:
                    with os.fdopen(input_descriptor, "rb", closefd=True) as reader, os.fdopen(
                        output_descriptor,
                        "wb",
                        closefd=True,
                    ) as writer:
                        while chunk := reader.read(self.CHUNK_SIZE):
                            copied += len(chunk)
                            if copied > item.size_bytes:
                                raise VersionedToolchainError(
                                    f"Managed build tool changed during isolation: {item.name}"
                                )
                            digest.update(chunk)
                            writer.write(chunk)
                        writer.flush()
                        os.fsync(writer.fileno())
                except Exception:
                    with suppress(OSError):
                        os.close(output_descriptor)
                    raise
            except Exception:
                with suppress(OSError):
                    os.close(input_descriptor)
                raise
            after = source.stat()
            if (
                copied != item.size_bytes
                or digest.hexdigest() != item.sha256
                or not os.path.samestat(before, after)
                or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
            ):
                raise VersionedToolchainError(
                    f"Managed build tool changed during isolation: {item.name}"
                )
            if os.name != "nt":
                target.chmod(0o500)
            receipt = self._receipt(item)
            atomic_write_json(
                staging / self.RECEIPT_NAME,
                {"format": "romverse.versioned-tool", **asdict(receipt)},
                boundary=self.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
            try:
                os.replace(staging, slot)
            except OSError:
                if not slot.exists():
                    raise
            self._verify_slot(slot, item)
            return executable
        except VersionedToolchainError:
            raise
        except (OSError, ValueError, LocalStoreError) as exc:
            raise VersionedToolchainError(
                f"Managed build tool could not be isolated: {item.name}: {exc}"
            ) from exc
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def _verify_slot(self, slot: Path, item: ToolExecutableEvidence) -> None:
        try:
            ensure_private_directory(slot.parent, boundary=self.workspace)
            details = slot.lstat()
            if slot.is_symlink() or not stat.S_ISDIR(details.st_mode):
                raise VersionedToolchainError("A versioned tool slot is unsafe")
            entries = tuple(sorted(path.name for path in slot.iterdir()))
            if entries != tuple(sorted((item.executable_name, self.RECEIPT_NAME))):
                raise VersionedToolchainError("A versioned tool slot contains unexpected files")
            executable = slot / item.executable_name
            executable_details = executable.lstat()
            if executable.is_symlink() or not stat.S_ISREG(executable_details.st_mode):
                raise VersionedToolchainError("A versioned executable is unsafe")
            digest, size = sha256_regular_file(
                executable,
                boundary=slot,
                maximum_bytes=self.MAX_EXECUTABLE_BYTES,
            )
            payload = read_json_object(
                slot / self.RECEIPT_NAME,
                boundary=self.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
            expected_fields = {"format", *(field.name for field in VersionedToolReceipt.__dataclass_fields__.values())}
            if set(payload) != expected_fields or payload.pop("format") != "romverse.versioned-tool":
                raise VersionedToolchainError("A versioned tool receipt has an invalid shape")
            receipt = VersionedToolReceipt(**payload)
            self._validate_receipt(receipt, item)
            if digest != item.sha256 or size != item.size_bytes:
                raise VersionedToolchainError("A versioned tool no longer matches its exact hash")
        except VersionedToolchainError:
            raise
        except (OSError, TypeError, ValueError, LocalStoreError) as exc:
            raise VersionedToolchainError(f"A versioned tool slot is invalid: {exc}") from exc

    def _receipt(self, item: ToolExecutableEvidence) -> VersionedToolReceipt:
        unsigned: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "tool_name": item.name,
            "executable_name": item.executable_name,
            "source_sha256": item.sha256,
            "size_bytes": item.size_bytes,
            "version": item.version,
            "source": item.source,
            "integrity_scope": item.integrity_scope,
            "phone_changed": False,
            "execution_authority": "none",
        }
        return VersionedToolReceipt(
            self.SCHEMA_VERSION,
            item.name,
            item.executable_name,
            item.sha256,
            item.size_bytes,
            item.version,
            item.source,
            item.integrity_scope,
            False,
            "none",
            self._digest(unsigned),
        )

    def _validate_receipt(
        self,
        receipt: VersionedToolReceipt,
        item: ToolExecutableEvidence,
    ) -> None:
        unsigned = asdict(receipt)
        digest = unsigned.pop("receipt_digest")
        if (
            type(receipt.schema_version) is not int
            or receipt.schema_version != self.SCHEMA_VERSION
            or receipt.tool_name != item.name
            or receipt.executable_name != item.executable_name
            or receipt.source_sha256 != item.sha256
            or type(receipt.size_bytes) is not int
            or receipt.size_bytes != item.size_bytes
            or receipt.version != item.version
            or receipt.source != item.source
            or receipt.integrity_scope != "managed-source-and-executable"
            or receipt.phone_changed is not False
            or receipt.execution_authority != "none"
            or not isinstance(digest, str)
            or self.SHA256_PATTERN.fullmatch(digest) is None
            or digest != self._digest(unsigned)
        ):
            raise VersionedToolchainError("A versioned tool receipt failed verification")

    def _exact_source(self, path: Path, item: ToolExecutableEvidence) -> Path:
        try:
            source = Path(path).resolve(strict=True)
            details = source.lstat()
            if source.is_symlink() or not stat.S_ISREG(details.st_mode):
                raise VersionedToolchainError(f"Build tool is not a regular file: {item.name}")
            if source.name != item.executable_name:
                raise VersionedToolchainError(f"Build tool identity changed: {item.name}")
            digest, size = sha256_regular_file(
                source,
                boundary=source.parent,
                maximum_bytes=self.MAX_EXECUTABLE_BYTES,
            )
        except VersionedToolchainError:
            raise
        except (OSError, ValueError, LocalStoreError) as exc:
            raise VersionedToolchainError(f"Build tool is unavailable: {item.name}") from exc
        if digest != item.sha256 or size != item.size_bytes:
            raise VersionedToolchainError(f"Build tool changed before isolation: {item.name}")
        return source

    def _slot(self, item: ToolExecutableEvidence) -> Path:
        if (
            self.SHA256_PATTERN.fullmatch(item.sha256) is None
            or self.EXECUTABLE_PATTERN.fullmatch(item.executable_name) is None
        ):
            raise VersionedToolchainError("The versioned tool identity is invalid")
        slug = re.sub(r"[^a-z0-9]+", "-", item.name.casefold()).strip("-")[:48]
        if not slug:
            raise VersionedToolchainError("The versioned tool name is invalid")
        identity = hashlib.sha256(item.name.encode("utf-8")).hexdigest()[:8]
        return self.versioned_root / f"{slug}-{identity}" / item.sha256

    @staticmethod
    def _digest(payload: object) -> str:
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
