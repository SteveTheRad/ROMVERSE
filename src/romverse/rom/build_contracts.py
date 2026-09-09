from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from romverse.device_packs.models import DeviceBuildContract, PartitionBuildRule
from romverse.device_packs.registry import DevicePackRegistry
from romverse.infrastructure.provisioning import required_tools_for_contract
from romverse.infrastructure.tools import ToolStatus
from romverse.rom.builds import RomBuildPlanner
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore


class ContractCheckStatus(StrEnum):
    PASS = "pass"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class ContractCheck:
    check_id: str
    label: str
    status: ContractCheckStatus
    evidence: str
    resolution: str


@dataclass(frozen=True, slots=True)
class BuildContractAssessment:
    project_id: str
    pack_id: str
    contract_id: str
    checks: tuple[ContractCheck, ...]

    @property
    def ready(self) -> bool:
        return bool(self.checks) and all(
            check.status is ContractCheckStatus.PASS for check in self.checks
        )

    @property
    def blockers(self) -> tuple[str, ...]:
        return tuple(
            check.label for check in self.checks if check.status is ContractCheckStatus.BLOCKED
        )


@dataclass(frozen=True, slots=True)
class PlannedBuildStep:
    step_id: str
    label: str
    tool: str
    arguments: tuple[str, ...]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    phone_changed: bool = False


@dataclass(frozen=True, slots=True)
class DeviceBuildExecutionPlan:
    schema_version: int
    plan_id: str
    project_id: str
    created_at: str
    pack_id: str
    pack_sha256: str
    contract_id: str
    contract_version: int
    source_archive_sha256: str
    source_payload_sha256: str
    workspace_tree_sha256: str
    steps: tuple[PlannedBuildStep, ...]
    expected_outputs: tuple[str, ...]
    execution_locked: bool
    phone_changed: bool
    plan_digest: str
    workspace_plan_digest: str = ""


