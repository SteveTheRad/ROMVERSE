from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import asdict, dataclass, fields, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from romverse.device_packs.models import AvbPolicyAuthority, AvbPolicyMode
from romverse.device_packs.registry import DevicePackRegistry
from romverse.infrastructure.local_store import (
    atomic_write_json,
    ensure_private_directory,
    read_json_object,
)
from romverse.infrastructure.process import CommandRunner
from romverse.infrastructure.tools import ToolStatus
from romverse.rom.avb_evidence import AvbEvidenceService, AvbImageEvidence
from romverse.rom.build_execution import LocalDeviceBuildExecutor
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore


@dataclass(frozen=True, slots=True)
class SigningArtifactRequest:
    name: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class OfflineSigningRequest:
    schema_version: int
    request_id: str
    project_id: str
    created_at: str
    pack_id: str
    pack_version: str
    pack_sha256: str
    contract_id: str
    source_build_id: str
    source_archive_sha256: str
    local_build_receipt_digest: str
    expected_algorithm: str
    expected_public_key_sha1: str
    expected_rollback_index: int
    expected_rollback_index_location: int
    expected_flags: int
    expected_descriptor_partitions: tuple[str, ...]
    artifacts: tuple[SigningArtifactRequest, ...]
    authority: str
    private_key_included: bool
    phone_changed: bool
    request_digest: str
    output_path: str


@dataclass(frozen=True, slots=True)
class SignedArtifactEvidence:
    name: str
    path: str
    sha256: str
    size_bytes: int
    modified_ns: int
    algorithm: str
    public_key_sha1: str
    rollback_index: int
    rollback_index_location: int
    flags: int
    descriptor_partitions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OfflineSigningReceipt:
    schema_version: int
    receipt_id: str
    project_id: str
    created_at: str
    pack_id: str
    pack_sha256: str
    contract_id: str
    local_build_receipt_digest: str
    request_digest: str
    artifacts: tuple[SignedArtifactEvidence, ...]
    verified: bool
    private_key_stored: bool
    phone_changed: bool
    receipt_digest: str


