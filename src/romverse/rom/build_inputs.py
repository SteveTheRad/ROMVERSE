from __future__ import annotations

from dataclasses import dataclass

from romverse.device_packs.models import DeviceBuildContract
from romverse.rom.filesystems import PartitionFilesystemService
from romverse.rom.models import ProjectError
from romverse.rom.payloads import PayloadService
from romverse.rom.projects import RomProjectStore
from romverse.rom.rebuild_metadata import RebuildMetadataReceipt, RebuildMetadataService


@dataclass(frozen=True, slots=True)
class BuildInputPreparation:
    project_id: str
    contract_id: str
    extracted_partitions: tuple[str, ...]
    expanded_filesystems: tuple[str, ...]
    metadata_receipts: tuple[RebuildMetadataReceipt, ...]
    phone_changed: bool = False


class BuildInputPreparationService:
    """Complete exact, local build-input preparation without invoking any device command."""

    def __init__(
        self,
        store: RomProjectStore,
        payloads: PayloadService,
        filesystems: PartitionFilesystemService,
        metadata: RebuildMetadataService,
    ) -> None:
        self.store = store
        self.payloads = payloads
        self.filesystems = filesystems
        self.metadata = metadata

    def prepare(
        self,
        project_id: str,
        contract: DeviceBuildContract,
    ) -> BuildInputPreparation:
        project = self.store.get(project_id)
        if project.original is None or project.original.sha256 != contract.source.archive_sha256:
            raise ProjectError(
                f"Build inputs require exact source {contract.source.build_id}; archive hash differs"
            )
        payload = self.payloads.load(project_id) or self.payloads.scan(project_id)
        if payload.payload_sha256 != contract.source.payload_sha256:
            raise ProjectError("payload.bin does not match the Device Pack build contract")
        records = {item.name: item for item in payload.partitions}
        expected_names = tuple(rule.name for rule in contract.partitions)
        missing_names = tuple(name for name in expected_names if name not in records)
        if missing_names:
            raise ProjectError(
                "The exact payload is missing required partitions: " + ", ".join(missing_names)
            )
        extraction = tuple(name for name in expected_names if not records[name].extracted_path)
        if extraction:
            payload = self.payloads.extract(project_id, extraction)
            records = {item.name: item for item in payload.partitions}
        failures = []
        for rule in contract.partitions:
            item = records[rule.name]
            if not item.extracted_path:
                failures.append(f"{rule.name}: extraction missing")
            elif item.actual_bytes != rule.source_size_bytes:
                failures.append(f"{rule.name}: source size differs")
            elif item.sha256 != rule.source_sha256:
                failures.append(f"{rule.name}: source SHA-256 differs")
        if failures:
            raise ProjectError("Exact partition validation failed: " + "; ".join(failures))

        required_filesystems = tuple(
            dict.fromkeys(
                (
                    *(source.partition for source in contract.file_context_sources),
                    *(rule.name for rule in contract.partitions if rule.mode == "rebuild"),
                )
            )
        )
        expanded = []
        for partition in required_filesystems:
            if self.filesystems.load(project_id, partition) is not None:
                continue
            self.filesystems.expand(project_id, partition)
            expanded.append(partition)
        receipts = self.metadata.prepare(project_id, contract)
        return BuildInputPreparation(
            project_id,
            contract.contract_id,
            extraction,
            tuple(expanded),
            receipts,
            False,
        )
