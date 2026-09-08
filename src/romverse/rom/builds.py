from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from romverse.guardian.models import OperationClass
from romverse.guardian.planning import (
    CheckStatus,
    GuardianPreflight,
    OperationManifest,
    PlannedStep,
    Precondition,
)
from romverse.infrastructure.toolchain_evidence import (
    ToolchainEvidenceError,
    ToolchainEvidenceService,
)
from romverse.infrastructure.tools import ToolStatus
from romverse.platform.host import current_host
from romverse.rom.inspection import RomInspectionService
from romverse.rom.models import ArtifactVerification, ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.rom.recipes import RecipeStore


@dataclass(frozen=True, slots=True)
class BuildPlan:
    schema_version: int
    project_id: str
    created_at: str
    source_tree: str
    device_pack_id: str
    partitions: tuple[str, ...]
    input_files: tuple[str, ...]
    execution_locked: bool = True
    guardian_status: str = "blocked"
    guardian_risk: str = "none"
    guardian_reasons: tuple[str, ...] = ()
    guardian_manifest_digest: str = ""
    tree_sha256: str = ""
    recipe_digest: str = ""
    input_symlinks: tuple[tuple[str, str], ...] = ()
    source_sha256: str = ""
    required_tools: tuple[str, ...] = ()
    toolchain_manifest_digest: str = ""
    guided_choice_digest: str = ""
    local_only: bool = True
    flashable: bool = False
    execution_authority: str = "none"
    plan_digest: str = ""