class OfflineSigningCeremonyService:
    """Export and verify offline AVB signing artifacts without handling private keys."""

    REQUEST_NAME = "offline-signing-request.romverse"
    RECEIPT_NAME = "offline-signing-receipt.romverse"
    MANIFEST_NAME = "romverse-signing-request.json"
    SIGNED_NAMES = ("product.img", "vbmeta_system.img")
    MAX_VBMETA_BYTES = 64 * 1024 * 1024
    MAX_REQUEST_BYTES = 512 * 1024
    MAX_RECEIPT_BYTES = 512 * 1024
    MAX_DESCRIPTOR_PARTITIONS = 128

    def __init__(
        self,
        store: RomProjectStore,
        registry: DevicePackRegistry,
        tool_statuses: tuple[ToolStatus, ...],
        avbtool: Path,
        runner: CommandRunner,
    ) -> None:
        self.store = store
        self.registry = registry
        self.tool_statuses = tool_statuses
        self.avbtool = avbtool.resolve()
        self.runner = runner

    def eligibility(self, project_id: str) -> tuple[bool, str]:
        try:
            _project, pack, contract, policy, _build, _outputs = self._context(project_id)
        except (OSError, ProjectError) as exc:
            return False, str(exc)
        return (
            True,
            f"{pack.display_name} authorizes {policy.candidate_algorithm} offline signing for "
            f"contract {contract.contract_id} and key {policy.signing_public_key_sha1[:16]}…",
        )

    def export_request(self, project_id: str, output_parent: Path) -> OfflineSigningRequest:
        project, pack, contract, policy, build, outputs = self._context(project_id)
        unresolved_parent = output_parent.expanduser()
        if unresolved_parent.is_symlink():
            raise ProjectError("Choose a real external folder for the offline signing request")
        parent = unresolved_parent.resolve(strict=True)
        if not parent.is_dir():
            raise ProjectError("Choose a real external folder for the offline signing request")
        if parent.is_relative_to(self.store.workspace.resolve()):
            raise ProjectError(
                "Offline signing requests must be exported outside ROMVERSE workspace"
            )

        artifacts = tuple(
            SigningArtifactRequest(name, output.sha256, output.size_bytes)
            for name in self.SIGNED_NAMES
            if (output := outputs[name])
        )
        payload: dict[str, object] = {
            "schema_version": 1,
            "request_id": uuid4().hex,
            "project_id": project_id,
            "created_at": datetime.now(UTC).isoformat(),
            "pack_id": pack.pack_id,
            "pack_version": pack.version,
            "pack_sha256": pack.sha256,
            "contract_id": contract.contract_id,
            "source_build_id": contract.source.build_id,
            "source_archive_sha256": contract.source.archive_sha256,
            "local_build_receipt_digest": build.receipt_digest,
            "expected_algorithm": policy.candidate_algorithm,
            "expected_public_key_sha1": policy.signing_public_key_sha1,
            "expected_rollback_index": policy.candidate_rollback_index,
            "expected_rollback_index_location": policy.candidate_rollback_index_location,
            "expected_flags": policy.candidate_flags,
            "expected_descriptor_partitions": contract.vbmeta_descriptor_partitions,
            "artifacts": [asdict(item) for item in artifacts],
            "authority": "offline-signing-request-only",
            "private_key_included": False,
            "phone_changed": False,
        }
        request_digest = _digest(payload)
        destination = parent / f"romverse-signing-{project_id}-{request_digest[:12]}"
        if destination.exists():
            raise ProjectError("This exact signing request already exists in the chosen folder")
        destination.mkdir(mode=0o700)
        try:
            for artifact in artifacts:
                source = self._workspace_file(outputs[artifact.name].path)
                if _sha256(source) != artifact.sha256:
                    raise ProjectError(f"{artifact.name} changed after local build verification")
                copied = destination / artifact.name
                shutil.copyfile(source, copied)
                copied.chmod(0o600)
            manifest = {**payload, "request_digest": request_digest}
            atomic_write_json(
                destination / self.MANIFEST_NAME,
                manifest,
                boundary=parent,
                maximum_bytes=self.MAX_REQUEST_BYTES,
            )
            request = OfflineSigningRequest(
                **{key: value for key, value in payload.items() if key != "artifacts"},
                artifacts=artifacts,
                request_digest=request_digest,
                output_path=str(destination),
            )
            atomic_write_json(
                self.store.projects_root / project_id / self.REQUEST_NAME,
                {"format": "romverse.offline-signing-request", **asdict(request)},
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_REQUEST_BYTES,
            )
            return request
        except Exception:
            shutil.rmtree(destination, ignore_errors=True)
            raise

    def import_signed_bundle(self, project_id: str, bundle: Path) -> OfflineSigningReceipt:
        _project, pack, contract, policy, build, unsigned_outputs = self._context(project_id)
        unresolved_folder = bundle.expanduser()
        if unresolved_folder.is_symlink():
            raise ProjectError("Choose the folder containing the externally signed artifacts")
        folder = unresolved_folder.resolve(strict=True)
        if not folder.is_dir():
            raise ProjectError("Choose the folder containing the externally signed artifacts")
        request = self._load_request(project_id)
        if request is None or request.local_build_receipt_digest != build.receipt_digest:
            raise ProjectError(
                "Export a fresh signing request for the current local candidate first"
            )
        if not self._manifest_matches_request(folder, request):
            raise ProjectError(
                "The signed bundle is missing the exact ROMVERSE request manifest or it changed"
            )

        inspected: list[tuple[Path, AvbImageEvidence]] = []
        for name in self.SIGNED_NAMES:
            unresolved = folder / name
            if unresolved.is_symlink():
                raise ProjectError(f"Signed {name} cannot be a symbolic link")
            path = unresolved.resolve(strict=True)
            expected = unsigned_outputs[name]
            if (
                path.parent != folder
                or not path.is_file()
                or path.is_symlink()
                or path.stat().st_size != expected.size_bytes
                or (name == "vbmeta_system.img" and path.stat().st_size > self.MAX_VBMETA_BYTES)
            ):
                raise ProjectError(f"Signed {name} has an unsafe path or unexpected size")
            evidence = self._inspect(name, path)
            if (
                evidence.algorithm != policy.candidate_algorithm
                or evidence.public_key_sha1 != policy.signing_public_key_sha1
            ):
                raise ProjectError(f"Signed {name} does not use the Device Pack signing identity")
            if name == "vbmeta_system.img" and (
                evidence.rollback_index != policy.candidate_rollback_index
                or evidence.rollback_index_location != policy.candidate_rollback_index_location
                or evidence.flags != policy.candidate_flags
                or set(evidence.descriptor_partitions) != set(contract.vbmeta_descriptor_partitions)
            ):
                raise ProjectError(
                    "Signed vbmeta_system.img violates the exact AVB descriptor policy"
                )
            inspected.append((path, evidence))

        evidence_root = (
            self.store.projects_root / project_id / "signing-evidence" / request.request_digest[:16]
        )
        if os.path.lexists(evidence_root):
            raise ProjectError("Signed evidence for this request was already imported")
        ensure_private_directory(evidence_root, boundary=self.store.workspace)
        try:
            records = []
            for source, evidence in inspected:
                destination = evidence_root / source.name
                shutil.copyfile(source, destination)
                destination.chmod(0o600)
                digest = _sha256(destination)
                if digest != evidence.sha256:
                    raise ProjectError(f"Signed {source.name} changed during evidence import")
                stat = destination.stat()
                records.append(
                    SignedArtifactEvidence(
                        source.name,
                        destination.relative_to(self.store.workspace).as_posix(),
                        digest,
                        stat.st_size,
                        stat.st_mtime_ns,
                        evidence.algorithm,
                        evidence.public_key_sha1,
                        evidence.rollback_index,
                        evidence.rollback_index_location,
                        evidence.flags,
                        evidence.descriptor_partitions,
                    )
                )
            payload = {
                "schema_version": 2,
                "receipt_id": uuid4().hex,
                "project_id": project_id,
                "created_at": datetime.now(UTC).isoformat(),
                "pack_id": pack.pack_id,
                "pack_sha256": pack.sha256,
                "contract_id": contract.contract_id,
                "local_build_receipt_digest": build.receipt_digest,
                "request_digest": request.request_digest,
                "artifacts": [asdict(item) for item in records],
                "verified": True,
                "private_key_stored": False,
                "phone_changed": False,
            }
            receipt = OfflineSigningReceipt(
                **{key: value for key, value in payload.items() if key != "artifacts"},
                artifacts=tuple(records),
                receipt_digest=_digest(payload),
            )
            atomic_write_json(
                self.store.projects_root / project_id / self.RECEIPT_NAME,
                {"format": "romverse.offline-signing-receipt", **asdict(receipt)},
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
            return receipt
        except Exception:
            shutil.rmtree(evidence_root, ignore_errors=True)
            raise

    def load_receipt(self, project_id: str) -> OfflineSigningReceipt | None:
        path = self.store.projects_root / project_id / self.RECEIPT_NAME
        try:
            data = read_json_object(
                path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
            if (
                set(data) != {"format", *(field.name for field in fields(OfflineSigningReceipt))}
                or data.pop("format") != "romverse.offline-signing-receipt"
            ):
                return None
            raw_artifacts = data.pop("artifacts")
            artifact_fields = {field.name for field in fields(SignedArtifactEvidence)}
            if (
                not isinstance(raw_artifacts, list)
                or len(raw_artifacts) != len(self.SIGNED_NAMES)
                or any(
                    not isinstance(item, dict)
                    or set(item) != artifact_fields
                    or not isinstance(item.get("descriptor_partitions"), list)
                    or len(item["descriptor_partitions"]) > self.MAX_DESCRIPTOR_PARTITIONS
                    for item in raw_artifacts
                )
            ):
                return None
            artifacts = tuple(
                SignedArtifactEvidence(
                    **{**item, "descriptor_partitions": tuple(item["descriptor_partitions"])}
                )
                for item in raw_artifacts
            )
            receipt = OfflineSigningReceipt(**data, artifacts=artifacts)
            payload = asdict(receipt)
            digest = payload.pop("receipt_digest")
            _project, pack, contract, policy, build, _outputs = self._context(project_id)
            request = self._load_request(project_id)
            if (
                receipt.schema_version not in {1, 2}
                or not _hex_value(receipt.receipt_id, 32)
                or not _aware_timestamp(receipt.created_at)
                or receipt.project_id != project_id
                or not receipt.verified
                or receipt.private_key_stored
                or receipt.phone_changed
                or receipt.pack_id != pack.pack_id
                or receipt.pack_sha256 != pack.sha256
                or receipt.contract_id != contract.contract_id
                or receipt.local_build_receipt_digest != build.receipt_digest
                or request is None
                or receipt.request_digest != request.request_digest
                or digest != _digest(payload)
                or {item.name for item in artifacts} != set(self.SIGNED_NAMES)
                or any(not self._valid_signed_artifact(item) for item in artifacts)
            ):
                return None
            for artifact in artifacts:
                stored = self._workspace_file(artifact.path)
                stat = stored.stat()
                if (
                    stat.st_size != artifact.size_bytes
                    or stat.st_mtime_ns != artifact.modified_ns
                    or artifact.algorithm != policy.candidate_algorithm
                    or artifact.public_key_sha1 != policy.signing_public_key_sha1
                    or (
                        artifact.name == "vbmeta_system.img"
                        and (
                            artifact.rollback_index != policy.candidate_rollback_index
                            or artifact.rollback_index_location
                            != policy.candidate_rollback_index_location
                            or artifact.flags != policy.candidate_flags
                            or set(artifact.descriptor_partitions)
                            != set(contract.vbmeta_descriptor_partitions)
                        )
                    )
                ):
                    return None
                if receipt.schema_version == 1 and _sha256(stored) != artifact.sha256:
                    return None
            if receipt.schema_version == 1:
                upgraded = replace(receipt, schema_version=2, receipt_digest="")
                upgraded_payload = asdict(upgraded)
                upgraded_payload.pop("receipt_digest")
                upgraded = replace(upgraded, receipt_digest=_digest(upgraded_payload))
                atomic_write_json(
                    path,
                    {"format": "romverse.offline-signing-receipt", **asdict(upgraded)},
                    boundary=self.store.workspace,
                    maximum_bytes=self.MAX_RECEIPT_BYTES,
                )
                return upgraded
            return receipt
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError, ProjectError):
            return None

    def _context(self, project_id: str):
        project = self.store.get(project_id)
        pack = next(
            (item for item in self.registry.packs if item.pack_id == project.device_pack_id), None
        )
        if project.original is None or pack is None or pack.build_contract is None:
            raise ProjectError("Offline signing requires an exact source-bound Device Pack")
        contract = pack.build_contract
        policy = contract.avb_execution_policy
        if (
            project.original.sha256 != contract.source.archive_sha256
            or policy is None
            or policy.mode is not AvbPolicyMode.SIGNED_CUSTOM_RECHAIN
            or policy.authority is not AvbPolicyAuthority.FLASH_VALIDATED
            or not policy.signing_public_key_sha1
            or not policy.attestation_sha256
        ):
            raise ProjectError(
                "This Device Pack does not authorize a flash-validated offline signing ceremony"
            )
        if not self.avbtool.is_file():
            raise ProjectError("Verified AVBTool is unavailable")
        build = LocalDeviceBuildExecutor(
            self.store, self.registry, self.tool_statuses, self.runner
        ).load_receipt(project_id)
        if build is None:
            raise ProjectError("A current verified local build candidate is required")
        outputs = {item.name: item for item in build.outputs}
        if any(name not in outputs for name in self.SIGNED_NAMES):
            raise ProjectError("Local build candidate is missing required AVB artifacts")
        return project, pack, contract, policy, build, outputs

    def _load_request(self, project_id: str) -> OfflineSigningRequest | None:
        path = self.store.projects_root / project_id / self.REQUEST_NAME
        try:
            data = read_json_object(
                path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_REQUEST_BYTES,
            )
            if (
                set(data) != {"format", *(field.name for field in fields(OfflineSigningRequest))}
                or data.pop("format") != "romverse.offline-signing-request"
            ):
                return None
            raw_artifacts = data.pop("artifacts")
            raw_descriptors = data.get("expected_descriptor_partitions")
            if (
                not isinstance(raw_artifacts, list)
                or len(raw_artifacts) != len(self.SIGNED_NAMES)
                or any(
                    not isinstance(item, dict)
                    or set(item) != {field.name for field in fields(SigningArtifactRequest)}
                    for item in raw_artifacts
                )
                or not isinstance(raw_descriptors, list)
                or not 1 <= len(raw_descriptors) <= self.MAX_DESCRIPTOR_PARTITIONS
            ):
                return None
            artifacts = tuple(SigningArtifactRequest(**item) for item in raw_artifacts)
            data["expected_descriptor_partitions"] = tuple(raw_descriptors)
            request = OfflineSigningRequest(**data, artifacts=artifacts)
            project, pack, contract, policy, build, outputs = self._context(project_id)
            digest_payload = asdict(request)
            digest = str(digest_payload.pop("request_digest"))
            digest_payload.pop("output_path")
            if (
                request.schema_version != 1
                or not _hex_value(request.request_id, 32)
                or not _aware_timestamp(request.created_at)
                or request.project_id != project.project_id
                or request.pack_id != pack.pack_id
                or request.pack_version != pack.version
                or request.pack_sha256 != pack.sha256
                or request.contract_id != contract.contract_id
                or request.source_build_id != contract.source.build_id
                or request.source_archive_sha256 != contract.source.archive_sha256
                or request.local_build_receipt_digest != build.receipt_digest
                or request.expected_algorithm != policy.candidate_algorithm
                or request.expected_public_key_sha1 != policy.signing_public_key_sha1
                or request.expected_rollback_index != policy.candidate_rollback_index
                or request.expected_rollback_index_location
                != policy.candidate_rollback_index_location
                or request.expected_flags != policy.candidate_flags
                or request.expected_descriptor_partitions != contract.vbmeta_descriptor_partitions
                or request.authority != "offline-signing-request-only"
                or request.private_key_included
                or request.phone_changed
                or not _safe_external_path_label(request.output_path)
                or digest != _digest(digest_payload)
                or request.request_digest != digest
                or {item.name for item in artifacts} != set(self.SIGNED_NAMES)
                or any(
                    not _valid_artifact_request(item)
                    or item.sha256 != outputs[item.name].sha256
                    or item.size_bytes != outputs[item.name].size_bytes
                    for item in artifacts
                )
            ):
                return None
            return request
        except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError, ProjectError):
            return None

    def _manifest_matches_request(
        self,
        folder: Path,
        request: OfflineSigningRequest,
    ) -> bool:
        try:
            manifest = read_json_object(
                folder / self.MANIFEST_NAME,
                boundary=folder,
                maximum_bytes=self.MAX_REQUEST_BYTES,
            )
        except OSError:
            return False
        expected = asdict(request)
        expected.pop("output_path")
        expected = json.loads(json.dumps(expected))
        return manifest == expected

    def _valid_signed_artifact(self, item: SignedArtifactEvidence) -> bool:
        return bool(
            item.name in self.SIGNED_NAMES
            and _safe_relative_path(item.path)
            and _sha256_value(item.sha256)
            and type(item.size_bytes) is int
            and item.size_bytes > 0
            and type(item.modified_ns) is int
            and item.modified_ns > 0
            and _clean_text(item.algorithm, 80)
            and _hex_value(item.public_key_sha1, 40)
            and type(item.rollback_index) is int
            and 0 <= item.rollback_index < 2**64
            and type(item.rollback_index_location) is int
            and 0 <= item.rollback_index_location <= 63
            and type(item.flags) is int
            and 0 <= item.flags < 2**32
            and len(item.descriptor_partitions) <= self.MAX_DESCRIPTOR_PARTITIONS
            and len(set(item.descriptor_partitions)) == len(item.descriptor_partitions)
            and all(_partition_name(value) for value in item.descriptor_partitions)
        )

    def _inspect(self, name: str, path: Path) -> AvbImageEvidence:
        digest = _sha256(path)
        result = self.runner.run(
            (str(self.avbtool), "info_image", "--image", str(path)), timeout=120
        )
        if not result.ok:
            raise ProjectError(f"AVBTool could not verify signed {name}")
        return AvbEvidenceService.parse_info(name, str(path), digest, result.stdout)

    def _workspace_file(self, relative: str) -> Path:
        if not _safe_relative_path(relative):
            raise ProjectError("Signing artifact escaped ROMVERSE workspace")
        unresolved = self.store.workspace / relative
        current = self.store.workspace
        for part in Path(relative).parts:
            current /= part
            if current.is_symlink():
                raise ProjectError("Signing artifacts cannot use symbolic links")
        path = unresolved.resolve(strict=True)
        if not path.is_relative_to(self.store.workspace.resolve()) or not path.is_file():
            raise ProjectError("Signing artifact escaped ROMVERSE workspace")
        return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256_value(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _hex_value(value: object, length: int) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(rf"[0-9a-f]{{{length}}}", value))


def _aware_timestamp(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 80:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed <= datetime.now(UTC) + timedelta(minutes=5)


def _clean_text(value: object, maximum: int) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= maximum
        and "\x00" not in value
        and value == value.strip()
    )


def _partition_name(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", value))


def _safe_relative_path(value: object) -> bool:
    if not isinstance(value, str) or not 1 <= len(value) <= 4_096 or "\x00" in value:
        return False
    candidate = Path(value)
    return not candidate.is_absolute() and ".." not in candidate.parts


def _safe_external_path_label(value: object) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 4_096
        and "\x00" not in value
        and not any(ord(character) < 32 for character in value)
    )


def _valid_artifact_request(item: SigningArtifactRequest) -> bool:
    return bool(
        _partition_name(item.name)
        and item.name.endswith(".img")
        and _sha256_value(item.sha256)
        and type(item.size_bytes) is int
        and item.size_bytes > 0
    )
