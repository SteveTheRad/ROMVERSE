from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime, timedelta
from pathlib import Path

from romverse.device_packs.models import DeviceBuildContract
from romverse.device_packs.registry import DevicePackRegistry
from romverse.infrastructure.local_store import atomic_write_json, read_json_object
from romverse.infrastructure.process import CommandResult, CommandRunner
from romverse.infrastructure.toolchain_evidence import (
    ToolchainEvidenceError,
    ToolchainEvidenceService,
)
from romverse.infrastructure.toolchain_versions import (
    VersionedToolchainError,
    VersionedToolchainStore,
)
from romverse.infrastructure.tools import ToolStatus
from romverse.rom.build_contracts import (
    DeviceBuildContractService,
    DeviceBuildExecutionPlan,
    PlannedBuildStep,
)
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore


@dataclass(frozen=True, slots=True)
class BuildStepReceipt:
    step_id: str
    label: str
    tool: str
    started_at: str
    completed_at: str
    returncode: int
    log_path: str
    output_sizes: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class BuildOutputReceipt:
    name: str
    path: str
    size_bytes: int
    modified_ns: int
    sha256: str


@dataclass(frozen=True, slots=True)
class LocalBuildReceipt:
    schema_version: int
    project_id: str
    plan_id: str
    plan_digest: str
    contract_id: str
    started_at: str
    completed_at: str
    status: str
    failure: str
    steps: tuple[BuildStepReceipt, ...]
    outputs: tuple[BuildOutputReceipt, ...]
    phone_changed: bool
    receipt_digest: str
    toolchain_manifest_digest: str = ""


