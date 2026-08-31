from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import uuid4

from romverse.infrastructure.local_store import atomic_write_json, read_json_object
from romverse.infrastructure.tools import ToolStatus


@dataclass(frozen=True, slots=True)
class TypedLocalActionEvidence:
    local_action_id: str
    receipt_digest: str
    evidence_ref: str
    evidence_format: str


class LocalActionEvidenceVerifier(Protocol):
    def verify(self, evidence: TypedLocalActionEvidence) -> bool: ...


@dataclass(frozen=True, slots=True)
class ToolchainVerificationReceipt:
    schema_version: int
    receipt_id: str
    created_at: str
    required_tools: tuple[str, ...]
    tools: tuple[dict[str, object], ...]
    status: str
    authority: str
    phone_changed: bool
    receipt_digest: str
    evidence_ref: str


class ToolchainVerificationStore:
    FORMAT = "romverse.toolchain-verification"
    MAX_RECEIPT_BYTES = 128 * 1024
    MAX_TOOLS = 32

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve()
        self.root = self.workspace / "knowledge" / "toolchain-verification"

    def record(
        self,
        statuses: tuple[ToolStatus, ...],
        required_names: tuple[str, ...],
    ) -> ToolchainVerificationReceipt:
        required = tuple(dict.fromkeys(required_names))
        if not 1 <= len(required) <= self.MAX_TOOLS or any(
            not _label(name, 80) for name in required
        ):
            raise ValueError("Toolchain verification has an invalid requirement set")
        by_name = {status.name: status for status in statuses}
        tools = []
        for name in required:
            status = by_name.get(name)
            if status is None or not status.available or not status.path:
                raise ValueError(f"Required tool has no successful verification: {name}")
            try:
                executable = Path(status.path).resolve(strict=True)
            except OSError as exc:
                raise ValueError(f"Verified tool is unavailable: {name}") from exc
            if not executable.is_file():
                raise ValueError(f"Verified tool is not a regular file: {name}")
            tools.append(
                {
                    "name": name,
                    "path": str(executable),
                    "sha256": _sha256_file(executable),
                    "version": _text(status.version, 120),
                }
            )
        receipt_id = uuid4().hex
        evidence_ref = (
            (self.root / f"{receipt_id}.romverse-toolchain-verification.json")
            .relative_to(self.workspace)
            .as_posix()
        )
        unsigned: dict[str, object] = {
            "schema_version": 1,
            "receipt_id": receipt_id,
            "created_at": datetime.now(UTC).isoformat(),
            "required_tools": list(required),
            "tools": tools,
            "status": "verified",
            "authority": "host-toolchain-verification-only",
            "phone_changed": False,
        }
        digest = _digest(unsigned)
        receipt = ToolchainVerificationReceipt(
            1,
            receipt_id,
            str(unsigned["created_at"]),
            required,
            tuple(tools),
            "verified",
            "host-toolchain-verification-only",
            False,
            digest,
            evidence_ref,
        )
        atomic_write_json(
            self.workspace / evidence_ref,
            {self.FORMAT_KEY: self.FORMAT, **unsigned, "receipt_digest": digest},
            boundary=self.workspace,
            maximum_bytes=self.MAX_RECEIPT_BYTES,
        )
        return receipt

    FORMAT_KEY = "format"


