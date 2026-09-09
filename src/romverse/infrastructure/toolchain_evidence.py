from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from time import time

from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    ensure_private_directory,
    read_json_object,
    sha256_regular_file,
)
from romverse.infrastructure.tools import ToolStatus


class ToolchainEvidenceError(ValueError):
    """A toolchain inventory could not satisfy the evidence contract."""


@dataclass(frozen=True, slots=True)
class ToolExecutableEvidence:
    name: str
    state: str
    version: str
    executable_name: str
    origin: str
    source: str
    integrity_scope: str
    sha256: str
    size_bytes: int
    path_candidate_count: int
    path_conflict: bool
    detail: str


@dataclass(frozen=True, slots=True)
class ToolchainEvidenceManifest:
    schema_version: int
    host: str
    distribution: str
    scope: str
    required_tools: tuple[str, ...]
    captured_at_epoch_ms: int
    tools: tuple[ToolExecutableEvidence, ...]
    complete: bool
    conflict_count: int
    phone_changed: bool
    execution_authority: str
    manifest_digest: str

    def to_mapping(self) -> dict[str, object]:
        return {
            "format": "romverse.toolchain-evidence-manifest",
            **asdict(self),
        }


class ToolchainEvidenceService:
    """Create path-private, reproducible evidence for the exact active host tools.

    The exported manifest intentionally records executable names and fingerprints,
    not host-specific absolute paths. A managed receipt can prove the packaged
    source and executable hash; a system/SDK executable is truthfully limited to
    an observed local SHA-256 until its publisher/package proof is available.
    """

    SCHEMA_VERSION = 1
    MAX_TOOLS = 64
    MAX_RECORD_BYTES = 256 * 1024
    MAX_EXECUTABLE_BYTES = 1024 * 1024 * 1024
    MAX_PATH_ENTRIES = 256
    MAX_TEXT = 240
    SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
    NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._+()-]{0,79}")
    SCOPE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,119}")
    ABSOLUTE_PATH_TOKEN_PATTERN = re.compile(r"(^|[\s(=])((?:[A-Za-z]:[\\/]|/|\\\\)[^\s),;]*)")
    TRUSTED_MANAGED_SOURCE_PREFIXES = (
        "https://android.googlesource.com/platform/external/avb/",
        "https://dl.google.com/android/repository/",
        "https://dl.google.com/dl/android/maven2/com/android/tools/build/",
        "https://github.com/Rprop/aosp15_partition_tools",
        "https://github.com/ssut/payload-dumper-go/releases/download/",
    )

    def __init__(
        self,
        workspace: Path,
        host: str,
        distribution: str = "",
        *,
        clock: Callable[[], float] = time,
        path_value: str | None = None,
    ) -> None:
        unresolved = Path(os.path.abspath(workspace))
        try:
            details = unresolved.lstat()
            resolved = unresolved.resolve(strict=True)
        except OSError as exc:
            raise ToolchainEvidenceError("The ROMVERSE workspace is unavailable") from exc
        if (
            unresolved.is_symlink()
            or not stat.S_ISDIR(details.st_mode)
            or not resolved.is_dir()
            or resolved.is_symlink()
        ):
            raise ToolchainEvidenceError("The ROMVERSE workspace boundary is unsafe")
        self.workspace = resolved
        self.host = self._text(host, 64, "host")
        self.distribution = self._optional_text(distribution, 64)
        self.clock = clock
        self.path_value = os.environ.get("PATH", "") if path_value is None else path_value
        self.root = self.workspace / "config" / "toolchain" / "evidence"
        self.managed_root = self.workspace / "tools" / "downloads"

    def capture(
        self,
        statuses: Iterable[ToolStatus],
        *,
        required_tools: Iterable[str] = (),
        scope: str = "full-inventory",
    ) -> ToolchainEvidenceManifest:
        status_tuple = tuple(statuses)
        if not 1 <= len(status_tuple) <= self.MAX_TOOLS or any(
            not isinstance(item, ToolStatus)
            or type(item.available) is not bool
            or not isinstance(item.path, str)
            or not isinstance(item.version, str)
            or not isinstance(item.detail, str)
            for item in status_tuple
        ):
            raise ToolchainEvidenceError("The toolchain inventory is invalid")
        names = tuple(self._tool_name(item.name) for item in status_tuple)
        if len(names) != len(set(names)):
            raise ToolchainEvidenceError("The toolchain inventory contains duplicate names")
        required = tuple(self._tool_name(name) for name in required_tools)
        if len(required) != len(set(required)) or any(name not in names for name in required):
            raise ToolchainEvidenceError("The required tool scope is invalid")
        selected_scope = self._scope(scope)
        evidence = tuple(self._inspect_status(item) for item in status_tuple)
        by_name = {item.name: item for item in evidence}
        required_set = set(required) if required else set(names)
        complete = all(by_name[name].state == "verified" for name in required_set)
        unsigned: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "host": self.host,
            "distribution": self.distribution,
            "scope": selected_scope,
            "required_tools": list(required),
            "captured_at_epoch_ms": int(self.clock() * 1_000),
            "tools": [asdict(item) for item in evidence],
            "complete": complete,
            "conflict_count": sum(item.path_conflict for item in evidence),
            "phone_changed": False,
            "execution_authority": "none",
        }
        manifest = ToolchainEvidenceManifest(
            schema_version=self.SCHEMA_VERSION,
            host=self.host,
            distribution=self.distribution,
            scope=selected_scope,
            required_tools=required,
            captured_at_epoch_ms=unsigned["captured_at_epoch_ms"],
            tools=evidence,
            complete=complete,
            conflict_count=unsigned["conflict_count"],
            phone_changed=False,
            execution_authority="none",
            manifest_digest=self._digest(unsigned),
        )
        self._validate_manifest(manifest)
        return manifest

    def save_private(self, manifest: ToolchainEvidenceManifest) -> Path:
        self._validate_manifest(manifest)
        try:
            ensure_private_directory(self.root, boundary=self.workspace)
            destination = self.root / f"{manifest.manifest_digest}.romverse-toolchain.json"
            atomic_write_json(
                destination,
                manifest.to_mapping(),
                boundary=self.workspace,
                maximum_bytes=self.MAX_RECORD_BYTES,
            )
            return destination
        except (LocalStoreError, OSError, ValueError) as exc:
            raise ToolchainEvidenceError(f"Toolchain evidence could not be saved: {exc}") from exc

    def export(self, manifest: ToolchainEvidenceManifest, destination: Path) -> Path:
        """Write the exact path-private manifest to a user-selected destination."""

        self._validate_manifest(manifest)
        destination = Path(destination)
        if destination.name in {"", ".", ".."} or destination.suffix.casefold() != ".json":
            raise ToolchainEvidenceError("Choose a JSON destination for the toolchain manifest")
        try:
            unresolved_parent = destination.parent
            parent_details = unresolved_parent.lstat()
            boundary = unresolved_parent.resolve(strict=True)
            if (
                unresolved_parent.is_symlink()
                or not stat.S_ISDIR(parent_details.st_mode)
                or not boundary.is_dir()
            ):
                raise ToolchainEvidenceError("The export destination is unsafe")
            atomic_write_json(
                destination,
                manifest.to_mapping(),
                boundary=boundary,
                maximum_bytes=self.MAX_RECORD_BYTES,
            )
            return destination
        except ToolchainEvidenceError:
            raise
        except (LocalStoreError, OSError, ValueError) as exc:
            raise ToolchainEvidenceError(f"Toolchain manifest export failed: {exc}") from exc

    def load_private(self, manifest_digest: str) -> ToolchainEvidenceManifest:
        if self.SHA256_PATTERN.fullmatch(manifest_digest) is None:
            raise ToolchainEvidenceError("The toolchain manifest identity is invalid")
        try:
            payload = read_json_object(
                self.root / f"{manifest_digest}.romverse-toolchain.json",
                boundary=self.workspace,
                maximum_bytes=self.MAX_RECORD_BYTES,
            )
            manifest = self._from_mapping(payload)
        except ToolchainEvidenceError:
            raise
        except (LocalStoreError, OSError, ValueError, TypeError, KeyError) as exc:
            raise ToolchainEvidenceError(f"Toolchain evidence is unavailable: {exc}") from exc
        if manifest.manifest_digest != manifest_digest:
            raise ToolchainEvidenceError("The toolchain manifest identity changed")
        return manifest

    def _inspect_status(self, status: ToolStatus) -> ToolExecutableEvidence:
        name = self._tool_name(status.name)
        version = self._private_observation(status.version, 160)
        detail = self._private_observation(status.detail, self.MAX_TEXT)
        if not status.available:
            return ToolExecutableEvidence(
                name,
                "missing",
                version,
                "",
                "unavailable",
                "not-resolved",
                "none",
                "",
                0,
                0,
                False,
                detail or "The executable did not pass its version/start check.",
            )
        if not status.path:
            raise ToolchainEvidenceError(f"{name} is marked ready without an executable path")
        original = Path(status.path)
        try:
            resolved = original.resolve(strict=True)
            before = resolved.stat()
            if not stat.S_ISREG(before.st_mode):
                raise ToolchainEvidenceError(f"{name} does not resolve to a regular executable")
            digest, size = sha256_regular_file(
                resolved,
                boundary=resolved.parent,
                maximum_bytes=self.MAX_EXECUTABLE_BYTES,
            )
            after = resolved.stat()
        except ToolchainEvidenceError:
            raise
        except (LocalStoreError, OSError, ValueError) as exc:
            raise ToolchainEvidenceError(f"{name} could not be fingerprinted: {exc}") from exc
        if (
            not os.path.samestat(before, after)
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
        ):
            raise ToolchainEvidenceError(f"{name} changed while it was fingerprinted")
        origin = self._origin(resolved)
        source, integrity_scope = self._source_and_scope(resolved, digest, origin)
        candidates = self._path_candidates(original.name, resolved)
        return ToolExecutableEvidence(
            name,
            "verified",
            version or "version not reported",
            self._text(resolved.name, 160, "executable name"),
            origin,
            source,
            integrity_scope,
            digest,
            size,
            len(candidates),
            len(candidates) > 1,
            detail or "Version/start check and exact executable SHA-256 completed.",
        )

    def _origin(self, path: Path) -> str:
        try:
            path.relative_to(self.managed_root.resolve())
        except (OSError, ValueError):
            normalized = tuple(part.casefold() for part in path.parts)
            if "build-tools" in normalized:
                return "android-sdk-build-tools"
            if path == Path(os.path.realpath(os.sys.executable)):
                return "python-runtime"
            return "host-installation"
        return "romverse-managed"

    def _source_and_scope(self, path: Path, digest: str, origin: str) -> tuple[str, str]:
        if origin == "romverse-managed":
            source = self._verified_managed_source(path, digest)
            if source:
                return source, "managed-source-and-executable"
            return "ROMVERSE managed receipt unavailable", "observed-executable-sha256"
        if origin == "android-sdk-build-tools":
            return "Local Android SDK Build Tools", "observed-executable-sha256"
        if origin == "python-runtime":
            return "ROMVERSE Python runtime", "observed-executable-sha256"
        return "Local host installation", "observed-executable-sha256"

    def _verified_managed_source(self, path: Path, digest: str) -> str:
        candidates = (
            path.with_name(path.name + ".romverse"),
            path.parent / "managed-tool.romverse",
        )
        for receipt_path in candidates:
            payload = self._read_small_receipt(receipt_path)
            if payload is None:
                continue
            if (
                payload.get("format") == "romverse.managed-tool"
                and payload.get("sha256") == digest
                and payload.get("executable", path.name) == path.name
                and self._official_source(payload.get("source"))
            ):
                return str(payload["source"])[: self.MAX_TEXT]
        root = self.managed_root.resolve()
        current = path.parent
        for _depth in range(5):
            if current == root or root not in current.parents:
                break
            receipt_path = current / "managed-package.romverse"
            payload = self._read_small_receipt(receipt_path)
            if payload is not None and payload.get("format") == "romverse.managed-package":
                files = payload.get("files")
                try:
                    relative = str(path.relative_to(current))
                except ValueError:
                    return ""
                if (
                    isinstance(files, dict)
                    and files.get(relative) == digest
                    and self._official_source(payload.get("source"))
                ):
                    return str(payload["source"])[: self.MAX_TEXT]
            current = current.parent
        return ""

    def _read_small_receipt(self, path: Path) -> dict[str, object] | None:
        try:
            resolved = path.resolve(strict=True)
            if path.is_symlink() or not resolved.is_file() or resolved.stat().st_size > 64 * 1024:
                return None
            resolved.relative_to(self.managed_root.resolve())
            payload = json.loads(resolved.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else None
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError):
            return None

    @classmethod
    def _official_source(cls, value: object) -> bool:
        return (
            isinstance(value, str)
            and len(value) <= 500
            and any(value.startswith(prefix) for prefix in cls.TRUSTED_MANAGED_SOURCE_PREFIXES)
        )

    def _path_candidates(self, executable_name: str, active: Path) -> tuple[Path, ...]:
        candidates: list[Path] = [active]
        directories = self.path_value.split(os.pathsep)
        if len(directories) > self.MAX_PATH_ENTRIES:
            raise ToolchainEvidenceError("PATH contains too many entries to audit safely")
        names = {executable_name}
        if self.host.casefold() == "windows" and not executable_name.casefold().endswith(".exe"):
            names.add(f"{executable_name}.exe")
        for directory in directories:
            if not directory or "\x00" in directory:
                continue
            for name in names:
                candidate = Path(directory) / name
                try:
                    resolved = candidate.resolve(strict=True)
                    if resolved.is_file() and resolved not in candidates:
                        candidates.append(resolved)
                except (OSError, RuntimeError):
                    continue
        return tuple(candidates)

    def _from_mapping(self, payload: dict[str, object]) -> ToolchainEvidenceManifest:
        expected = {"format", *(field.name for field in fields(ToolchainEvidenceManifest))}
        if set(payload) != expected or payload.get("format") != (
            "romverse.toolchain-evidence-manifest"
        ):
            raise ToolchainEvidenceError("The toolchain manifest has an invalid shape")
        raw_tools = payload.get("tools")
        raw_required = payload.get("required_tools")
        if not isinstance(raw_tools, list) or not isinstance(raw_required, list):
            raise ToolchainEvidenceError("The toolchain manifest collections are invalid")
        if any(not isinstance(item, str) for item in raw_required):
            raise ToolchainEvidenceError("The required tool names are invalid")
        tool_fields = {field.name for field in fields(ToolExecutableEvidence)}
        if any(not isinstance(item, dict) or set(item) != tool_fields for item in raw_tools):
            raise ToolchainEvidenceError("A toolchain manifest item has an invalid shape")
        tools = tuple(ToolExecutableEvidence(**item) for item in raw_tools)
        manifest = ToolchainEvidenceManifest(
            schema_version=self._strict_int(payload["schema_version"]),
            host=self._required_string(payload["host"]),
            distribution=self._required_string(payload["distribution"]),
            scope=self._required_string(payload["scope"]),
            required_tools=tuple(raw_required),
            captured_at_epoch_ms=self._strict_int(payload["captured_at_epoch_ms"]),
            tools=tools,
            complete=self._strict_bool(payload["complete"]),
            conflict_count=self._strict_int(payload["conflict_count"]),
            phone_changed=self._strict_bool(payload["phone_changed"]),
            execution_authority=self._required_string(payload["execution_authority"]),
            manifest_digest=self._required_string(payload["manifest_digest"]),
        )
        self._validate_manifest(manifest)
        return manifest

    def _validate_manifest(self, manifest: ToolchainEvidenceManifest) -> None:
        if not isinstance(manifest, ToolchainEvidenceManifest):
            raise ToolchainEvidenceError("The toolchain manifest is invalid")
        names = tuple(item.name for item in manifest.tools)
        if (
            type(manifest.schema_version) is not int
            or manifest.schema_version != self.SCHEMA_VERSION
            or not 1 <= len(manifest.tools) <= self.MAX_TOOLS
            or len(names) != len(set(names))
            or any(name not in names for name in manifest.required_tools)
            or len(manifest.required_tools) != len(set(manifest.required_tools))
            or type(manifest.captured_at_epoch_ms) is not int
            or manifest.captured_at_epoch_ms <= 0
            or type(manifest.complete) is not bool
            or type(manifest.conflict_count) is not int
            or manifest.conflict_count != sum(item.path_conflict for item in manifest.tools)
            or manifest.phone_changed is not False
            or manifest.execution_authority != "none"
            or self.SHA256_PATTERN.fullmatch(manifest.manifest_digest) is None
        ):
            raise ToolchainEvidenceError("The toolchain manifest violates its safety contract")
        self._text(manifest.host, 64, "host")
        self._optional_text(manifest.distribution, 64)
        self._scope(manifest.scope)
        for name in manifest.required_tools:
            self._tool_name(name)
        for item in manifest.tools:
            self._validate_item(item)
        by_name = {item.name: item for item in manifest.tools}
        required = set(manifest.required_tools) if manifest.required_tools else set(names)
        if manifest.complete != all(by_name[name].state == "verified" for name in required):
            raise ToolchainEvidenceError("The toolchain completion claim is inconsistent")
        unsigned = asdict(manifest)
        digest = unsigned.pop("manifest_digest")
        if digest != self._digest(unsigned):
            raise ToolchainEvidenceError("The toolchain manifest failed integrity verification")

    def _validate_item(self, item: ToolExecutableEvidence) -> None:
        if not isinstance(item, ToolExecutableEvidence):
            raise ToolchainEvidenceError("A toolchain evidence item is invalid")
        self._tool_name(item.name)
        self._optional_text(item.version, 160)
        self._optional_text(item.executable_name, 160)
        self._optional_text(item.source, self.MAX_TEXT)
        self._optional_text(item.detail, self.MAX_TEXT)
        if (
            item.state not in {"verified", "missing"}
            or item.origin
            not in {
                "romverse-managed",
                "android-sdk-build-tools",
                "python-runtime",
                "host-installation",
                "unavailable",
            }
            or item.integrity_scope
            not in {"managed-source-and-executable", "observed-executable-sha256", "none"}
            or type(item.size_bytes) is not int
            or type(item.path_candidate_count) is not int
            or type(item.path_conflict) is not bool
            or item.path_conflict != (item.path_candidate_count > 1)
        ):
            raise ToolchainEvidenceError("A toolchain evidence item violates its contract")
        if item.state == "verified":
            if (
                not item.executable_name
                or self.SHA256_PATTERN.fullmatch(item.sha256) is None
                or not 0 < item.size_bytes <= self.MAX_EXECUTABLE_BYTES
                or not 1 <= item.path_candidate_count <= self.MAX_PATH_ENTRIES + 1
                or item.integrity_scope == "none"
            ):
                raise ToolchainEvidenceError("Verified tool evidence is incomplete")
        elif (
            any((item.executable_name, item.sha256, item.size_bytes, item.path_candidate_count))
            or item.path_conflict
            or item.origin != "unavailable"
            or item.integrity_scope != "none"
        ):
            raise ToolchainEvidenceError("Missing tool evidence claims executable proof")

    @classmethod
    def _tool_name(cls, value: object) -> str:
        if not isinstance(value, str) or cls.NAME_PATTERN.fullmatch(value) is None:
            raise ToolchainEvidenceError("A tool name is invalid")
        return value

    @classmethod
    def _scope(cls, value: object) -> str:
        if not isinstance(value, str) or cls.SCOPE_PATTERN.fullmatch(value) is None:
            raise ToolchainEvidenceError("The toolchain scope is invalid")
        return value

    @staticmethod
    def _strict_int(value: object) -> int:
        if type(value) is not int:
            raise ToolchainEvidenceError("The toolchain manifest expected an integer")
        return value

    @staticmethod
    def _strict_bool(value: object) -> bool:
        if type(value) is not bool:
            raise ToolchainEvidenceError("The toolchain manifest expected a Boolean")
        return value

    @staticmethod
    def _required_string(value: object) -> str:
        if not isinstance(value, str):
            raise ToolchainEvidenceError("The toolchain manifest expected text")
        return value

    @staticmethod
    def _text(value: object, maximum: int, label: str) -> str:
        if (
            not isinstance(value, str)
            or not 1 <= len(value) <= maximum
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            raise ToolchainEvidenceError(f"The toolchain {label} is invalid")
        return value

    @staticmethod
    def _optional_text(value: object, maximum: int) -> str:
        if (
            not isinstance(value, str)
            or len(value) > maximum
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            raise ToolchainEvidenceError("Toolchain text is invalid")
        return value

    @classmethod
    def _private_observation(cls, value: object, maximum: int) -> str:
        observed = cls._optional_text(value, maximum)
        redacted = cls.ABSOLUTE_PATH_TOKEN_PATTERN.sub(
            lambda match: f"{match.group(1)}[local-path-omitted]",
            observed,
        )
        return cls._optional_text(redacted, maximum)

    @staticmethod
    def _digest(payload: object) -> str:
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