class RomBuildPlanner:
    PLAN_NAME = "build-plan.romverse"

    def __init__(
        self,
        store: RomProjectStore,
        tool_statuses: tuple[ToolStatus, ...] = (),
        required_tools: tuple[str, ...] = (),
    ) -> None:
        self.store = store
        self.inspection = RomInspectionService(store)
        self.tool_statuses = tool_statuses
        self.required_tools = tuple(dict.fromkeys(required_tools))

    def plan(self, project_id: str) -> BuildPlan:
        project = self.store.get(project_id)
        if project.original is None:
            raise ProjectError("Import a protected original before planning a build")
        source = self.store.original_path(project_id)
        try:
            source_before = source.stat()
        except OSError as exc:
            raise ProjectError(f"Protected original is unavailable: {exc}") from exc
        verification = self.store.verify_original(project_id)
        if not verification.valid:
            raise ProjectError(f"Original integrity check failed: {verification.status}")
        report = self.inspection.load_report(project_id)
        if report is None:
            raise ProjectError("Current structure inspection evidence is required")
        # Build inputs must never trust the fast display index. Re-enumerate the
        # current tree on this background planning operation before deriving hashes.
        summary = self.inspection.refresh_working_tree_summary(project_id)
        if summary is None:
            raise ProjectError("Extract a verified archive before planning a build")
        root = self.store.working_root / project_id / "tree"
        inputs, symlinks = _tree_inventory(root)
        partitions = tuple(
            sorted({Path(path).stem for path in summary.notable_files if path.endswith(".img")})
        )
        tree_digest = _tree_digest(root, inputs, symlinks)
        manifest = OperationManifest(
            1,
            uuid4().hex,
            datetime.now(UTC).isoformat(),
            "ROM build dry-run",
            "rom_build",
            project_id,
            (
                Precondition(
                    "original",
                    "Protected original verified",
                    CheckStatus.PASS,
                    "SHA-256 provenance is recorded",
                ),
                Precondition("tree", "Contained working tree exists", CheckStatus.PASS, str(root)),
            ),
            (
                PlannedStep(
                    "plan",
                    "Generate deterministic build inputs",
                    "Describe future build inputs without execution",
                    OperationClass.READ_ONLY,
                    "No files or devices changed",
                    True,
                ),
            ),
        )
        assessment = GuardianPreflight().assess(manifest)
        recipe = RecipeStore().load(self.store.projects_root / project_id)
        try:
            source_after = source.stat()
        except OSError as exc:
            raise ProjectError(f"Protected original became unavailable: {exc}") from exc
        current_project = self.store.get(project_id)
        if (
            current_project != project
            or self.inspection.load_report(project_id) != report
            or source_before.st_dev != source_after.st_dev
            or source_before.st_ino != source_after.st_ino
            or source_before.st_size != source_after.st_size
            or source_before.st_mtime_ns != source_after.st_mtime_ns
        ):
            raise ProjectError("Project, source, or inspection evidence changed during dry run")
        toolchain_manifest = self._capture_toolchain_manifest()
        schema_version = 3 if toolchain_manifest is not None else 2
        plan = BuildPlan(
            schema_version,
            project_id,
            datetime.now(UTC).isoformat(),
            root.relative_to(self.store.workspace).as_posix(),
            project.device_pack_id,
            partitions,
            inputs,
            True,
            assessment.status.value,
            assessment.risk.value,
            assessment.reasons,
            assessment.manifest_digest,
            tree_digest.hexdigest(),
            recipe.digest() if recipe is not None else "",
            symlinks,
            project.original.sha256,
            toolchain_manifest.required_tools if toolchain_manifest is not None else (),
            toolchain_manifest.manifest_digest if toolchain_manifest is not None else "",
            _guided_choice_digest(self.store, project_id) if toolchain_manifest is not None else "",
            True,
            False,
            "none",
        )
        if schema_version >= 3:
            plan = replace(plan, plan_digest=_plan_digest(plan))
        path = self.store.projects_root / project_id / self.PLAN_NAME
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"format": "romverse.build-plan", **asdict(plan)}, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
        return plan

    def load(self, project_id: str) -> BuildPlan | None:
        path = self.store.projects_root / project_id / self.PLAN_NAME
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("format") != "romverse.build-plan":
                return None
            plan = BuildPlan(
                int(data["schema_version"]),
                str(data["project_id"]),
                str(data["created_at"]),
                str(data["source_tree"]),
                str(data["device_pack_id"]),
                tuple(map(str, data["partitions"])),
                tuple(map(str, data["input_files"])),
                bool(data["execution_locked"]),
                str(data.get("guardian_status", "blocked")),
                str(data.get("guardian_risk", "none")),
                tuple(map(str, data.get("guardian_reasons", ()))),
                str(data.get("guardian_manifest_digest", "")),
                str(data.get("tree_sha256", "")),
                str(data.get("recipe_digest", "")),
                tuple(
                    (str(item[0]), str(item[1]))
                    for item in data.get("input_symlinks", ())
                    if isinstance(item, (list, tuple)) and len(item) == 2
                ),
                str(data.get("source_sha256", "")),
                tuple(map(str, data.get("required_tools", ()))),
                str(data.get("toolchain_manifest_digest", "")),
                str(data.get("guided_choice_digest", "")),
                data.get("local_only", True),
                data.get("flashable", False),
                str(data.get("execution_authority", "none")),
                str(data.get("plan_digest", "")),
            )
            if plan.schema_version >= 3 and (
                plan.project_id != project_id or not _valid_bound_plan(plan)
            ):
                return None
            return plan
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None

    def verify_tree(self, project_id: str) -> ArtifactVerification:
        plan = self.load(project_id)
        if plan is None:
            return ArtifactVerification(False, "No saved build plan")
        if plan.schema_version >= 3:
            binding_error = self._binding_error(plan)
            if binding_error:
                return ArtifactVerification(False, binding_error, plan.tree_sha256)
        source_tree = Path(plan.source_tree)
        if source_tree.is_absolute() or ".." in source_tree.parts:
            return ArtifactVerification(False, "Planned working tree path is unsafe")
        root = self.store.workspace / source_tree
        if root.is_symlink() or not root.is_dir():
            return ArtifactVerification(False, "Planned working tree is missing", plan.tree_sha256)
        if not root.resolve().is_relative_to(self.store.working_root.resolve()):
            return ArtifactVerification(False, "Planned working tree escapes the contained store")
        if plan.schema_version == 1 and any(path.is_symlink() for path in root.rglob("*")):
            return ArtifactVerification(
                False, "Working tree changed since build plan", plan.tree_sha256
            )
        try:
            actual_inputs, actual_symlinks = _tree_inventory(root)
        except ProjectError as exc:
            return ArtifactVerification(False, str(exc), plan.tree_sha256)
        if actual_inputs != plan.input_files:
            return ArtifactVerification(
                False, "Working tree file set changed since build plan", plan.tree_sha256
            )
        if plan.schema_version >= 2 and actual_symlinks != plan.input_symlinks:
            return ArtifactVerification(
                False, "Working tree symbolic-link set changed since build plan", plan.tree_sha256
            )
        for relative in plan.input_files:
            relative_path = Path(relative)
            if relative_path.is_absolute() or ".." in relative_path.parts:
                return ArtifactVerification(
                    False, f"Planned input path is unsafe: {relative}", plan.tree_sha256
                )
            path = root / relative
            if not path.is_file():
                return ArtifactVerification(
                    False, f"Planned input is missing: {relative}", plan.tree_sha256
                )
        if plan.schema_version >= 2:
            digest = _tree_digest(root, plan.input_files, plan.input_symlinks)
        else:
            digest = _legacy_tree_digest(root, plan.input_files)
        actual = digest.hexdigest()
        return ArtifactVerification(
            actual == plan.tree_sha256,
            "Working tree matches build plan"
            if actual == plan.tree_sha256
            else "Working tree changed since build plan",
            plan.tree_sha256,
            actual,
        )

    def _capture_toolchain_manifest(self):
        if not self.required_tools:
            return None
        by_name = {item.name: item for item in self.tool_statuses}
        selected = tuple(by_name[name] for name in self.required_tools if name in by_name)
        if len(selected) != len(self.required_tools) or any(not item.available for item in selected):
            raise ProjectError("Every source-scoped build tool needs fresh verified evidence")
        host = current_host()
        service = ToolchainEvidenceService(
            self.store.workspace,
            host.name,
            getattr(host, "distribution_id", ""),
        )
        try:
            manifest = service.capture(
                selected,
                required_tools=self.required_tools,
                scope="guided-build-plan",
            )
            if not manifest.complete or manifest.conflict_count:
                raise ProjectError("The source-scoped toolchain is incomplete or ambiguous")
            service.save_private(manifest)
        except ToolchainEvidenceError as exc:
            raise ProjectError(f"Toolchain evidence could not bind the build plan: {exc}") from exc
        return manifest

    def _binding_error(self, plan: BuildPlan) -> str:
        project = self.store.get(plan.project_id)
        if (
            project.original is None
            or project.original.sha256 != plan.source_sha256
            or not self.store.verify_original(plan.project_id).valid
        ):
            return "Protected source changed since build plan"
        if _guided_choice_digest(self.store, plan.project_id) != plan.guided_choice_digest:
            return "Guided build choices changed since build plan"
        host = current_host()
        service = ToolchainEvidenceService(
            self.store.workspace,
            host.name,
            getattr(host, "distribution_id", ""),
        )
        try:
            manifest = service.load_private(plan.toolchain_manifest_digest)
            if (
                not manifest.complete
                or manifest.conflict_count
                or manifest.host != host.name
                or manifest.distribution != getattr(host, "distribution_id", "")
                or manifest.required_tools != plan.required_tools
            ):
                return "Bound toolchain evidence is incomplete, ambiguous, or for another host"
            if self.tool_statuses:
                by_name = {item.name: item for item in self.tool_statuses}
                selected = tuple(by_name[name] for name in plan.required_tools if name in by_name)
                if len(selected) != len(plan.required_tools):
                    return "Current source-scoped tool evidence is incomplete"
                fresh = service.capture(
                    selected,
                    required_tools=plan.required_tools,
                    scope="guided-build-plan",
                )
                if not fresh.complete or fresh.conflict_count or fresh.tools != manifest.tools:
                    return "Current source-scoped tool evidence changed since build plan"
        except ToolchainEvidenceError:
            return "Bound toolchain evidence is unavailable or invalid"
        return ""

    def readiness(self, project_id: str) -> tuple[bool, tuple[str, ...]]:
        project = self.store.get(project_id)
        checks = [
            (project.original is not None, "Protected original imported"),
            (self.inspection.load_report(project_id) is not None, "Structure inspection saved"),
            (
                self.inspection.working_tree_exists(project_id),
                "Contained working tree extracted",
            ),
            (self.load(project_id) is not None, "Guardian-assessed build plan saved"),
        ]
        if self.load(project_id) is not None:
            checks.append((self.verify_tree(project_id).valid, "Working tree matches build plan"))
        missing = tuple(label for passed, label in checks if not passed)
        return not missing, missing