class WorkspaceLocalActionEvidenceVerifier:
    """Revalidate a typed local action receipt without executing an operation."""

    MAX_EVIDENCE_BYTES = 512 * 1024
    _ACTION_FORMATS = {
        "refresh-adb-evidence": {"romverse.adb-host-repair"},
        "verify-platform-tools": {ToolchainVerificationStore.FORMAT},
        "inspect-payload-source": {"romverse.ota-source-blueprint"},
        "classify-ota-source": {"romverse.ota-source-blueprint"},
        "inspect-avb-topology": {"romverse.avb-topology"},
    }

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve()

    def verify(self, evidence: TypedLocalActionEvidence) -> bool:
        if (
            evidence.local_action_id not in self._ACTION_FORMATS
            or not _sha256_value(evidence.receipt_digest)
            or evidence.evidence_format not in self._ACTION_FORMATS[evidence.local_action_id]
        ):
            return False
        path = self._path(evidence.evidence_ref)
        if path is None:
            return False
        try:
            payload = read_json_object(
                path,
                boundary=self.workspace,
                maximum_bytes=self.MAX_EVIDENCE_BYTES,
            )
            if payload.get("format") != evidence.evidence_format:
                return False
            if evidence.local_action_id == "refresh-adb-evidence":
                return self._host_receipt(payload, evidence.receipt_digest)
            if evidence.local_action_id == "verify-platform-tools":
                return self._toolchain_receipt(payload, evidence.receipt_digest)
            if evidence.local_action_id in {"inspect-payload-source", "classify-ota-source"}:
                return self._ota_blueprint(payload, evidence.receipt_digest, path)
            if evidence.local_action_id == "inspect-avb-topology":
                return self._avb_receipt(payload, evidence.receipt_digest, path)
        except (OSError, TypeError, ValueError, KeyError):
            return False
        return False

    def _path(self, value: str) -> Path | None:
        if not isinstance(value, str) or not 1 <= len(value) <= 1_024:
            return None
        relative = PurePosixPath(value)
        if relative.is_absolute() or ".." in relative.parts or not relative.name:
            return None
        path = self.workspace.joinpath(*relative.parts)
        try:
            resolved_parent = path.parent.resolve(strict=True)
        except OSError:
            return None
        if not resolved_parent.is_relative_to(self.workspace) or path.is_symlink():
            return None
        return path

    @staticmethod
    def _host_receipt(payload: dict[str, object], digest: str) -> bool:
        expected_keys = {
            "format",
            "schema_version",
            "receipt_id",
            "recorded_at",
            "plan_digest",
            "mode",
            "status",
            "steps",
            "device_commands_executed",
            "phone_changed",
            "execution_authority",
            "bootloader_relock",
            "receipt_digest",
        }
        unsigned = dict(payload)
        expected = str(unsigned.pop("receipt_digest", ""))
        steps = unsigned.get("steps")
        if (
            set(payload) != expected_keys
            or unsigned.get("schema_version") != 1
            or not _hex_value(unsigned.get("receipt_id"), 32)
            or not _timestamp(unsigned.get("recorded_at"))
            or not _sha256_value(unsigned.get("plan_digest"))
            or unsigned.get("mode") not in {"start", "restart"}
            or unsigned.get("status") != "succeeded"
            or unsigned.get("device_commands_executed") is not False
            or unsigned.get("phone_changed") is not False
            or unsigned.get("execution_authority") != "host-adb-daemon-only"
            or unsigned.get("bootloader_relock") != "never"
            or not isinstance(steps, list)
            or not 2 <= len(steps) <= 3
            or expected != digest
            or _digest(unsigned) != digest
        ):
            return False
        labels = [step.get("step") for step in steps if isinstance(step, dict)]
        return labels[-2:] == ["start-server", "verify-devices"] and all(
            isinstance(step, dict)
            and set(step) == {"step", "returncode", "timed_out", "output_digest"}
            and type(step.get("returncode")) is int
            and step.get("returncode") == 0
            and step.get("timed_out") is False
            and _sha256_value(step.get("output_digest"))
            for step in steps[-2:]
        )

    @staticmethod
    def _toolchain_receipt(payload: dict[str, object], digest: str) -> bool:
        expected_keys = {
            "format",
            "schema_version",
            "receipt_id",
            "created_at",
            "required_tools",
            "tools",
            "status",
            "authority",
            "phone_changed",
            "receipt_digest",
        }
        unsigned = dict(payload)
        expected = str(unsigned.pop("receipt_digest", ""))
        unsigned.pop("format", None)
        required = unsigned.get("required_tools")
        tools = unsigned.get("tools")
        if (
            set(payload) != expected_keys
            or unsigned.get("schema_version") != 1
            or not _hex_value(unsigned.get("receipt_id"), 32)
            or not _timestamp(unsigned.get("created_at"))
            or unsigned.get("status") != "verified"
            or unsigned.get("authority") != "host-toolchain-verification-only"
            or unsigned.get("phone_changed") is not False
            or not isinstance(required, list)
            or not isinstance(tools, list)
            or not 1 <= len(required) == len(tools) <= ToolchainVerificationStore.MAX_TOOLS
            or len(set(required)) != len(required)
            or expected != digest
            or _digest(unsigned) != digest
        ):
            return False
        seen = set()
        for item in tools:
            if not isinstance(item, dict) or set(item) != {"name", "path", "sha256", "version"}:
                return False
            name = item.get("name")
            if name not in required or name in seen or not _label(name, 80):
                return False
            seen.add(name)
            try:
                executable = Path(str(item.get("path", ""))).resolve(strict=True)
            except OSError:
                return False
            if (
                not executable.is_file()
                or not _sha256_value(item.get("sha256"))
                or _sha256_file(executable) != item.get("sha256")
                or not _text_matches(item.get("version"), 120, allow_empty=True)
            ):
                return False
        return seen == set(required)

    @staticmethod
    def _ota_blueprint(payload: dict[str, object], digest: str, path: Path) -> bool:
        unsigned = dict(payload)
        unsigned.pop("format", None)
        expected = str(unsigned.pop("blueprint_digest", ""))
        if (
            payload.get("schema_version") != 1
            or payload.get("phone_changed") is not False
            or payload.get("authority") != "project-local-build-evidence-only"
            or payload.get("plan_mode") != "verified-ota-payload-baseline"
            or not _project_path_matches(path, payload.get("project_id"))
            or not _sha256_value(payload.get("source_archive_sha256"))
            or not _sha256_value(payload.get("payload_sha256"))
            or expected != digest
            or _digest(unsigned) != digest
        ):
            return False
        return _workspace_artifact_matches(
            path,
            payload.get("payload_path"),
            payload.get("payload_size_bytes"),
            payload.get("payload_modified_ns"),
            payload.get("payload_sha256"),
        )

    @staticmethod
    def _avb_receipt(payload: dict[str, object], digest: str, path: Path) -> bool:
        unsigned = dict(payload)
        unsigned.pop("format", None)
        images = unsigned.get("images")
        image_fields = {
            "role",
            "path",
            "sha256",
            "algorithm",
            "public_key_sha1",
            "rollback_index",
            "rollback_index_location",
            "flags",
            "descriptor_partitions",
            "size_bytes",
            "modified_ns",
        }
        if (
            payload.get("schema_version") != 3
            or payload.get("phone_changed") is not False
            or not _project_path_matches(path, payload.get("project_id"))
            or not _sha256_value(payload.get("source_original_sha256"))
            or not _sha256_value(payload.get("local_build_receipt_digest"))
            or not isinstance(images, list)
            or len(images) != 4
            or any(not isinstance(image, dict) or set(image) != image_fields for image in images)
            or {image["role"] for image in images}
            != {
                "source-vbmeta",
                "source-vbmeta_system",
                "candidate-product",
                "candidate-vbmeta_system",
            }
            or _digest(unsigned) != digest
        ):
            return False
        for image in images:
            if not isinstance(image, dict) or not _workspace_artifact_matches(
                path,
                image.get("path"),
                image.get("size_bytes"),
                image.get("modified_ns"),
                image.get("sha256"),
            ):
                return False
        return True


