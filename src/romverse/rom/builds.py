from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
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


class RomBuildPlanner:
    PLAN_NAME = "build-plan.romverse"

    def __init__(self, store: RomProjectStore) -> None:
        self.store = store
        self.inspection = RomInspectionService(store)

    def plan(self, project_id: str) -> BuildPlan:
        project = self.store.get(project_id)
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
        plan = BuildPlan(
            2,
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
        )
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
            return BuildPlan(
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
            )
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None

    def verify_tree(self, project_id: str) -> ArtifactVerification:
        plan = self.load(project_id)
        if plan is None:
            return ArtifactVerification(False, "No saved build plan")
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