def _tree_inventory(root: Path) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    files: list[str] = []
    symlinks: list[tuple[str, str]] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            target = os.readlink(path)
            if len(target) > 4096 or any(ord(character) < 32 for character in target):
                raise ProjectError(f"Working tree has an unsafe symbolic-link target: {relative}")
            symlinks.append((relative, target))
        elif path.is_file():
            files.append(relative)
        elif not path.is_dir():
            raise ProjectError(f"Working tree contains an unsupported file type: {relative}")
    return tuple(sorted(files)), tuple(sorted(symlinks))


def _tree_digest(
    root: Path,
    files: tuple[str, ...],
    symlinks: tuple[tuple[str, str], ...],
) -> hashlib._Hash:
    digest = hashlib.sha256()
    links = dict(symlinks)
    for relative in sorted((*files, *links)):
        if relative in links:
            digest.update(b"L\0")
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(links[relative].encode("utf-8"))
            continue
        digest.update(b"F\0")
        digest.update(relative.encode("utf-8"))
        file_digest = hashlib.sha256()
        with (root / relative).open("rb") as stream:
            while chunk := stream.read(4 * 1024 * 1024):
                file_digest.update(chunk)
        digest.update(file_digest.digest())
    return digest


def _legacy_tree_digest(root: Path, files: tuple[str, ...]) -> hashlib._Hash:
    digest = hashlib.sha256()
    for relative in files:
        digest.update(relative.encode("utf-8"))
        file_digest = hashlib.sha256()
        with (root / relative).open("rb") as stream:
            while chunk := stream.read(4 * 1024 * 1024):
                file_digest.update(chunk)
        digest.update(file_digest.digest())
    return digest


def _guided_choice_digest(store: RomProjectStore, project_id: str) -> str:
    from romverse.rom.guided import GuidedMissionStore

    state = GuidedMissionStore(store.projects_root / project_id).load()
    payload = {
        "customization_skipped": state.customization_skipped,
        "recipe_skipped": state.recipe_skipped,
        "recipe_validated": state.recipe_validated,
        "root_choice": state.root_choice,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _plan_digest(plan: BuildPlan) -> str:
    payload = asdict(plan)
    payload.pop("plan_digest", None)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _valid_bound_plan(plan: BuildPlan) -> bool:
    return (
        plan.schema_version == 3
        and _is_sha256(plan.source_sha256)
        and _is_sha256(plan.tree_sha256)
        and _is_sha256(plan.toolchain_manifest_digest)
        and _is_sha256(plan.guided_choice_digest)
        and bool(plan.required_tools)
        and len(plan.required_tools) == len(set(plan.required_tools))
        and plan.local_only is True
        and plan.flashable is False
        and plan.execution_locked is True
        and plan.execution_authority == "none"
        and _is_sha256(plan.plan_digest)
        and plan.plan_digest == _plan_digest(plan)
    )


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)