class LocalDeviceBuildExecutor:
    """Execute an exact Device Pack plan locally; this class has no device transport."""

    RECEIPT_NAME = "local-build-receipt.romverse"
    ATTEMPT_NAME = "latest-local-build-attempt.romverse"
    MIN_RESERVE = 4 * 1024 * 1024 * 1024
    MAX_RECEIPT_BYTES = 2 * 1024 * 1024
    MAX_STEPS = 128
    MAX_OUTPUTS = 64
    TOOL_MAP = {
        "fakeroot": "Fakeroot",
        "fsck.erofs": "EROFS Verifier",
        "avbtool": "AVBTool",
        "lpmake": "LP Make",
    }
    VERIFY_TOOLS = {
        "simg2img": "simg2img",
        "lpunpack": "LP Unpack",
        "lpdumps": "LP Dump",
    }

    def __init__(
        self,
        store: RomProjectStore,
        registry: DevicePackRegistry,
        tool_statuses: tuple[ToolStatus, ...],
        runner: CommandRunner,
    ) -> None:
        self.store = store
        self.registry = registry
        self.tool_statuses = tool_statuses
        self.runner = runner
        self.contracts = DeviceBuildContractService(store, registry, tool_statuses)

    def execute(self, project_id: str) -> LocalBuildReceipt:
        plan = self.contracts.verify_for_execution(project_id)
        project = self.store.get(project_id)
        pack = next(
            (item for item in self.registry.packs if item.pack_id == project.device_pack_id),
            None,
        )
        if pack is None or pack.build_contract is None:
            raise ProjectError("Exact Device Pack build contract is unavailable")
        contract = pack.build_contract
        tools = self._verified_tools()
        toolchain_manifest_digest, locked_tool_hashes, tools = self._capture_toolchain(
            project_id,
            tools,
        )
        output_root = self._output_root(project_id, plan.plan_id)
        if output_root.exists():
            raise ProjectError(
                "This versioned build output already exists; create a fresh plan before retrying"
            )
        required_free = (
            contract.super_size_bytes
            + sum(rule.source_size_bytes for rule in contract.partitions)
            + sum(rule.size_bytes for rule in contract.partitions if rule.mode == "rebuild")
            + self.MIN_RESERVE
        )
        free = shutil.disk_usage(self.store.workspace).free
        if free < required_free:
            raise ProjectError(
                f"Local build requires at least {_byte_label(required_free)} free; "
                f"{_byte_label(free)} is available"
            )
        output_root.mkdir(parents=True)
        logs = output_root / "logs"
        logs.mkdir()
        started = _now()
        step_receipts: list[BuildStepReceipt] = []
        active_step = "preflight"
        try:
            for step in plan.steps:
                active_step = step.step_id
                step_receipts.append(
                    self._execute_step(
                        step,
                        plan,
                        contract,
                        tools,
                        locked_tool_hashes,
                        output_root,
                        logs,
                    )
                )
            self._assert_locked_tools(tools, locked_tool_hashes)
            outputs = tuple(
                self._output_receipt(output_root / name, name, project_id)
                for name in plan.expected_outputs
            )
            receipt = self._receipt(
                project_id,
                plan,
                contract,
                started,
                "success",
                "",
                tuple(step_receipts),
                outputs,
                toolchain_manifest_digest,
            )
            atomic_write_json(
                output_root / self.RECEIPT_NAME,
                {"format": "romverse.local-build-receipt", **asdict(receipt)},
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
            self._record_attempt(receipt)
            return receipt
        except (OSError, ProjectError) as exc:
            failure = f"{active_step}: {exc}"
            receipt = self._receipt(
                project_id,
                plan,
                contract,
                started,
                "failed",
                failure,
                tuple(step_receipts),
                (),
                toolchain_manifest_digest,
            )
            self._record_attempt(receipt)
            raise ProjectError(f"Local build stopped safely at {failure}") from exc

    def load_receipt(self, project_id: str) -> LocalBuildReceipt | None:
        path = self.store.projects_root / project_id / self.ATTEMPT_NAME
        try:
            data = read_json_object(
                path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
            schema_version = data.get("schema_version")
            expected = {"format", *(field.name for field in fields(LocalBuildReceipt))}
            if schema_version == 1:
                expected.remove("toolchain_manifest_digest")
            if set(data) != expected or data.pop("format") != "romverse.local-build-attempt":
                return None
            if schema_version == 1:
                data["toolchain_manifest_digest"] = ""
            raw_steps = data.pop("steps")
            raw_outputs = data.pop("outputs")
            if (
                not isinstance(raw_steps, list)
                or not isinstance(raw_outputs, list)
                or not 1 <= len(raw_steps) <= self.MAX_STEPS
                or not 1 <= len(raw_outputs) <= self.MAX_OUTPUTS
                or any(
                    not isinstance(item, dict)
                    or set(item) != {field.name for field in fields(BuildStepReceipt)}
                    for item in raw_steps
                )
                or any(
                    not isinstance(item, dict)
                    or set(item) != {field.name for field in fields(BuildOutputReceipt)}
                    for item in raw_outputs
                )
            ):
                return None
            steps = tuple(
                BuildStepReceipt(
                    str(item["step_id"]),
                    str(item["label"]),
                    str(item["tool"]),
                    str(item["started_at"]),
                    str(item["completed_at"]),
                    int(item["returncode"]),
                    str(item["log_path"]),
                    tuple((str(name), int(size)) for name, size in item["output_sizes"]),
                )
                for item in raw_steps
            )
            outputs = tuple(
                BuildOutputReceipt(
                    str(item["name"]),
                    str(item["path"]),
                    int(item["size_bytes"]),
                    int(item["modified_ns"]),
                    str(item["sha256"]),
                )
                for item in raw_outputs
            )
            receipt = LocalBuildReceipt(**data, steps=steps, outputs=outputs)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None
        payload = asdict(receipt)
        digest = str(payload.pop("receipt_digest"))
        if receipt.schema_version == 1:
            payload.pop("toolchain_manifest_digest")
        plan = self.contracts.load(project_id)
        toolchain_manifest_valid = receipt.schema_version == 1
        if receipt.schema_version == 2 and _sha256_value(receipt.toolchain_manifest_digest):
            try:
                manifest = ToolchainEvidenceService(
                    self.store.workspace,
                    platform.system() or os.name,
                ).load_private(receipt.toolchain_manifest_digest)
                toolchain_manifest_valid = (
                    manifest.complete
                    and manifest.scope == f"local-build:{project_id}"
                    and manifest.execution_authority == "none"
                    and not manifest.phone_changed
                )
            except (OSError, ValueError, ToolchainEvidenceError):
                toolchain_manifest_valid = False
        if (
            receipt.schema_version not in {1, 2}
            or receipt.project_id != project_id
            or not _aware_timestamp(receipt.started_at)
            or not _aware_timestamp(receipt.completed_at)
            or receipt.status != "success"
            or receipt.phone_changed
            or receipt.failure
            or not _sha256_value(receipt.plan_digest)
            or not _sha256_value(receipt.receipt_digest)
            or not toolchain_manifest_valid
            or any(not self._valid_step(item) for item in steps)
            or any(not self._valid_output(item) for item in outputs)
            or plan is None
            or receipt.plan_id != plan.plan_id
            or receipt.plan_digest != plan.plan_digest
            or _json_digest(payload) != digest
        ):
            return None
        expected = set(plan.expected_outputs)
        if {output.name for output in outputs} != expected:
            return None
        for output in outputs:
            try:
                candidate = self._workspace_path(output.path, must_exist=True)
                stat = candidate.stat()
                if (
                    not candidate.is_relative_to(self._output_root(project_id, plan.plan_id))
                    or not candidate.is_file()
                    or candidate.is_symlink()
                    or stat.st_size != output.size_bytes
                    or stat.st_mtime_ns != output.modified_ns
                ):
                    return None
            except (OSError, ProjectError):
                return None
        for step in steps:
            try:
                log = self._workspace_path(step.log_path, must_exist=True)
                if not log.is_file() or log.is_symlink():
                    return None
            except (OSError, ProjectError):
                return None
        return receipt

    @staticmethod
    def _valid_step(item: BuildStepReceipt) -> bool:
        return bool(
            _label(item.step_id, 100)
            and _label(item.label, 200)
            and _label(item.tool, 160)
            and _aware_timestamp(item.started_at)
            and _aware_timestamp(item.completed_at)
            and type(item.returncode) is int
            and item.returncode == 0
            and _relative_path(item.log_path)
            and len(item.output_sizes) <= LocalDeviceBuildExecutor.MAX_OUTPUTS
            and all(
                _relative_path(path) and type(size) is int and size >= 0
                for path, size in item.output_sizes
            )
        )

    @staticmethod
    def _valid_output(item: BuildOutputReceipt) -> bool:
        return bool(
            _label(item.name, 120)
            and _relative_path(item.path)
            and type(item.size_bytes) is int
            and item.size_bytes > 0
            and type(item.modified_ns) is int
            and item.modified_ns > 0
            and _sha256_value(item.sha256)
        )

    def _execute_step(
        self,
        step: PlannedBuildStep,
        plan: DeviceBuildExecutionPlan,
        contract: DeviceBuildContract,
        tools: dict[str, Path],
        locked_tool_hashes: dict[str, str],
        output_root: Path,
        logs: Path,
    ) -> BuildStepReceipt:
        if step.phone_changed:
            raise ProjectError("A local build plan attempted to declare a phone-changing step")
        self._assert_locked_tools(tools, locked_tool_hashes)
        started = _now()
        log_path = logs / f"{step.step_id}.log"
        if step.tool == "ROMVERSE internal copier":
            self._copy_sparse(step, output_root)
            result = CommandResult(("ROMVERSE", step.step_id), 0, "Sparse copy complete", "")
        elif step.tool == "ROMVERSE internal verifier":
            result = self._verify_super(step, plan, contract, tools, output_root)
        else:
            command = self._external_command(step, tools)
            result = self.runner.run(command, timeout=4 * 60 * 60, cwd=self.store.workspace)
        self._assert_locked_tools(tools, locked_tool_hashes)
        log_path.write_text(
            "COMMAND\n"
            + "\n".join(result.args)
            + "\n\nSTDOUT\n"
            + result.stdout
            + "\n\nSTDERR\n"
            + result.stderr,
            encoding="utf-8",
        )
        if not result.ok:
            detail = (result.stderr or result.stdout).strip().splitlines()
            raise ProjectError(f"{step.label} failed" + (f": {detail[-1][:240]}" if detail else ""))
        output_sizes = []
        for relative in step.outputs:
            output = self._workspace_path(relative, must_exist=True)
            if not output.is_file():
                raise ProjectError(f"{step.label} did not produce {Path(relative).name}")
            output_sizes.append((relative, output.stat().st_size))
        return BuildStepReceipt(
            step.step_id,
            step.label,
            step.tool,
            started,
            _now(),
            result.returncode,
            log_path.relative_to(self.store.workspace).as_posix(),
            tuple(output_sizes),
        )

    def _external_command(self, step: PlannedBuildStep, tools: dict[str, Path]) -> tuple[str, ...]:
        status_name = self.TOOL_MAP.get(step.tool)
        if status_name is None:
            raise ProjectError(f"Unsupported external build tool: {step.tool}")
        path_tokens = {
            relative: str(self._workspace_path(relative))
            for relative in (*step.inputs, *step.outputs)
        }
        arguments = []
        for token in step.arguments:
            if token in path_tokens:
                arguments.append(path_tokens[token])
            elif token.startswith("--file-contexts="):
                relative = token.split("=", 1)[1]
                arguments.append("--file-contexts=" + str(self._workspace_path(relative)))
            elif token == "mkfs.erofs":
                arguments.append(str(tools["EROFS Builder"]))
            elif "=" in token and token.split("=", 1)[1] in path_tokens:
                name, relative = token.split("=", 1)
                arguments.append(f"{name}={path_tokens[relative]}")
            else:
                arguments.append(token)
        return (str(tools[status_name]), *arguments)

    def _copy_sparse(self, step: PlannedBuildStep, output_root: Path) -> None:
        if len(step.arguments) != 3 or step.arguments[0] != "copy-sparse":
            raise ProjectError("Invalid internal sparse-copy instruction")
        source = self._workspace_path(step.arguments[1], must_exist=True)
        target = self._workspace_path(step.arguments[2])
        if not target.is_relative_to(output_root) or target.exists():
            raise ProjectError("Sparse-copy output is outside the new build candidate")
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as reader, target.open("xb") as writer:
            while chunk := reader.read(4 * 1024 * 1024):
                if chunk.count(0) == len(chunk):
                    writer.seek(len(chunk), os.SEEK_CUR)
                else:
                    writer.write(chunk)
            writer.truncate(source.stat().st_size)

    def _verify_super(
        self,
        step: PlannedBuildStep,
        plan: DeviceBuildExecutionPlan,
        contract: DeviceBuildContract,
        tools: dict[str, Path],
        output_root: Path,
    ) -> CommandResult:
        if step.arguments != ("verify-all-logical-partitions",):
            raise ProjectError("Invalid internal super verification instruction")
        super_image = output_root / "super.img"
        if not super_image.is_file():
            raise ProjectError("Sparse super image is missing")
        staging = output_root / ".verification.part"
        raw = staging / "super.raw.img"
        unpacked = staging / "unpacked"
        staging.mkdir()
        unpacked.mkdir()
        reports = []
        try:
            commands = (
                (str(tools["simg2img"]), str(super_image), str(raw)),
                (str(tools["LP Unpack"]), str(raw), str(unpacked)),
                (str(tools["LP Dump"]), str(raw)),
            )
            results = []
            for command in commands:
                result = self.runner.run(command, timeout=4 * 60 * 60, cwd=self.store.workspace)
                results.append(result)
                if not result.ok:
                    return result
            payload = self.contracts._payload_manifest(plan.project_id)
            if payload is None:
                raise ProjectError("Payload evidence disappeared during verification")
            records = {str(item["name"]): item for item in payload["partitions"]}
            for rule in contract.partitions:
                expected = (
                    output_root / f"{rule.name}.img"
                    if rule.mode == "rebuild"
                    else self._workspace_path(str(records[rule.name]["extracted_path"]), True)
                )
                actual = unpacked / f"{rule.name}_a.img"
                if not actual.is_file():
                    raise ProjectError(f"Unpacked super is missing {rule.name}_a")
                expected_hash = _sha256(expected)
                actual_hash = _sha256(actual)
                if actual.stat().st_size != expected.stat().st_size or actual_hash != expected_hash:
                    raise ProjectError(f"Unpacked {rule.name}_a differs from its planned image")
                reports.append(
                    {
                        "partition": f"{rule.name}_a",
                        "size_bytes": actual.stat().st_size,
                        "sha256": actual_hash,
                        "matches": True,
                    }
                )
            verification = self._workspace_path(step.outputs[0])
            atomic_write_json(
                verification,
                {
                    "format": "romverse.super-verification",
                    "schema_version": 1,
                    "project_id": plan.project_id,
                    "plan_id": plan.plan_id,
                    "super_sha256": _sha256(super_image),
                    "partitions": reports,
                    "lpdump_sha256": hashlib.sha256(results[-1].stdout.encode()).hexdigest(),
                    "phone_changed": False,
                },
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
            return CommandResult(
                ("ROMVERSE", "verify-all-logical-partitions"),
                0,
                f"Verified {len(reports)} logical partitions byte-for-byte",
                "",
            )
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def _verified_tools(self) -> dict[str, Path]:
        available = {
            status.name: Path(status.path).resolve()
            for status in self.tool_statuses
            if status.available and status.path
        }
        required = set(self.TOOL_MAP.values()) | set(self.VERIFY_TOOLS.values()) | {"EROFS Builder"}
        missing = tuple(sorted(name for name in required if name not in available))
        if missing:
            raise ProjectError("Verified local build tools are missing: " + ", ".join(missing))
        if any(not available[name].is_file() for name in required):
            raise ProjectError("A verified local build executable is no longer available")
        return {name: available[name] for name in sorted(required)}

    def _capture_toolchain(
        self,
        project_id: str,
        tools: dict[str, Path],
    ) -> tuple[str, dict[str, str], dict[str, Path]]:
        required = tuple(sorted(tools))
        by_name = {status.name: status for status in self.tool_statuses}
        statuses = tuple(by_name[name] for name in required)
        try:
            service = ToolchainEvidenceService(
                self.store.workspace,
                platform.system() or os.name,
            )
            manifest = service.capture(
                statuses,
                required_tools=required,
                scope=f"local-build:{project_id}",
            )
            if not manifest.complete:
                raise ToolchainEvidenceError("The exact build toolchain is incomplete")
            service.save_private(manifest)
            isolated = VersionedToolchainStore(self.store.workspace).isolate(tools, manifest)
        except (OSError, ValueError, ToolchainEvidenceError, VersionedToolchainError) as exc:
            raise ProjectError(f"Exact build toolchain proof failed: {exc}") from exc
        return (
            manifest.manifest_digest,
            {item.name: item.sha256 for item in manifest.tools if item.state == "verified"},
            isolated,
        )

    @staticmethod
    def _assert_locked_tools(tools: dict[str, Path], expected: dict[str, str]) -> None:
        if set(tools) != set(expected):
            raise ProjectError("The exact build toolchain lock is incomplete")
        for name, executable in tools.items():
            try:
                if not executable.is_file() or executable.is_symlink():
                    raise ProjectError(f"Locked build tool is unavailable: {name}")
                digest = _sha256(executable)
            except OSError as exc:
                raise ProjectError(f"Locked build tool is unavailable: {name}") from exc
            if digest != expected[name]:
                raise ProjectError(
                    f"Locked build tool changed after preflight: {name}. "
                    "Re-open Forge Arsenal and create a fresh build plan."
                )

    def _output_root(self, project_id: str, plan_id: str) -> Path:
        root = (self.store.working_root / project_id / "build-candidates" / plan_id).resolve()
        boundary = (self.store.working_root / project_id / "build-candidates").resolve()
        if not root.is_relative_to(boundary):
            raise ProjectError("Build output escaped the versioned candidate boundary")
        return root

    def _workspace_path(self, relative: str, must_exist: bool = False) -> Path:
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ProjectError("Build plan contains an unsafe workspace path")
        unresolved = self.store.workspace / candidate
        if unresolved.is_symlink():
            raise ProjectError("Build inputs and outputs cannot be symbolic links")
        resolved = unresolved.resolve(strict=must_exist)
        if not resolved.is_relative_to(self.store.workspace.resolve()):
            raise ProjectError("Build path escaped the ROMVERSE workspace")
        return resolved

    def _output_receipt(self, path: Path, name: str, project_id: str) -> BuildOutputReceipt:
        if not path.is_file() or path.is_symlink():
            raise ProjectError(f"Expected build output is missing: {name}")
        boundary = (self.store.working_root / project_id / "build-candidates").resolve()
        resolved = path.resolve()
        if not resolved.is_relative_to(boundary):
            raise ProjectError(f"Build output escaped its boundary: {name}")
        return BuildOutputReceipt(
            name,
            resolved.relative_to(self.store.workspace).as_posix(),
            resolved.stat().st_size,
            resolved.stat().st_mtime_ns,
            _sha256(resolved),
        )

    def _receipt(
        self,
        project_id: str,
        plan: DeviceBuildExecutionPlan,
        contract: DeviceBuildContract,
        started: str,
        status: str,
        failure: str,
        steps: tuple[BuildStepReceipt, ...],
        outputs: tuple[BuildOutputReceipt, ...],
        toolchain_manifest_digest: str,
    ) -> LocalBuildReceipt:
        payload = {
            "schema_version": 2,
            "project_id": project_id,
            "plan_id": plan.plan_id,
            "plan_digest": plan.plan_digest,
            "contract_id": contract.contract_id,
            "started_at": started,
            "completed_at": _now(),
            "status": status,
            "failure": failure,
            "steps": [asdict(step) for step in steps],
            "outputs": [asdict(output) for output in outputs],
            "phone_changed": False,
            "toolchain_manifest_digest": toolchain_manifest_digest,
        }
        digest = _json_digest(payload)
        return LocalBuildReceipt(
            2,
            project_id,
            plan.plan_id,
            plan.plan_digest,
            contract.contract_id,
            started,
            str(payload["completed_at"]),
            status,
            failure,
            steps,
            outputs,
            False,
            digest,
            toolchain_manifest_digest,
        )

    def _record_attempt(self, receipt: LocalBuildReceipt) -> None:
        atomic_write_json(
            self.store.projects_root / receipt.project_id / self.ATTEMPT_NAME,
            {"format": "romverse.local-build-attempt", **asdict(receipt)},
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_RECEIPT_BYTES,
        )


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _json_digest(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


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


def _label(value: object, maximum: int) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= maximum
        and value == " ".join(value.replace("\x00", " ").split())
    )


def _relative_path(value: object) -> bool:
    if not isinstance(value, str) or not 1 <= len(value) <= 4_096:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts


def _byte_label(value: int) -> str:
    size = float(max(0, value))
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"
