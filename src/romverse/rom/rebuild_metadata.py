from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from romverse.device_packs.models import DeviceBuildContract, PartitionBuildRule
from romverse.infrastructure.process import CommandRunner
from romverse.rom.filesystems import FilesystemManifest, PartitionFilesystemService
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore


@dataclass(frozen=True, slots=True)
class FileContextEvidence:
    partition: str
    source_path: str
    source_sha256: str


@dataclass(frozen=True, slots=True)
class RebuildMetadataReceipt:
    schema_version: int
    project_id: str
    partition: str
    created_at: str
    contract_id: str
    contract_version: int
    source_sha256: str
    fakeroot_path: str
    fakeroot_sha256: str
    file_contexts_path: str
    file_contexts_sha256: str
    context_sources: tuple[FileContextEvidence, ...]


class RebuildMetadataService:
    """Prepare source-bound ownership and SELinux evidence for local image rebuilding."""

    MAX_SOURCE_BYTES = 32 * 1024 * 1024
    MAX_COMBINED_BYTES = 64 * 1024 * 1024

    def __init__(
        self,
        store: RomProjectStore,
        filesystems: PartitionFilesystemService,
        runner: CommandRunner,
        fakeroot: Path,
    ) -> None:
        self.store = store
        self.filesystems = filesystems
        self.runner = runner
        self.fakeroot = fakeroot.resolve()

    def prepare(
        self,
        project_id: str,
        contract: DeviceBuildContract,
    ) -> tuple[RebuildMetadataReceipt, ...]:
        self.store.get(project_id)
        if not self.fakeroot.is_file():
            raise ProjectError("Fakeroot is unavailable; open Forge Arsenal and verify it")
        if not contract.file_context_sources:
            raise ProjectError("The Device Pack has no file-context provenance contract")
        contexts, context_evidence = self._combined_contexts(project_id, contract)
        receipts = []
        for rule in contract.partitions:
            if rule.mode != "rebuild":
                continue
            receipts.append(
                self._prepare_partition(
                    project_id,
                    contract,
                    rule,
                    contexts,
                    context_evidence,
                )
            )
        if not receipts:
            raise ProjectError("The Device Pack has no rebuildable partition")
        return tuple(receipts)

    def _prepare_partition(
        self,
        project_id: str,
        contract: DeviceBuildContract,
        rule: PartitionBuildRule,
        contexts: bytes,
        context_evidence: tuple[FileContextEvidence, ...],
    ) -> RebuildMetadataReceipt:
        manifest = self._source_manifest(project_id, rule)
        if not manifest.fakeroot_state_path:
            raise ProjectError(
                f"Re-expand {rule.name} with the verified fakeroot-aware EROFS extractor"
            )
        tree = self._contained_tree(project_id, manifest)
        state = self._contained_workspace_file(manifest.fakeroot_state_path)
        if state.stat().st_size > self.MAX_SOURCE_BYTES:
            raise ProjectError(f"{rule.name} fakeroot state exceeds the safe size limit")

        root = self.store.projects_root / project_id / "rebuild-metadata"
        root.mkdir(parents=True, exist_ok=True)
        state_target = root / f"{rule.name}.fakeroot"
        contexts_target = root / f"{rule.name}.file_contexts"
        state_staging = root / f".{rule.name}-{uuid4().hex}.fakeroot.part"
        contexts_staging = root / f".{rule.name}-{uuid4().hex}.contexts.part"
        try:
            shutil.copyfile(state, state_staging)
            result = self.runner.run(
                (
                    str(self.fakeroot),
                    "-i",
                    str(state_staging),
                    "-s",
                    str(state_staging),
                    "--",
                    "/usr/bin/chown",
                    "-R",
                    "0:0",
                    str(tree),
                ),
                timeout=2 * 60 * 60,
                cwd=self.store.workspace,
            )
            if not result.ok:
                detail = (result.stderr or result.stdout).strip().splitlines()
                raise ProjectError(
                    "Fakeroot metadata reconciliation failed"
                    + (f": {detail[-1][:240]}" if detail else "")
                )
            if (
                not state_staging.is_file()
                or state_staging.is_symlink()
                or state_staging.stat().st_size > self.MAX_SOURCE_BYTES
            ):
                raise ProjectError("Reconciled fakeroot state failed bounded validation")
            contexts_staging.write_bytes(contexts)
            state_staging.chmod(0o600)
            contexts_staging.chmod(0o644)
            state_digest = _sha256(state_staging)
            context_digest = _sha256(contexts_staging)
            os.replace(state_staging, state_target)
            os.replace(contexts_staging, contexts_target)
        finally:
            state_staging.unlink(missing_ok=True)
            contexts_staging.unlink(missing_ok=True)

        receipt = RebuildMetadataReceipt(
            1,
            project_id,
            rule.name,
            datetime.now(UTC).isoformat(),
            contract.contract_id,
            contract.version,
            rule.source_sha256,
            state_target.name,
            state_digest,
            contexts_target.name,
            context_digest,
            context_evidence,
        )
        _atomic_json(
            root / f"{rule.name}.romverse",
            {"format": "romverse.rebuild-metadata", **asdict(receipt)},
        )
        return receipt

    def _combined_contexts(
        self,
        project_id: str,
        contract: DeviceBuildContract,
    ) -> tuple[bytes, tuple[FileContextEvidence, ...]]:
        combined: list[bytes] = []
        evidence = []
        rules = {rule.name: rule for rule in contract.partitions}
        for source in contract.file_context_sources:
            rule = rules[source.partition]
            manifest = self._source_manifest(project_id, rule)
            tree = self._contained_tree(project_id, manifest)
            recorded = dict(manifest.metadata_hashes)
            selected = None
            for relative in source.candidate_paths:
                if relative not in recorded:
                    continue
                candidate = self._contained_tree_file(tree, relative)
                if candidate.stat().st_size > self.MAX_SOURCE_BYTES:
                    raise ProjectError(
                        f"{source.partition} file-context source exceeds the safe size limit"
                    )
                if _sha256(candidate) != recorded[relative]:
                    raise ProjectError(
                        f"{source.partition} file-context source changed after extraction"
                    )
                selected = candidate
                break
            if selected is None:
                choices = ", ".join(source.candidate_paths)
                raise ProjectError(
                    f"Expand {source.partition} from the exact source; expected one of: {choices}"
                )
            payload = selected.read_bytes()
            if b"\x00" in payload:
                raise ProjectError(f"{source.partition} file-context source is not plain text")
            lines = [
                line.rstrip(b"\r")
                for line in payload.splitlines()
                if line.strip() and not line.lstrip().startswith(b"#")
            ]
            combined.extend(lines)
            evidence.append(
                FileContextEvidence(
                    source.partition,
                    selected.relative_to(tree).as_posix(),
                    _sha256(selected),
                )
            )
        payload = b"\n".join(combined) + b"\n"
        if len(payload) <= 1 or len(payload) > self.MAX_COMBINED_BYTES:
            raise ProjectError("Combined file-context evidence is empty or exceeds its safe limit")
        return payload, tuple(evidence)

    def _source_manifest(
        self,
        project_id: str,
        rule: PartitionBuildRule,
    ) -> FilesystemManifest:
        manifest = self.filesystems.load(project_id, rule.name)
        if manifest is None:
            raise ProjectError(f"Expand {rule.name} from the exact source before building")
        if manifest.source_sha256 != rule.source_sha256:
            raise ProjectError(f"{rule.name} filesystem does not match the Device Pack source")
        return manifest

    def _contained_tree(self, project_id: str, manifest: FilesystemManifest) -> Path:
        tree = (self.store.workspace / manifest.tree_path).resolve(strict=True)
        root = (self.store.working_root / project_id / "tree" / "partition_files").resolve(
            strict=True
        )
        if not tree.is_relative_to(root) or not tree.is_dir():
            raise ProjectError("Expanded filesystem tree escaped the project boundary")
        return tree

    def _contained_workspace_file(self, relative: str) -> Path:
        unresolved = self.store.workspace / relative
        if unresolved.is_symlink():
            raise ProjectError("Metadata source cannot be a symbolic link")
        candidate = unresolved.resolve(strict=True)
        if not candidate.is_relative_to(self.store.workspace.resolve()) or not candidate.is_file():
            raise ProjectError("Metadata source escaped the ROMVERSE workspace")
        return candidate

    @staticmethod
    def _contained_tree_file(tree: Path, relative: str) -> Path:
        unresolved = tree / relative
        if unresolved.is_symlink():
            raise ProjectError("File-context source cannot be a symbolic link")
        candidate = unresolved.resolve(strict=True)
        if not candidate.is_relative_to(tree) or not candidate.is_file():
            raise ProjectError("File-context source escaped the extracted filesystem")
        return candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
