from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from romverse.device_packs.models import (
    AvbPolicyAuthority,
    AvbPolicyMode,
    DeviceWriteTransport,
)
from romverse.device_packs.registry import DevicePackRegistry
from romverse.guardian.flash_handoff import FlashMode, GuardianFlashHandoffService
from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    ensure_private_directory,
    read_json_object,
)
from romverse.infrastructure.process import CommandRunner, SubprocessRunner
from romverse.infrastructure.tools import ToolStatus
from romverse.rom.build_execution import LocalDeviceBuildExecutor
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.rom.signing_ceremony import OfflineSigningCeremonyService


@dataclass(frozen=True, slots=True)
class GuardianBoundArtifact:
    order: int
    partition: str
    artifact_name: str
    artifact_relative_path: str
    artifact_sha256: str
    artifact_size_bytes: int
    artifact_modified_ns: int
    transport: DeviceWriteTransport
    target_slot: str
    verify_after_write: bool
    evidence_kind: str
    evidence_receipt_digest: str


@dataclass(frozen=True, slots=True)
class GuardianArtifactBindingReceipt:
    """Exact read-only artifact evidence; this is never a device command manifest."""

    schema_version: int
    binding_id: str
    created_at: str
    project_id: str
    handoff_digest: str
    device_key: str
    mode: FlashMode
    pack_id: str
    pack_version: str
    pack_sha256: str
    build_contract_id: str
    build_contract_version: int
    write_contract_id: str
    write_contract_version: int
    write_attestation_sha256: str
    source_build_id: str
    source_archive_sha256: str
    local_build_receipt_digest: str
    offline_signing_receipt_digest: str
    writes: tuple[GuardianBoundArtifact, ...]
    phone_changed: bool
    bootloader_relock_allowed: bool
    execution_authority: str
    command_manifest: tuple[tuple[str, ...], ...]
    binding_digest: str


@dataclass(frozen=True, slots=True)
class _ArtifactEvidence:
    rule: object
    path: Path
    recorded_sha256: str
    recorded_size_bytes: int
    recorded_modified_ns: int
    kind: str
    receipt_digest: str