class DeviceBuildContractService:
    """Validate and plan a local Device Pack build without executing tools or touching a phone."""

    PLAN_NAME = "device-build-plan.romverse"
    METADATA_ROOT = "rebuild-metadata"
    MAX_METADATA_BYTES = 32 * 1024 * 1024

    def __init__(
        self,
        store: RomProjectStore,
        registry: DevicePackRegistry,
        tool_statuses: tuple[ToolStatus, ...] = (),
    ) -> None:
        self.store = store
        self.registry = registry
        self.tool_statuses = tool_statuses

    def assess(self, project_id: str) -> BuildContractAssessment:
        project = self.store.get(project_id)
        pack = next(
            (
                candidate
                for candidate in self.registry.packs
                if candidate.pack_id == project.device_pack_id
            ),
            None,
        )
        if pack is None or pack.build_contract is None:
            return BuildContractAssessment(
                project_id,
                project.device_pack_id,
                "",
                (
                    _blocked(
                        "contract",
                        "Device Pack build contract",
                        "The selected pack has no schema-2 build contract.",
                        "Select an exact Device Pack with a reviewed declarative build contract.",
                    ),
                ),
            )
        contract = pack.build_contract
        original_match = bool(
            project.original and project.original.sha256 == contract.source.archive_sha256
        )
        payload = self._payload_manifest(project_id)
        payload_match = bool(
            payload
            and payload.get("source_original_sha256") == contract.source.archive_sha256
            and payload.get("payload_sha256") == contract.source.payload_sha256
        )
        partition_records = (
            {
                str(item.get("name")): item
                for item in payload.get("partitions", ())
                if isinstance(item, dict)
            }
            if payload
            else {}
        )
        partition_failures = []
        for rule in contract.partitions:
            item = partition_records.get(rule.name)
            if not item or not item.get("extracted_path"):
                partition_failures.append(f"{rule.name}: not extracted")
            elif int(item.get("actual_bytes", -1)) != rule.source_size_bytes:
                partition_failures.append(f"{rule.name}: size differs")
            elif str(item.get("sha256", "")) != rule.source_sha256:
                partition_failures.append(f"{rule.name}: source hash differs")
            elif not self._workspace_file(str(item.get("extracted_path", ""))):
                partition_failures.append(f"{rule.name}: contained image missing")
        metadata_failures = []
        for rule in contract.partitions:
            if rule.mode == "rebuild" and not self._metadata_ready(project_id, contract, rule):
                metadata_failures.append(rule.name)
        build_plan = self._verified_workspace_plan(project_id)
        tree_verified = bool(build_plan and build_plan.device_pack_id == pack.pack_id)
        available = {status.name for status in self.tool_statuses if status.available}
        required_tools = required_tools_for_contract(contract)
        missing_tools = tuple(name for name in required_tools if name not in available)
        checks = (
            _check(
                "source",
                "Exact source firmware",
                original_match,
                (
                    f"Archive SHA-256 matches {contract.source.build_id}"
                    if original_match
                    else f"Requires {contract.source.build_id} archive {contract.source.archive_sha256[:16]}…"
                ),
                "Import the exact contract-bound firmware; similar versions and regions are rejected.",
            ),
            _check(
                "payload",
                "Exact payload provenance",
                payload_match,
                (
                    "Payload hash and protected source binding match"
                    if payload_match
                    else "Scan the exact source payload and verify its SHA-256."
                ),
                "Run Partition Atlas against the protected original and do not substitute payload.bin.",
            ),
            _check(
                "partitions",
                "Protected partition inputs",
                not partition_failures,
                (
                    "All contract partitions have matching size and recorded SHA-256"
                    if not partition_failures
                    else "; ".join(partition_failures[:5])
                ),
                "Extract every contract partition from the verified payload and resolve every size/hash mismatch.",
            ),
            _check(
                "metadata",
                "Rebuild metadata",
                not metadata_failures,
                (
                    "Fakeroot ownership and SELinux file-context receipts are present"
                    if not metadata_failures
                    else "Missing verified metadata: " + ", ".join(metadata_failures)
                ),
                "Capture ownership/mode and file-context evidence from the exact source before rebuilding.",
            ),
            _check(
                "workspace-plan",
                "Frozen working tree",
                tree_verified,
                (
                    "The current working tree matches its deterministic plan"
                    if tree_verified
                    else "Create or refresh the deterministic plan after the final Recipe change."
                ),
                "Regenerate and verify the build plan; never build a tree that changed afterward.",
            ),
            _check(
                "tools",
                "Complete verified toolchain",
                bool(self.tool_statuses) and not missing_tools,
                (
                    "All Genesis requirements are ready"
                    if self.tool_statuses and not missing_tools
                    else "Missing: " + ", ".join(missing_tools or required_tools)
                ),
                "Use Install and verify requirements in Genesis Sequence.",
            ),
        )
        return BuildContractAssessment(project_id, pack.pack_id, contract.contract_id, checks)

    def create_plan(self, project_id: str) -> DeviceBuildExecutionPlan:
        assessment = self.assess(project_id)
        if not assessment.ready:
            raise ProjectError(
                "Device build planning is blocked: " + ", ".join(assessment.blockers)
            )
        project = self.store.get(project_id)
        pack = next(item for item in self.registry.packs if item.pack_id == project.device_pack_id)
        contract = pack.build_contract
        assert project.original is not None and contract is not None
        payload = self._payload_manifest(project_id)
        assert payload is not None
        records = {str(item["name"]): item for item in payload["partitions"]}
        for rule in contract.partitions:
            image = self.store.workspace / str(records[rule.name]["extracted_path"])
            if _sha256(image) != rule.source_sha256:
                raise ProjectError(f"Protected {rule.name} image changed after extraction")
        build_plan = self._verified_workspace_plan(project_id)
        if build_plan is None:
            raise ProjectError("The exact workspace build plan no longer verifies")
        plan_id = uuid4().hex
        steps = self._steps(project_id, contract, records, plan_id)
        payload_without_digest = {
            "schema_version": 2 if build_plan.schema_version >= 3 else 1,
            "plan_id": plan_id,
            "project_id": project_id,
            "created_at": datetime.now(UTC).isoformat(),
            "pack_id": pack.pack_id,
            "pack_sha256": pack.sha256,
            "contract_id": contract.contract_id,
            "contract_version": contract.version,
            "source_archive_sha256": contract.source.archive_sha256,
            "source_payload_sha256": contract.source.payload_sha256,
            "workspace_tree_sha256": build_plan.tree_sha256,
            "steps": [asdict(step) for step in steps],
            "expected_outputs": contract.allowed_outputs,
            "execution_locked": False,
            "phone_changed": False,
        }
        if build_plan.schema_version >= 3:
            payload_without_digest["workspace_plan_digest"] = build_plan.plan_digest
        digest = _json_digest(payload_without_digest)
        plan = DeviceBuildExecutionPlan(
            int(payload_without_digest["schema_version"]),
            str(payload_without_digest["plan_id"]),
            project_id,
            str(payload_without_digest["created_at"]),
            pack.pack_id,
            pack.sha256,
            contract.contract_id,
            contract.version,
            contract.source.archive_sha256,
            contract.source.payload_sha256,
            build_plan.tree_sha256,
            steps,
            contract.allowed_outputs,
            False,
            False,
            digest,
            build_plan.plan_digest if build_plan.schema_version >= 3 else "",
        )
        serialized_plan = asdict(plan)
        if plan.schema_version == 1:
            serialized_plan.pop("workspace_plan_digest", None)
        _atomic_json(
            self.store.projects_root / project_id / self.PLAN_NAME,
            {"format": "romverse.device-build-plan", **serialized_plan},
        )
        return plan

    def load(self, project_id: str) -> DeviceBuildExecutionPlan | None:
        path = self.store.projects_root / project_id / self.PLAN_NAME
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.pop("format") != "romverse.device-build-plan":
                return None
            steps = tuple(
                PlannedBuildStep(
                    str(item["step_id"]),
                    str(item["label"]),
                    str(item["tool"]),
                    tuple(map(str, item["arguments"])),
                    tuple(map(str, item["inputs"])),
                    tuple(map(str, item["outputs"])),
                    bool(item.get("phone_changed", False)),
                )
                for item in data.pop("steps")
            )
            expected_outputs = tuple(data.pop("expected_outputs"))
            plan = DeviceBuildExecutionPlan(**data, steps=steps, expected_outputs=expected_outputs)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None
        project = self.store.get(project_id)
        pack = next(
            (item for item in self.registry.packs if item.pack_id == project.device_pack_id), None
        )
        payload = asdict(plan)
        digest = str(payload.pop("plan_digest"))
        if plan.schema_version == 1:
            payload.pop("workspace_plan_digest", None)
        if (
            plan.schema_version not in {1, 2}
            or plan.project_id != project_id
            or re.fullmatch(r"[0-9a-f]{32}", plan.plan_id) is None
            or pack is None
            or (
                plan.pack_sha256 != pack.sha256
                and plan.pack_sha256 not in pack.build_compatible_pack_sha256
            )
            or pack.build_contract is None
            or plan.contract_id != pack.build_contract.contract_id
            or plan.contract_version != pack.build_contract.version
            or plan.source_archive_sha256 != pack.build_contract.source.archive_sha256
            or plan.source_payload_sha256 != pack.build_contract.source.payload_sha256
            or plan.expected_outputs != pack.build_contract.allowed_outputs
            or plan.phone_changed
            or any(step.phone_changed for step in plan.steps)
            or (plan.schema_version == 1 and bool(plan.workspace_plan_digest))
            or (plan.schema_version == 2 and not _is_sha256(plan.workspace_plan_digest))
            or _json_digest(payload) != digest
        ):
            return None
        return plan

    def verify_for_execution(self, project_id: str) -> DeviceBuildExecutionPlan:
        """Re-derive and rehash a saved local plan before any build process starts."""

        assessment = self.assess(project_id)
        if not assessment.ready:
            raise ProjectError(
                "Local build execution is blocked: " + ", ".join(assessment.blockers)
            )
        plan = self.load(project_id)
        if plan is None:
            raise ProjectError("Create a fresh deterministic Device Pack plan")
        if plan.execution_locked:
            raise ProjectError("This plan predates the local build executor; regenerate it")
        workspace_plan = self._verified_workspace_plan(project_id)
        if (
            workspace_plan is None
            or workspace_plan.tree_sha256 != plan.workspace_tree_sha256
            or (
                workspace_plan.schema_version >= 3
                and (
                    plan.schema_version < 2
                    or plan.workspace_plan_digest != workspace_plan.plan_digest
                )
            )
        ):
            raise ProjectError("The exact workspace build plan changed before local execution")
        project = self.store.get(project_id)
        pack = next(
            (item for item in self.registry.packs if item.pack_id == project.device_pack_id),
            None,
        )
        if pack is None or pack.build_contract is None:
            raise ProjectError("The selected Device Pack build contract is unavailable")
        payload = self._payload_manifest(project_id)
        if payload is None:
            raise ProjectError("Payload evidence is unavailable")
        records = {str(item["name"]): item for item in payload["partitions"]}
        for rule in pack.build_contract.partitions:
            image = self.store.workspace / str(records[rule.name]["extracted_path"])
            if _sha256(image) != rule.source_sha256:
                raise ProjectError(f"Protected {rule.name} image changed after planning")
        expected = self._steps(
            project_id,
            pack.build_contract,
            records,
            plan.plan_id,
        )
        if plan.steps != expected:
            raise ProjectError("Saved build steps do not match the current Device Pack contract")
        return plan

    def _verified_workspace_plan(self, project_id: str):
        plan = RomBuildPlanner(self.store).load(project_id)
        if plan is None:
            return None
        if plan.schema_version >= 3:
            if not self.tool_statuses:
                return None
            planner = RomBuildPlanner(self.store, self.tool_statuses, plan.required_tools)
        else:
            planner = RomBuildPlanner(self.store)
        try:
            return plan if planner.verify_tree(project_id).valid else None
        except (OSError, ProjectError, TypeError, ValueError):
            return None

    def _steps(
        self,
        project_id: str,
        contract: DeviceBuildContract,
        records: dict[str, dict],
        plan_id: str,
    ) -> tuple[PlannedBuildStep, ...]:
        if re.fullmatch(r"[0-9a-f]{32}", plan_id) is None:
            raise ProjectError("Invalid local build plan identifier")
        build_root = f"working_roms/{project_id}/build-candidates/{plan_id}"
        metadata_root = f"projects/{project_id}/{self.METADATA_ROOT}"
        editable = next(rule for rule in contract.partitions if rule.mode == "rebuild")
        assert editable.erofs is not None and editable.avb_hashtree is not None
        filesystem_tree = f"working_roms/{project_id}/tree/partition_files/{editable.name}/root"
        filesystem_image = f"{build_root}/{editable.name}-filesystem.img"
        partition_image = f"{build_root}/{editable.name}.img"
        vbmeta_image = f"{build_root}/vbmeta_system.img"
        super_image = f"{build_root}/super.img"
        erofs = editable.erofs
        avb = editable.avb_hashtree
        descriptor_images = tuple(
            partition_image if name == editable.name else str(records[name]["extracted_path"])
            for name in contract.vbmeta_descriptor_partitions
        )
        mkfs_args = (
            f"-z{erofs.compression},level={erofs.compression_level}",
            "-Elegacy-compress" if erofs.legacy_compress else "",
            f"-T{erofs.timestamp}",
            "--all-time",
            f"-U{erofs.filesystem_uuid}",
            f"--mount-point={erofs.mount_point}",
            f"--file-contexts={metadata_root}/{editable.name}.file_contexts",
            filesystem_image,
            filesystem_tree,
        )
        steps = [
            PlannedBuildStep(
                "rebuild-erofs",
                f"Rebuild {editable.name} EROFS deterministically",
                "fakeroot",
                (
                    "-i",
                    f"{metadata_root}/{editable.name}.fakeroot",
                    "--",
                    "mkfs.erofs",
                    *(value for value in mkfs_args if value),
                ),
                (
                    filesystem_tree,
                    f"{metadata_root}/{editable.name}.fakeroot",
                    f"{metadata_root}/{editable.name}.file_contexts",
                ),
                (filesystem_image,),
            ),
            PlannedBuildStep(
                "verify-erofs",
                "Verify rebuilt EROFS image",
                "fsck.erofs",
                ("--xattrs", filesystem_image),
                (filesystem_image,),
                (),
            ),
            PlannedBuildStep(
                "stage-partition-image",
                f"Create the fixed-size {editable.name} image staging copy",
                "ROMVERSE internal copier",
                ("copy-sparse", filesystem_image, partition_image),
                (filesystem_image,),
                (partition_image,),
            ),
            PlannedBuildStep(
                "add-avb-footer",
                f"Add contract-bound AVB hashtree footer to {editable.name}",
                "avbtool",
                tuple(
                    value
                    for value in (
                        "add_hashtree_footer",
                        "--image",
                        partition_image,
                        "--partition_name",
                        editable.name,
                        "--partition_size",
                        str(editable.size_bytes),
                        "--hash_algorithm",
                        avb.hash_algorithm,
                        "--salt",
                        avb.salt,
                        "--do_not_generate_fec" if not avb.generate_fec else "",
                    )
                    if value
                ),
                (partition_image,),
                (partition_image,),
            ),
            PlannedBuildStep(
                "make-vbmeta-system",
                "Recreate vbmeta_system from exact descriptors",
                "avbtool",
                (
                    "make_vbmeta_image",
                    "--output",
                    vbmeta_image,
                    *tuple(
                        value
                        for image in descriptor_images
                        for value in ("--include_descriptors_from_image", image)
                    ),
                    "--padding_size",
                    "4096",
                ),
                descriptor_images,
                (vbmeta_image,),
            ),
            self._super_step(contract, records, partition_image, super_image),
            PlannedBuildStep(
                "unpack-and-compare",
                "Unsparse, unpack, and byte-compare every logical partition",
                "ROMVERSE internal verifier",
                ("verify-all-logical-partitions",),
                (super_image, partition_image)
                + tuple(
                    str(records[rule.name]["extracted_path"])
                    for rule in contract.partitions
                    if rule.mode == "passthrough"
                ),
                (f"{build_root}/verification.romverse",),
            ),
        ]
        return tuple(steps)

    @staticmethod
    def _super_step(
        contract: DeviceBuildContract,
        records: dict[str, dict],
        editable_image: str,
        super_image: str,
    ) -> PlannedBuildStep:
        arguments = [
            "--metadata-size",
            str(contract.metadata_size_bytes),
            "--metadata-slots",
            str(contract.metadata_slots),
            "--super-name",
            "super",
            "--device",
            f"super:{contract.super_size_bytes}",
        ]
        for group in contract.groups:
            arguments.extend(("--group", f"{group.name}:{group.maximum_size_bytes}"))
        a_group = next(group.name for group in contract.groups if group.name.endswith("_a"))
        b_group = next(group.name for group in contract.groups if group.name.endswith("_b"))
        inputs = []
        for rule in contract.partitions:
            image = (
                editable_image
                if rule.mode == "rebuild"
                else str(records[rule.name]["extracted_path"])
            )
            inputs.append(image)
            arguments.extend(
                (
                    "--partition",
                    f"{rule.name}_a:readonly:{rule.size_bytes}:{a_group}",
                    "--image",
                    f"{rule.name}_a={image}",
                    "--partition",
                    f"{rule.name}_b:readonly:0:{b_group}",
                )
            )
        if contract.virtual_ab:
            arguments.append("--virtual-ab")
        arguments.extend(("--sparse", "--output", super_image))
        return PlannedBuildStep(
            "assemble-super",
            "Assemble exact sparse virtual A/B super image",
            "lpmake",
            tuple(arguments),
            tuple(inputs),
            (super_image,),
        )

    def _payload_manifest(self, project_id: str) -> dict | None:
        path = self.store.projects_root / project_id / "payload-manifest.romverse"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if (
                data.get("format") != "romverse.payload-manifest"
                or data.get("project_id") != project_id
            ):
                return None
            return data
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None

    def _metadata_ready(
        self,
        project_id: str,
        contract: DeviceBuildContract,
        rule: PartitionBuildRule,
    ) -> bool:
        path = self.store.projects_root / project_id / self.METADATA_ROOT / f"{rule.name}.romverse"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if (
                data.get("format") != "romverse.rebuild-metadata"
                or data.get("partition") != rule.name
                or data.get("source_sha256") != rule.source_sha256
                or data.get("contract_id") not in {None, contract.contract_id}
                or data.get("contract_version") not in {None, contract.version}
            ):
                return False
            for key in ("fakeroot", "file_contexts"):
                relative = str(data[f"{key}_path"])
                expected = str(data[f"{key}_sha256"])
                unresolved = path.parent / relative
                if unresolved.is_symlink():
                    return False
                candidate = unresolved.resolve(strict=True)
                if (
                    not candidate.is_relative_to(path.parent.resolve())
                    or not candidate.is_file()
                    or candidate.stat().st_size > self.MAX_METADATA_BYTES
                    or _sha256(candidate) != expected
                ):
                    return False
            return True
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return False

    def _workspace_file(self, relative: str) -> bool:
        try:
            path = (self.store.workspace / relative).resolve(strict=True)
            return (
                path.is_relative_to(self.store.working_root.resolve())
                and path.is_file()
                and not path.is_symlink()
            )
        except (OSError, RuntimeError):
            return False


def _check(
    check_id: str,
    label: str,
    passed: bool,
    evidence: str,
    resolution: str,
) -> ContractCheck:
    return ContractCheck(
        check_id,
        label,
        ContractCheckStatus.PASS if passed else ContractCheckStatus.BLOCKED,
        evidence,
        resolution,
    )


def _blocked(check_id: str, label: str, evidence: str, resolution: str) -> ContractCheck:
    return _check(check_id, label, False, evidence, resolution)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _json_digest(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _atomic_json(path: Path, payload: dict) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{uuid4().hex}")
    try:
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