def _project_path_matches(path: Path, project_id: object) -> bool:
    return (
        isinstance(project_id, str)
        and bool(re.fullmatch(r"[a-z0-9-]{1,64}", project_id))
        and path.parent.name == project_id
        and path.parent.parent.name == "projects"
    )


def _workspace_artifact_matches(
    receipt_path: Path,
    relative: object,
    size: object,
    modified_ns: object,
    digest: object,
) -> bool:
    if not isinstance(relative, str) or not _sha256_value(digest):
        return False
    if type(size) is not int or size <= 0 or type(modified_ns) is not int or modified_ns <= 0:
        return False
    workspace = receipt_path.parent.parent.parent.resolve()
    candidate_path = Path(relative)
    if candidate_path.is_absolute() or ".." in candidate_path.parts:
        return False
    unresolved = workspace / candidate_path
    if unresolved.is_symlink():
        return False
    try:
        candidate = unresolved.resolve(strict=True)
        details = candidate.stat()
    except OSError:
        return False
    if not candidate.is_relative_to(workspace) or not candidate.is_file():
        return False
    if details.st_size != size:
        return False
    # The producing typed service already computed the content digest. Rechecking
    # containment plus its saved size/mtime evidence keeps cached UI reads bounded;
    # current build/readiness services perform full content verification separately.
    return details.st_mtime_ns == modified_ns


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _hex_value(value: object, length: int) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(rf"[0-9a-f]{{{length}}}", value))


def _sha256_value(value: object) -> bool:
    return _hex_value(value, 64)


def _timestamp(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 80:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed <= datetime.now(UTC) + timedelta(minutes=5)


def _label(value: object, maximum: int) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and len(value) <= maximum
        and _text(value, maximum) == value
    )


def _text(value: object, maximum: int) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value.replace("\x00", " ")).strip()[:maximum]


def _text_matches(value: object, maximum: int, *, allow_empty: bool = False) -> bool:
    return (
        isinstance(value, str) and _text(value, maximum) == value and (allow_empty or bool(value))
    )