class GuardianArtifactBindingService:
    """Rehash exact declared images off the UI thread without changing a device."""

    FORMAT = "romverse.guardian-artifact-binding"
    SCHEMA_VERSION = 1
    LATEST_NAME = "artifact-binding.romverse"
    MAX_BYTES = 256 * 1024
    MAX_WRITES = 32
    MAX_ARTIFACT_BYTES = 128 * 1024 * 1024 * 1024

    def __init__(
        self,
        store: RomProjectStore,
        registry: DevicePackRegistry,
        tool_statuses: tuple[ToolStatus, ...] = (),
        avbtool: Path | None = None,
        runner: CommandRunner | None = None,
    ) -> None:
        self.store = store
        self.registry = registry
        self.tool_statuses = tool_statuses
        self.avbtool = avbtool.resolve() if avbtool is not None else None
        self.runner = runner or SubprocessRunner()

    def prepare(
        self,
        project_id: str,
        progress: Callable[[int], None] | None = None,
    ) -> GuardianArtifactBindingReceipt:
        context = self._context(project_id)
        evidence = self._artifact_evidence(*context)
        total = sum(item.recorded_size_bytes for item in evidence)
        completed = 0
        if progress is not None:
            progress(0)
        writes: list[GuardianBoundArtifact] = []
        for order, item in enumerate(evidence, start=1):
            digest = _sha256(
                item.path,
                lambda done, offset=completed: (
                    progress(round((offset + done) * 100 / total) if total else 100)
                    if progress is not None
                    else None
                ),
            )
            stat = item.path.stat()
            if (
                digest != item.recorded_sha256
                or stat.st_size != item.recorded_size_bytes
                or stat.st_mtime_ns != item.recorded_modified_ns
            ):
                raise ProjectError(
                    f"{item.path.name} changed after its verified build/signing receipt"
                )
            rule = item.rule
            writes.append(
                GuardianBoundArtifact(
                    order=order,
                    partition=str(rule.partition),
                    artifact_name=str(rule.artifact),
                    artifact_relative_path=item.path.relative_to(self.store.workspace).as_posix(),
                    artifact_sha256=digest,
                    artifact_size_bytes=stat.st_size,
                    artifact_modified_ns=stat.st_mtime_ns,
                    transport=rule.transport,
                    target_slot=str(rule.target_slot),
                    verify_after_write=bool(rule.verify_after_write),
                    evidence_kind=item.kind,
                    evidence_receipt_digest=item.receipt_digest,
                )
            )
            completed += item.recorded_size_bytes
        if progress is not None:
            progress(100)
        project, pack, contract, write_contract, handoff, build, signing = context
        payload: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "binding_id": uuid4().hex,
            "created_at": datetime.now(UTC).isoformat(),
            "project_id": project_id,
            "handoff_digest": handoff.handoff_digest,
            "device_key": handoff.device_key,
            "mode": handoff.mode,
            "pack_id": pack.pack_id,
            "pack_version": pack.version,
            "pack_sha256": pack.sha256,
            "build_contract_id": contract.contract_id,
            "build_contract_version": contract.version,
            "write_contract_id": write_contract.contract_id,
            "write_contract_version": write_contract.version,
            "write_attestation_sha256": write_contract.attestation_sha256,
            "source_build_id": contract.source.build_id,
            "source_archive_sha256": contract.source.archive_sha256,
            "local_build_receipt_digest": build.receipt_digest,
            "offline_signing_receipt_digest": signing.receipt_digest if signing else "",
            "writes": [asdict(item) for item in writes],
            "phone_changed": False,
            "bootloader_relock_allowed": False,
            "execution_authority": "review-only",
            "command_manifest": (),
        }
        receipt = GuardianArtifactBindingReceipt(
            **{key: value for key, value in payload.items() if key != "writes"},
            writes=tuple(writes),
            binding_digest=_digest(payload),
        )
        self.validate(receipt)
        self._write(receipt)
        return receipt

    def load(
        self,
        project_id: str,
        progress: Callable[[int], None] | None = None,
    ) -> GuardianArtifactBindingReceipt | None:
        path = self._root(project_id) / self.LATEST_NAME
        try:
            data = read_json_object(
                path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            if (
                set(data)
                != {"format", *(field.name for field in fields(GuardianArtifactBindingReceipt))}
                or data.pop("format") != self.FORMAT
            ):
                return None
            raw_writes = data.pop("writes")
            write_fields = {field.name for field in fields(GuardianBoundArtifact)}
            if (
                not isinstance(raw_writes, list)
                or not 1 <= len(raw_writes) <= self.MAX_WRITES
                or any(
                    not isinstance(item, dict) or set(item) != write_fields for item in raw_writes
                )
            ):
                return None
            writes = tuple(
                GuardianBoundArtifact(
                    **{
                        **item,
                        "transport": DeviceWriteTransport(str(item["transport"])),
                    }
                )
                for item in raw_writes
            )
            data["mode"] = FlashMode(str(data["mode"]))
            raw_commands = data.get("command_manifest")
            if raw_commands != []:
                return None
            data["command_manifest"] = ()
            receipt = GuardianArtifactBindingReceipt(**data, writes=writes)
            self.validate(receipt)
            context = self._context(project_id)
            evidence = self._artifact_evidence(*context)
            if not self._matches_context(receipt, context, evidence):
                return None
            total = sum(item.recorded_size_bytes for item in evidence)
            completed = 0
            if progress is not None:
                progress(0)
            for bound, item in zip(receipt.writes, evidence, strict=True):
                digest = _sha256(
                    item.path,
                    lambda done, offset=completed: (
                        progress(round((offset + done) * 100 / total) if total else 100)
                        if progress is not None
                        else None
                    ),
                )
                stat = item.path.stat()
                if (
                    digest != bound.artifact_sha256
                    or digest != item.recorded_sha256
                    or stat.st_size != bound.artifact_size_bytes
                    or stat.st_mtime_ns != bound.artifact_modified_ns
                ):
                    return None
                completed += item.recorded_size_bytes
            if progress is not None:
                progress(100)
            return receipt
        except (
            LocalStoreError,
            OSError,
            ValueError,
            TypeError,
            KeyError,
            ProjectError,
            json.JSONDecodeError,
        ):
            return None

    def validate(self, receipt: GuardianArtifactBindingReceipt) -> None:
        payload = asdict(receipt)
        expected = str(payload.pop("binding_digest", ""))
        if (
            receipt.schema_version != self.SCHEMA_VERSION
            or not _hex(receipt.binding_id, 32)
            or not _aware_timestamp(receipt.created_at)
            or not _clean(receipt.project_id, 128)
            or not _hex(receipt.handoff_digest, 64)
            or not _hex(receipt.device_key, 20)
            or not isinstance(receipt.mode, FlashMode)
            or not _clean(receipt.pack_id, 128)
            or not _clean(receipt.pack_version, 80)
            or not _hex(receipt.pack_sha256, 64)
            or not _clean(receipt.build_contract_id, 80)
            or type(receipt.build_contract_version) is not int
            or receipt.build_contract_version not in {1, 2}
            or not _clean(receipt.write_contract_id, 80)
            or type(receipt.write_contract_version) is not int
            or receipt.write_contract_version not in {1, 2}
            or not _hex(receipt.write_attestation_sha256, 64)
            or not _clean(receipt.source_build_id, 160)
            or not _hex(receipt.source_archive_sha256, 64)
            or not _hex(receipt.local_build_receipt_digest, 64)
            or (
                receipt.offline_signing_receipt_digest
                and not _hex(receipt.offline_signing_receipt_digest, 64)
            )
            or not 1 <= len(receipt.writes) <= self.MAX_WRITES
            or tuple(item.order for item in receipt.writes)
            != tuple(range(1, len(receipt.writes) + 1))
            or len({item.partition for item in receipt.writes}) != len(receipt.writes)
            or len({item.artifact_name for item in receipt.writes}) != len(receipt.writes)
            or any(not self._valid_write(item) for item in receipt.writes)
            or receipt.phone_changed
            or receipt.bootloader_relock_allowed
            or receipt.execution_authority != "review-only"
            or receipt.command_manifest
            or expected != _digest(payload)
        ):
            raise ProjectError("Guardian artifact binding failed integrity or safety validation")

    def _context(self, project_id: str):
        project = self.store.get(project_id)
        pack = next(
            (item for item in self.registry.packs if item.pack_id == project.device_pack_id), None
        )
        if project.original is None or pack is None or pack.build_contract is None:
            raise ProjectError("An exact source-bound Device Pack is required")
        contract = pack.build_contract
        write_contract = contract.partition_write_contract
        policy = contract.avb_execution_policy
        if (
            project.original.sha256 != contract.source.archive_sha256
            or write_contract is None
            or policy is None
            or policy.authority is not AvbPolicyAuthority.FLASH_VALIDATED
            or write_contract.source_build_id != contract.source.build_id
            or write_contract.attestation_sha256 != policy.attestation_sha256
            or write_contract.bootloader_relock_allowed
        ):
            raise ProjectError(
                "The exact Device Pack has no valid flash-certified partition-write contract"
            )
        handoff = GuardianFlashHandoffService(self.store).load(project_id)
        if handoff is None:
            raise ProjectError("Prepare a current Guardian keep-data or wipe-data handoff first")
        if (
            handoff.mode is FlashMode.DIRTY_KEEP_DATA
            and not write_contract.preserve_user_data_supported
        ):
            raise ProjectError("This exact write contract does not support keeping user data")
        if (
            handoff.mode is FlashMode.CLEAN_WIPE_DATA
            and not write_contract.wipe_user_data_supported
        ):
            raise ProjectError("This exact write contract does not support wiping user data")
        build = LocalDeviceBuildExecutor(
            self.store,
            self.registry,
            self.tool_statuses,
            self.runner,
        ).load_receipt(project_id)
        if build is None or build.contract_id != contract.contract_id:
            raise ProjectError("A current verified local build receipt is required")
        signing = None
        if policy.mode is AvbPolicyMode.SIGNED_CUSTOM_RECHAIN:
            if any(
                rule.artifact not in OfflineSigningCeremonyService.SIGNED_NAMES
                for rule in write_contract.writes
            ):
                raise ProjectError(
                    "The current signing pipeline cannot prove a signed composite image; the "
                    "write contract must name the separately verified signed images"
                )
            if self.avbtool is None or not self.avbtool.is_file():
                raise ProjectError(
                    "Verified AVBTool is required to reload signed artifact evidence"
                )
            signing = OfflineSigningCeremonyService(
                self.store,
                self.registry,
                self.tool_statuses,
                self.avbtool,
                self.runner,
            ).load_receipt(project_id)
            if signing is None:
                raise ProjectError("A current verified offline-signing receipt is required")
        elif policy.mode is AvbPolicyMode.EXACT_SOURCE_IDENTITY:
            raise ProjectError(
                "Exact-source write binding requires a protected source-image receipt that is not yet available"
            )
        return project, pack, contract, write_contract, handoff, build, signing

    def _artifact_evidence(
        self,
        _project,
        _pack,
        contract,
        write_contract,
        _handoff,
        build,
        signing,
    ) -> tuple[_ArtifactEvidence, ...]:
        local = {item.name: item for item in build.outputs}
        signed = {item.name: item for item in signing.artifacts} if signing is not None else {}
        evidence: list[_ArtifactEvidence] = []
        for rule in write_contract.writes:
            if signing is not None:
                item = signed.get(rule.artifact)
                kind = "verified-offline-signing"
                receipt_digest = signing.receipt_digest
            else:
                item = local.get(rule.artifact)
                kind = "verified-local-build"
                receipt_digest = build.receipt_digest
            if item is None:
                raise ProjectError(f"The current verified receipt does not contain {rule.artifact}")
            path = self._workspace_file(str(item.path))
            stat = path.stat()
            if (
                stat.st_size != item.size_bytes
                or stat.st_mtime_ns != item.modified_ns
                or not 0 < item.size_bytes <= self.MAX_ARTIFACT_BYTES
                or not _hex(str(item.sha256), 64)
            ):
                raise ProjectError(f"{rule.artifact} no longer matches its verified receipt")
            evidence.append(
                _ArtifactEvidence(
                    rule,
                    path,
                    str(item.sha256),
                    int(item.size_bytes),
                    int(item.modified_ns),
                    kind,
                    receipt_digest,
                )
            )
        if len(evidence) != len(write_contract.writes):
            raise ProjectError("Guardian could not bind every declared partition write")
        return tuple(evidence)

    def _matches_context(self, receipt, context, evidence) -> bool:
        project, pack, contract, write_contract, handoff, build, signing = context
        return bool(
            project.original is not None
            and receipt.project_id == project.project_id
            and receipt.handoff_digest == handoff.handoff_digest
            and receipt.device_key == handoff.device_key
            and receipt.mode is handoff.mode
            and receipt.pack_id == pack.pack_id
            and receipt.pack_version == pack.version
            and receipt.pack_sha256 == pack.sha256
            and receipt.build_contract_id == contract.contract_id
            and receipt.build_contract_version == contract.version
            and receipt.write_contract_id == write_contract.contract_id
            and receipt.write_contract_version == write_contract.version
            and receipt.write_attestation_sha256 == write_contract.attestation_sha256
            and receipt.source_build_id == contract.source.build_id
            and receipt.source_archive_sha256 == project.original.sha256
            and receipt.local_build_receipt_digest == build.receipt_digest
            and receipt.offline_signing_receipt_digest
            == (signing.receipt_digest if signing else "")
            and len(receipt.writes) == len(evidence)
            and all(
                bound.partition == item.rule.partition
                and bound.artifact_name == item.rule.artifact
                and bound.artifact_relative_path
                == item.path.relative_to(self.store.workspace).as_posix()
                and bound.artifact_sha256 == item.recorded_sha256
                and bound.artifact_size_bytes == item.recorded_size_bytes
                and bound.artifact_modified_ns == item.recorded_modified_ns
                and bound.transport is item.rule.transport
                and bound.target_slot == item.rule.target_slot
                and bound.verify_after_write == item.rule.verify_after_write
                and bound.evidence_kind == item.kind
                and bound.evidence_receipt_digest == item.receipt_digest
                for bound, item in zip(receipt.writes, evidence, strict=True)
            )
        )

    @classmethod
    def _valid_write(cls, item: GuardianBoundArtifact) -> bool:
        return bool(
            type(item.order) is int
            and 1 <= item.order <= cls.MAX_WRITES
            and _partition(item.partition)
            and _artifact_name(item.artifact_name)
            and _safe_relative(item.artifact_relative_path)
            and _hex(item.artifact_sha256, 64)
            and type(item.artifact_size_bytes) is int
            and 0 < item.artifact_size_bytes <= cls.MAX_ARTIFACT_BYTES
            and type(item.artifact_modified_ns) is int
            and item.artifact_modified_ns > 0
            and item.target_slot in {"a", "b", "none"}
            and item.verify_after_write
            and item.evidence_kind in {"verified-local-build", "verified-offline-signing"}
            and _hex(item.evidence_receipt_digest, 64)
        )

    def _workspace_file(self, relative: str) -> Path:
        if not _safe_relative(relative):
            raise ProjectError("Guardian artifact path is unsafe")
        current = self.store.workspace
        for part in Path(relative).parts:
            current /= part
            if current.is_symlink():
                raise ProjectError("Guardian artifacts cannot use symbolic links")
        path = (self.store.workspace / relative).resolve(strict=True)
        if not path.is_relative_to(self.store.workspace.resolve()) or not path.is_file():
            raise ProjectError("Guardian artifact escaped the contained workspace")
        return path

    def _write(self, receipt: GuardianArtifactBindingReceipt) -> None:
        root = self._root(receipt.project_id)
        ensure_private_directory(root, boundary=self.store.workspace)
        document = {"format": self.FORMAT, **asdict(receipt)}
        atomic_write_json(
            root / f"artifact-binding-{receipt.binding_id[:12]}.romverse",
            document,
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_BYTES,
        )
        atomic_write_json(
            root / self.LATEST_NAME,
            document,
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_BYTES,
        )

    def _root(self, project_id: str) -> Path:
        self.store.get(project_id)
        return self.store.projects_root / project_id / "guardian"


def _sha256(path: Path, progress: Callable[[int], None] | None = None) -> str:
    digest = hashlib.sha256()
    done = 0
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
            done += len(chunk)
            if progress is not None:
                progress(done)
    return digest.hexdigest()


def _digest(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _aware_timestamp(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 80:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed <= datetime.now(UTC) + timedelta(minutes=5)


def _hex(value: object, length: int) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(rf"[0-9a-f]{{{length}}}", value))


def _clean(value: object, maximum: int) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= maximum
        and "\x00" not in value
        and value == value.strip()
    )


def _partition(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value))


def _artifact_name(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}\.img", value))
        and "/" not in value
        and "\\" not in value
    )


def _safe_relative(value: object) -> bool:
    if not isinstance(value, str) or not 1 <= len(value) <= 4_096 or "\x00" in value:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts
