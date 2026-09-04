from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, fields, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from romverse.device_packs.models import (
    AvbExecutionPolicy,
    AvbPolicyAuthority,
    AvbPolicyMode,
)
from romverse.device_packs.registry import DevicePackRegistry
from romverse.infrastructure.local_store import atomic_write_json, read_json_object
from romverse.infrastructure.process import CommandRunner
from romverse.infrastructure.tools import ToolStatus
from romverse.rom.build_execution import LocalDeviceBuildExecutor
from romverse.rom.models import ProjectError
from romverse.rom.payloads import PayloadService
from romverse.rom.projects import RomProjectStore


@dataclass(frozen=True, slots=True)
class AvbImageEvidence:
    role: str
    path: str
    sha256: str
    algorithm: str
    public_key_sha1: str
    rollback_index: int
    rollback_index_location: int
    flags: int
    descriptor_partitions: tuple[str, ...]
    size_bytes: int = 0
    modified_ns: int = 0


@dataclass(frozen=True, slots=True)
class AvbTopologyReceipt:
    schema_version: int
    project_id: str
    created_at: str
    pack_id: str
    contract_id: str
    source_original_sha256: str
    local_build_receipt_digest: str
    images: tuple[AvbImageEvidence, ...]
    source_algorithm: str
    source_public_key_sha1: str
    candidate_signed: bool
    source_identity_matches: bool
    signing_ready: bool
    policy_mode: str
    policy_authority: str
    policy_compatible: bool
    policy_authorized: bool
    diagnosis: str
    phone_changed: bool


@dataclass(frozen=True, slots=True)
class SourceAvbTopologyReceipt:
    """Exact-source AVB inventory that grants no signing, Pack, or phone authority."""

    schema_version: int
    project_id: str
    created_at: str
    source_original_sha256: str
    payload_manifest_digest: str
    images: tuple[AvbImageEvidence, ...]
    signing_identity_consistent: bool
    top_level_chain_partitions: tuple[str, ...]
    child_descriptor_partitions: tuple[str, ...]
    diagnosis: str
    phone_changed: bool
    receipt_digest: str


class SourceAvbEvidenceService:
    """Inspect OEM source vbmeta without requiring or manufacturing a Device Pack contract."""

    RECEIPT_NAME = "source-avb-topology.romverse"
    FORMAT = "romverse.source-avb-topology"
    SCHEMA_VERSION = 1
    MAX_RECEIPT_BYTES = 256 * 1024

    def __init__(
        self,
        store: RomProjectStore,
        payloads: PayloadService,
        avbtool: Path,
        runner: CommandRunner,
    ) -> None:
        self.store = store
        self.payloads = payloads
        self.avbtool = avbtool.resolve()
        self.runner = runner

    def inspect(self, project_id: str) -> SourceAvbTopologyReceipt:
        project = self.store.get(project_id)
        if project.original is None:
            raise ProjectError("Source AVB inspection requires a protected firmware source")
        if not self.avbtool.is_file():
            raise ProjectError("Verified AVBTool is unavailable")
        payload = self.payloads.load(project_id) or self.payloads.scan(project_id)
        if (
            payload.schema_version != PayloadService.SCHEMA_VERSION
            or payload.source_original_sha256 != project.original.sha256
            or not _sha256_value(payload.record_digest)
        ):
            raise ProjectError("Payload evidence does not match the protected firmware source")
        records = {item.name: item for item in payload.partitions}
        missing = tuple(
            name
            for name in AvbEvidenceService.SOURCE_NAMES
            if name not in records or not records[name].extracted_path
        )
        if missing:
            payload = self.payloads.extract(project_id, missing)
            records = {item.name: item for item in payload.partitions}

        images: list[AvbImageEvidence] = []
        top_chains: tuple[str, ...] = ()
        for name in AvbEvidenceService.SOURCE_NAMES:
            record = records.get(name)
            if (
                record is None
                or not record.extracted_path
                or not _sha256_value(record.sha256)
                or record.actual_bytes <= 0
            ):
                raise ProjectError(f"Exact source {name} image evidence is unavailable")
            path = self._workspace_file(record.extracted_path)
            if path.stat().st_size != record.actual_bytes:
                raise ProjectError(f"Exact source {name} size changed before AVB inspection")
            image, chain_partitions = self._inspect_source_image(
                f"source-{name}", path, record.sha256
            )
            images.append(image)
            if name == "vbmeta":
                top_chains = chain_partitions

        top, child = images
        consistent = bool(
            top.algorithm != "NONE"
            and child.algorithm != "NONE"
            and top.public_key_sha1
            and top.public_key_sha1 == child.public_key_sha1
            and "vbmeta_system" in top_chains
        )
        child_descriptors = child.descriptor_partitions
        diagnosis = (
            f"OEM source AVB identity is consistent: {top.algorithm}, key "
            f"{top.public_key_sha1[:16]}…, top-level chains "
            f"{', '.join(top_chains) or 'none'}, child descriptors "
            f"{', '.join(child_descriptors) or 'none'}. This is source evidence only."
            if consistent
            else "OEM source vbmeta and vbmeta_system do not expose one consistent signed identity; exact Pack development must stop for review."
        )
        receipt = _seal_source_receipt(
            SourceAvbTopologyReceipt(
                self.SCHEMA_VERSION,
                project_id,
                datetime.now(UTC).isoformat(),
                project.original.sha256,
                payload.record_digest,
                tuple(images),
                consistent,
                top_chains,
                child_descriptors,
                diagnosis,
                False,
                "",
            )
        )
        atomic_write_json(
            self.store.projects_root / project_id / self.RECEIPT_NAME,
            {"format": self.FORMAT, **asdict(receipt)},
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_RECEIPT_BYTES,
        )
        return receipt

    def load(self, project_id: str) -> SourceAvbTopologyReceipt | None:
        path = self.store.projects_root / project_id / self.RECEIPT_NAME
        try:
            data = read_json_object(
                path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
            if (
                set(data) != {"format", *(field.name for field in fields(SourceAvbTopologyReceipt))}
                or data.pop("format") != self.FORMAT
            ):
                return None
            raw_images = data.pop("images")
            image_fields = {field.name for field in fields(AvbImageEvidence)}
            if (
                not isinstance(raw_images, list)
                or len(raw_images) != 2
                or any(
                    not isinstance(item, dict)
                    or set(item) != image_fields
                    or not isinstance(item.get("descriptor_partitions"), list)
                    for item in raw_images
                )
                or not isinstance(data.get("top_level_chain_partitions"), list)
                or not isinstance(data.get("child_descriptor_partitions"), list)
            ):
                return None
            images = tuple(
                AvbImageEvidence(
                    **{**item, "descriptor_partitions": tuple(item["descriptor_partitions"])}
                )
                for item in raw_images
            )
            top_level_chain_partitions = tuple(data.pop("top_level_chain_partitions"))
            child_descriptor_partitions = tuple(data.pop("child_descriptor_partitions"))
            receipt = SourceAvbTopologyReceipt(
                **data,
                images=images,
                top_level_chain_partitions=top_level_chain_partitions,
                child_descriptor_partitions=child_descriptor_partitions,
            )
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None
        try:
            project = self.store.get(project_id)
            payload = self.payloads.load(project_id)
            expected = _seal_source_receipt(replace(receipt, receipt_digest=""))
            top, child = receipt.images
            derived_consistency = bool(
                top.algorithm != "NONE"
                and child.algorithm != "NONE"
                and top.public_key_sha1
                and top.public_key_sha1 == child.public_key_sha1
                and "vbmeta_system" in receipt.top_level_chain_partitions
            )
            if (
                receipt.schema_version != self.SCHEMA_VERSION
                or expected != receipt
                or not _aware_timestamp(receipt.created_at)
                or receipt.project_id != project_id
                or project.original is None
                or receipt.source_original_sha256 != project.original.sha256
                or payload is None
                or receipt.payload_manifest_digest != payload.record_digest
                or type(receipt.signing_identity_consistent) is not bool
                or receipt.signing_identity_consistent != derived_consistency
                or type(receipt.phone_changed) is not bool
                or receipt.phone_changed
                or not 1 <= len(receipt.diagnosis) <= 600
                or tuple(item.role for item in receipt.images)
                != ("source-vbmeta", "source-vbmeta_system")
                or not receipt.top_level_chain_partitions
                or "vbmeta_system" not in receipt.top_level_chain_partitions
                or not set(receipt.top_level_chain_partitions).issubset(
                    receipt.images[0].descriptor_partitions
                )
                or not self._valid_partitions(receipt.top_level_chain_partitions)
                or receipt.child_descriptor_partitions != receipt.images[1].descriptor_partitions
                or any(not self._valid_image(item) for item in receipt.images)
            ):
                return None
            for item in receipt.images:
                artifact = self._workspace_file(item.path)
                details = artifact.stat()
                if details.st_size != item.size_bytes or details.st_mtime_ns != item.modified_ns:
                    return None
        except (OSError, ProjectError, TypeError, ValueError):
            return None
        return receipt

    def _inspect_source_image(
        self,
        role: str,
        path: Path,
        expected_sha256: str,
    ) -> tuple[AvbImageEvidence, tuple[str, ...]]:
        if _sha256(path) != expected_sha256:
            raise ProjectError(f"{role} changed before AVB inspection")
        result = self.runner.run(
            (str(self.avbtool), "info_image", "--image", str(path)),
            timeout=120,
        )
        if not result.ok:
            detail = (result.stderr or result.stdout).strip().splitlines()
            raise ProjectError(
                f"AVB inspection failed for {role}" + (f": {detail[-1][:240]}" if detail else "")
            )
        evidence = AvbEvidenceService.parse_info(
            role,
            path.relative_to(self.store.workspace).as_posix(),
            expected_sha256,
            result.stdout,
        )
        details = path.stat()
        evidence = replace(
            evidence,
            size_bytes=details.st_size,
            modified_ns=details.st_mtime_ns,
        )
        return evidence, self._parse_chain_partitions(result.stdout)

    @staticmethod
    def _parse_chain_partitions(output: str) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                match.group(1)
                for match in re.finditer(
                    r"^\s+Chain Partition descriptor:\s*$\s+Partition Name:\s*"
                    r"([A-Za-z0-9._-]+)\s*$",
                    output,
                    re.MULTILINE,
                )
            )
        )

    @staticmethod
    def _valid_partitions(values: tuple[str, ...]) -> bool:
        return bool(
            len(values) <= AvbEvidenceService.MAX_DESCRIPTOR_PARTITIONS
            and all(
                isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9._-]{1,80}", value))
                for value in values
            )
        )

    @staticmethod
    def _valid_image(item: AvbImageEvidence) -> bool:
        return bool(
            item.role in {"source-vbmeta", "source-vbmeta_system"}
            and isinstance(item.path, str)
            and 1 <= len(item.path) <= 4_096
            and _sha256_value(item.sha256)
            and isinstance(item.algorithm, str)
            and 1 <= len(item.algorithm) <= 80
            and (
                (item.algorithm == "NONE" and item.public_key_sha1 == "")
                or (
                    item.algorithm != "NONE"
                    and bool(re.fullmatch(r"[0-9a-f]{40}", item.public_key_sha1))
                )
            )
            and type(item.rollback_index) is int
            and item.rollback_index >= 0
            and type(item.rollback_index_location) is int
            and item.rollback_index_location >= 0
            and type(item.flags) is int
            and item.flags >= 0
            and item.size_bytes > 0
            and item.modified_ns > 0
            and len(item.descriptor_partitions) <= AvbEvidenceService.MAX_DESCRIPTOR_PARTITIONS
            and all(
                isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9._-]{1,80}", value))
                for value in item.descriptor_partitions
            )
        )

    def _workspace_file(self, relative: str) -> Path:
        candidate = (self.store.workspace / relative).resolve(strict=True)
        if (
            not candidate.is_relative_to(self.store.workspace.resolve())
            or not candidate.is_file()
            or candidate.is_symlink()
        ):
            raise ProjectError("Source AVB evidence path escaped the ROMVERSE workspace")
        return candidate


class AvbEvidenceService:
    """Inspect exact source/candidate AVB topology without signing or device access."""

    RECEIPT_NAME = "avb-topology.romverse"
    SOURCE_NAMES = ("vbmeta", "vbmeta_system")
    MAX_RECEIPT_BYTES = 256 * 1024
    MAX_DESCRIPTOR_PARTITIONS = 256

    def __init__(
        self,
        store: RomProjectStore,
        registry: DevicePackRegistry,
        tool_statuses: tuple[ToolStatus, ...],
        payloads: PayloadService,
        avbtool: Path,
        runner: CommandRunner,
    ) -> None:
        self.store = store
        self.registry = registry
        self.tool_statuses = tool_statuses
        self.payloads = payloads
        self.avbtool = avbtool.resolve()
        self.runner = runner

    def inspect(self, project_id: str) -> AvbTopologyReceipt:
        project = self.store.get(project_id)
        pack = next(
            (item for item in self.registry.packs if item.pack_id == project.device_pack_id), None
        )
        if project.original is None or pack is None or pack.build_contract is None:
            raise ProjectError("AVB inspection requires an exact source-bound Device Pack")
        contract = pack.build_contract
        if project.original.sha256 != contract.source.archive_sha256:
            raise ProjectError("Protected source does not match the Device Pack AVB contract")
        if not self.avbtool.is_file():
            raise ProjectError("Verified AVBTool is unavailable")

        payload = self.payloads.load(project_id) or self.payloads.scan(project_id)
        records = {item.name: item for item in payload.partitions}
        missing = tuple(
            name
            for name in self.SOURCE_NAMES
            if name not in records or not records[name].extracted_path
        )
        if missing:
            payload = self.payloads.extract(project_id, missing)
            records = {item.name: item for item in payload.partitions}
        expected_source = {
            "vbmeta": contract.top_level_vbmeta_sha256,
            "vbmeta_system": contract.vbmeta_system_sha256,
        }
        images = []
        for name in self.SOURCE_NAMES:
            record = records[name]
            if record.sha256 != expected_source[name]:
                raise ProjectError(f"Exact source {name} SHA-256 differs from the AVB contract")
            path = self._workspace_file(record.extracted_path)
            images.append(self._inspect_image(f"source-{name}", path, record.sha256))

        executor = LocalDeviceBuildExecutor(
            self.store,
            self.registry,
            self.tool_statuses,
            self.runner,
        )
        build = executor.load_receipt(project_id)
        if build is None:
            raise ProjectError("A current verified local build candidate is required")
        outputs = {item.name: item for item in build.outputs}
        for name in ("product.img", "vbmeta_system.img"):
            output = outputs.get(name)
            if output is None:
                raise ProjectError(f"Verified local candidate is missing {name}")
            path = self._workspace_file(output.path)
            images.append(self._inspect_image(f"candidate-{name[:-4]}", path, output.sha256))

        receipt = self.classify(
            project_id,
            pack.pack_id,
            contract.contract_id,
            project.original.sha256,
            build.receipt_digest,
            tuple(images),
            contract.avb_execution_policy,
        )
        atomic_write_json(
            self.store.projects_root / project_id / self.RECEIPT_NAME,
            {"format": "romverse.avb-topology", **asdict(receipt)},
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_RECEIPT_BYTES,
        )
        return receipt

    @classmethod
    def classify(
        cls,
        project_id: str,
        pack_id: str,
        contract_id: str,
        source_original_sha256: str,
        local_build_receipt_digest: str,
        images: tuple[AvbImageEvidence, ...],
        policy: AvbExecutionPolicy | None = None,
    ) -> AvbTopologyReceipt:
        by_role = {item.role: item for item in images}
        required = {
            "source-vbmeta",
            "source-vbmeta_system",
            "candidate-product",
            "candidate-vbmeta_system",
        }
        if set(by_role) != required:
            raise ProjectError("AVB topology is missing required source or candidate images")
        source_images = (by_role["source-vbmeta"], by_role["source-vbmeta_system"])
        candidate_images = (
            by_role["candidate-product"],
            by_role["candidate-vbmeta_system"],
        )
        algorithms = {item.algorithm for item in source_images}
        public_keys = {item.public_key_sha1 for item in source_images}
        if (
            len(algorithms) != 1
            or "NONE" in algorithms
            or len(public_keys) != 1
            or "" in public_keys
        ):
            raise ProjectError("Exact source AVB signing identity is inconsistent")
        source_algorithm = next(iter(algorithms))
        source_key = next(iter(public_keys))
        candidate_signed = all(
            item.algorithm != "NONE" and bool(item.public_key_sha1) for item in candidate_images
        )
        identity_matches = candidate_signed and all(
            item.algorithm == source_algorithm and item.public_key_sha1 == source_key
            for item in candidate_images
        )
        ready = candidate_signed and identity_matches
        policy_compatible = cls._policy_compatible(policy, by_role)
        policy_authorized = bool(
            policy_compatible
            and policy is not None
            and policy.authority is AvbPolicyAuthority.FLASH_VALIDATED
        )
        if ready:
            diagnosis = "Candidate AVB images are signed with the exact source identity"
        elif policy_compatible and policy is not None:
            policy_label = policy.mode.value.replace("_", " ")
            if policy_authorized:
                diagnosis = (
                    f"Candidate matches the flash-validated {policy_label} policy for "
                    f"{policy.evidence_build_id}; it is not OEM-signed"
                )
            else:
                diagnosis = (
                    f"Candidate matches the historical {policy_label} reference from "
                    f"{policy.evidence_build_id}, but this policy is reference-only; "
                    "the current build remains unsigned and flash-locked"
                )
        elif not candidate_signed:
            diagnosis = (
                f"Candidate AVB images are unsigned; exact source requires {source_algorithm} "
                f"key {source_key[:16]}…"
            )
        else:
            diagnosis = (
                f"Candidate signing identity differs from exact source key {source_key[:16]}…; "
                "a validated re-chaining policy is required"
            )
        evidence_schema = (
            3 if all(item.size_bytes > 0 and item.modified_ns > 0 for item in images) else 2
        )
        return AvbTopologyReceipt(
            evidence_schema,
            project_id,
            datetime.now(UTC).isoformat(),
            pack_id,
            contract_id,
            source_original_sha256,
            local_build_receipt_digest,
            images,
            source_algorithm,
            source_key,
            candidate_signed,
            identity_matches,
            ready,
            policy.mode.value if policy is not None else "",
            policy.authority.value if policy is not None else "",
            policy_compatible,
            policy_authorized,
            diagnosis,
            False,
        )

    @staticmethod
    def _policy_compatible(
        policy: AvbExecutionPolicy | None,
        by_role: dict[str, AvbImageEvidence],
    ) -> bool:
        if policy is None:
            return False
        source_top = by_role["source-vbmeta"]
        source_child = by_role["source-vbmeta_system"]
        candidate_product = by_role["candidate-product"]
        candidate_child = by_role["candidate-vbmeta_system"]
        if (
            policy.top_level_strategy != "preserve_exact_source"
            or source_top.algorithm == "NONE"
            or policy.chain_partition not in source_top.descriptor_partitions
            or source_child.algorithm == "NONE"
            or set(candidate_child.descriptor_partitions) != set(source_child.descriptor_partitions)
            or candidate_child.rollback_index != policy.candidate_rollback_index
            or candidate_child.rollback_index_location != policy.candidate_rollback_index_location
            or candidate_child.flags != policy.candidate_flags
        ):
            return False
        candidates = (candidate_product, candidate_child)
        if policy.mode is AvbPolicyMode.UNLOCKED_UNSIGNED_CHILD:
            return all(item.algorithm == policy.candidate_algorithm for item in candidates)
        return all(item.algorithm == policy.candidate_algorithm for item in candidates)

    @staticmethod
    def parse_info(role: str, path: str, sha256: str, output: str) -> AvbImageEvidence:
        def field(label: str, *, required: bool = True) -> str:
            match = re.search(rf"^{re.escape(label)}:\s*(.+?)\s*$", output, re.MULTILINE)
            if match:
                return match.group(1).strip(" '")
            if required:
                raise ProjectError(f"AVBTool output is missing {label}")
            return ""

        algorithm = field("Algorithm")
        public_key = field("Public key (sha1)", required=False).casefold()
        if public_key and not re.fullmatch(r"[0-9a-f]{40}", public_key):
            raise ProjectError("AVBTool returned an invalid public-key fingerprint")
        descriptor_partitions = tuple(
            dict.fromkeys(
                match.group(1)
                for match in re.finditer(
                    r"^\s+Partition Name:\s*([A-Za-z0-9._-]+)\s*$",
                    output,
                    re.MULTILINE,
                )
            )
        )
        try:
            rollback_index = int(field("Rollback Index"))
            rollback_location = int(field("Rollback Index Location"))
            flags = int(field("Flags"))
        except ValueError as exc:
            raise ProjectError("AVBTool returned invalid numeric header fields") from exc
        return AvbImageEvidence(
            role,
            path,
            sha256,
            algorithm,
            public_key,
            rollback_index,
            rollback_location,
            flags,
            descriptor_partitions,
        )

    def load(self, project_id: str) -> AvbTopologyReceipt | None:
        path = self.store.projects_root / project_id / self.RECEIPT_NAME
        try:
            data = read_json_object(
                path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
            if (
                set(data) != {"format", *(field.name for field in fields(AvbTopologyReceipt))}
                or data.pop("format") != "romverse.avb-topology"
            ):
                return None
            raw_images = data.pop("images")
            schema_version = data.get("schema_version")
            image_fields = {field.name for field in fields(AvbImageEvidence)}
            if schema_version == 2:
                image_fields -= {"size_bytes", "modified_ns"}
            if (
                not isinstance(raw_images, list)
                or len(raw_images) != 4
                or any(
                    not isinstance(item, dict)
                    or set(item) != image_fields
                    or not isinstance(item.get("descriptor_partitions"), list)
                    for item in raw_images
                )
            ):
                return None
            images = tuple(
                AvbImageEvidence(
                    **{
                        **item,
                        "descriptor_partitions": tuple(item["descriptor_partitions"]),
                    }
                )
                for item in raw_images
            )
            receipt = AvbTopologyReceipt(**data, images=images)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None
        project = self.store.get(project_id)
        pack = next(
            (item for item in self.registry.packs if item.pack_id == project.device_pack_id), None
        )
        build = LocalDeviceBuildExecutor(
            self.store,
            self.registry,
            self.tool_statuses,
            self.runner,
        ).load_receipt(project_id)
        if (
            receipt.schema_version not in {2, 3}
            or not _aware_timestamp(receipt.created_at)
            or receipt.project_id != project_id
            or receipt.phone_changed
            or not _sha256_value(receipt.source_original_sha256)
            or not _sha256_value(receipt.local_build_receipt_digest)
            or type(receipt.candidate_signed) is not bool
            or type(receipt.source_identity_matches) is not bool
            or type(receipt.signing_ready) is not bool
            or type(receipt.policy_compatible) is not bool
            or type(receipt.policy_authorized) is not bool
            or not isinstance(receipt.diagnosis, str)
            or not 1 <= len(receipt.diagnosis) <= 600
            or any(
                not self._valid_image(item, schema_version=receipt.schema_version)
                for item in images
            )
            or {item.role for item in images}
            != {
                "source-vbmeta",
                "source-vbmeta_system",
                "candidate-product",
                "candidate-vbmeta_system",
            }
            or project.original is None
            or receipt.source_original_sha256 != project.original.sha256
            or pack is None
            or pack.build_contract is None
            or receipt.pack_id != pack.pack_id
            or receipt.contract_id != pack.build_contract.contract_id
            or build is None
            or receipt.local_build_receipt_digest != build.receipt_digest
        ):
            return None
        try:
            for item in images:
                artifact = self._workspace_file(item.path)
                if receipt.schema_version == 3:
                    details = artifact.stat()
                    if (
                        details.st_size != item.size_bytes
                        or details.st_mtime_ns != item.modified_ns
                    ):
                        return None
        except (OSError, ProjectError):
            return None
        return receipt

    def _valid_image(self, item: AvbImageEvidence, *, schema_version: int) -> bool:
        return bool(
            item.role
            in {
                "source-vbmeta",
                "source-vbmeta_system",
                "candidate-product",
                "candidate-vbmeta_system",
            }
            and isinstance(item.path, str)
            and 1 <= len(item.path) <= 4_096
            and _sha256_value(item.sha256)
            and isinstance(item.algorithm, str)
            and 1 <= len(item.algorithm) <= 80
            and (
                not item.public_key_sha1
                or bool(re.fullmatch(r"[0-9a-f]{40}", item.public_key_sha1))
            )
            and type(item.rollback_index) is int
            and item.rollback_index >= 0
            and type(item.rollback_index_location) is int
            and item.rollback_index_location >= 0
            and type(item.flags) is int
            and item.flags >= 0
            and type(item.size_bytes) is int
            and type(item.modified_ns) is int
            and (
                (schema_version == 3 and item.size_bytes > 0 and item.modified_ns > 0)
                or (schema_version == 2 and item.size_bytes == 0 and item.modified_ns == 0)
            )
            and len(item.descriptor_partitions) <= self.MAX_DESCRIPTOR_PARTITIONS
            and all(
                isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9._-]{1,80}", value))
                for value in item.descriptor_partitions
            )
        )

    def _inspect_image(self, role: str, path: Path, expected_sha256: str) -> AvbImageEvidence:
        if _sha256(path) != expected_sha256:
            raise ProjectError(f"{role} changed before AVB inspection")
        result = self.runner.run(
            (str(self.avbtool), "info_image", "--image", str(path)),
            timeout=120,
        )
        if not result.ok:
            detail = (result.stderr or result.stdout).strip().splitlines()
            raise ProjectError(
                f"AVB inspection failed for {role}" + (f": {detail[-1][:240]}" if detail else "")
            )
        evidence = self.parse_info(
            role,
            path.relative_to(self.store.workspace).as_posix(),
            expected_sha256,
            result.stdout,
        )
        details = path.stat()
        return replace(
            evidence,
            size_bytes=details.st_size,
            modified_ns=details.st_mtime_ns,
        )

    def _workspace_file(self, relative: str) -> Path:
        candidate = (self.store.workspace / relative).resolve(strict=True)
        if (
            not candidate.is_relative_to(self.store.workspace.resolve())
            or not candidate.is_file()
            or candidate.is_symlink()
        ):
            raise ProjectError("AVB evidence path escaped the ROMVERSE workspace")
        return candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _seal_source_receipt(receipt: SourceAvbTopologyReceipt) -> SourceAvbTopologyReceipt:
    payload = asdict(receipt)
    payload.pop("receipt_digest", None)
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return replace(receipt, receipt_digest=digest)


def _sha256_value(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _aware_timestamp(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 80:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed <= datetime.now(UTC) + timedelta(minutes=5)
