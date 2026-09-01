from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import shutil
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    read_json_object,
)
from romverse.rom.models import ProjectError


@dataclass(frozen=True, slots=True)
class RecipeStep:
    step_id: str
    operation: str
    target: str
    parameters: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class RomRecipe:
    schema_version: int
    recipe_id: str
    name: str
    description: str
    steps: tuple[RecipeStep, ...]
    execution_locked: bool = True
    persistence_schema_version: int = 1

    def digest(self) -> str:
        payload = json.dumps(
            {
                "schema_version": self.schema_version,
                "recipe_id": self.recipe_id,
                "name": self.name,
                "description": self.description,
                "steps": [asdict(step) for step in self.steps],
                "execution_locked": self.execution_locked,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class RecipeDraft:
    schema_version: int
    project_id: str
    source_original_sha256: str
    updated_at: str
    stage: int
    name: str
    description: str
    operation: str
    target: str
    source_input: str
    property_key: str
    property_value: str
    remove_acknowledged: bool
    replace_existing: bool
    steps: tuple[RecipeStep, ...]
    record_digest: str = ""


class RecipeDraftStore:
    """Private crash-resume state; never an executable Recipe or approval."""

    NAME = "recipe-draft.romverse"
    FORMAT = "romverse.recipe-draft"
    SCHEMA_VERSION = 1
    MAX_BYTES = 128 * 1024
    MAX_STEPS = 64
    MAX_PARAMETERS = 8
    MAX_PATH_CHARS = 4096
    MAX_VALUE_CHARS = 4096
    FIELDS = {
        "format",
        "schema_version",
        "project_id",
        "source_original_sha256",
        "updated_at",
        "stage",
        "name",
        "description",
        "operation",
        "target",
        "source_input",
        "property_key",
        "property_value",
        "remove_acknowledged",
        "replace_existing",
        "steps",
        "record_digest",
    }
    STEP_FIELDS = {"step_id", "operation", "target", "parameters"}

    def __init__(self, project_dir: Path, workspace: Path) -> None:
        self.project_dir = project_dir
        self.workspace = workspace
        self.path = project_dir / self.NAME

    def save(self, draft: RecipeDraft) -> RecipeDraft:
        normalized = RecipeDraft(
            self.SCHEMA_VERSION,
            draft.project_id,
            draft.source_original_sha256,
            datetime.now(UTC).isoformat(),
            draft.stage,
            draft.name,
            draft.description,
            draft.operation,
            draft.target,
            draft.source_input,
            draft.property_key,
            draft.property_value,
            draft.remove_acknowledged,
            draft.replace_existing,
            draft.steps,
            "",
        )
        if not self._valid(normalized, require_digest=False):
            raise ProjectError("Recipe draft contains invalid or unbounded fields")
        payload = self._payload(normalized, include_digest=False)
        sealed = RecipeDraft(
            normalized.schema_version,
            normalized.project_id,
            normalized.source_original_sha256,
            normalized.updated_at,
            normalized.stage,
            normalized.name,
            normalized.description,
            normalized.operation,
            normalized.target,
            normalized.source_input,
            normalized.property_key,
            normalized.property_value,
            normalized.remove_acknowledged,
            normalized.replace_existing,
            normalized.steps,
            _payload_digest(payload),
        )
        atomic_write_json(
            self.path,
            self._payload(sealed, include_digest=True),
            boundary=self.workspace,
            maximum_bytes=self.MAX_BYTES,
        )
        return sealed

    def load(self, project_id: str, source_original_sha256: str) -> RecipeDraft | None:
        try:
            data = read_json_object(
                self.path,
                boundary=self.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            if set(data) != self.FIELDS:
                return None
            steps_data = data.get("steps")
            if not isinstance(steps_data, list) or len(steps_data) > self.MAX_STEPS:
                return None
            steps: list[RecipeStep] = []
            for item in steps_data:
                if not isinstance(item, dict) or set(item) != self.STEP_FIELDS:
                    return None
                parameters = item.get("parameters")
                if not isinstance(parameters, list) or len(parameters) > self.MAX_PARAMETERS:
                    return None
                parsed_parameters: list[tuple[str, str]] = []
                for parameter in parameters:
                    if (
                        not isinstance(parameter, list)
                        or len(parameter) != 2
                        or not all(isinstance(value, str) for value in parameter)
                    ):
                        return None
                    parsed_parameters.append((parameter[0], parameter[1]))
                steps.append(
                    RecipeStep(
                        item.get("step_id"),
                        item.get("operation"),
                        item.get("target"),
                        tuple(parsed_parameters),
                    )
                )
            draft = RecipeDraft(
                data.get("schema_version"),
                data.get("project_id"),
                data.get("source_original_sha256"),
                data.get("updated_at"),
                data.get("stage"),
                data.get("name"),
                data.get("description"),
                data.get("operation"),
                data.get("target"),
                data.get("source_input"),
                data.get("property_key"),
                data.get("property_value"),
                data.get("remove_acknowledged"),
                data.get("replace_existing"),
                tuple(steps),
                data.get("record_digest"),
            )
            if (
                draft.project_id != project_id
                or draft.source_original_sha256 != source_original_sha256
                or not self._valid(draft, require_digest=True)
            ):
                return None
            unsigned = self._payload(draft, include_digest=False)
            if draft.record_digest != _payload_digest(unsigned):
                return None
            return draft
        except (LocalStoreError, ProjectError, TypeError, ValueError):
            return None

    def delete(self) -> None:
        try:
            if self.path.is_file() and not self.path.is_symlink():
                self.path.unlink()
        except OSError:
            return

    @classmethod
    def _payload(cls, draft: RecipeDraft, *, include_digest: bool) -> dict[str, object]:
        payload: dict[str, object] = {
            "format": cls.FORMAT,
            "schema_version": draft.schema_version,
            "project_id": draft.project_id,
            "source_original_sha256": draft.source_original_sha256,
            "updated_at": draft.updated_at,
            "stage": draft.stage,
            "name": draft.name,
            "description": draft.description,
            "operation": draft.operation,
            "target": draft.target,
            "source_input": draft.source_input,
            "property_key": draft.property_key,
            "property_value": draft.property_value,
            "remove_acknowledged": draft.remove_acknowledged,
            "replace_existing": draft.replace_existing,
            "steps": [
                {
                    "step_id": step.step_id,
                    "operation": step.operation,
                    "target": step.target,
                    "parameters": [[key, value] for key, value in step.parameters],
                }
                for step in draft.steps
            ],
        }
        if include_digest:
            payload["record_digest"] = draft.record_digest
        return payload

    @classmethod
    def _valid(cls, draft: RecipeDraft, *, require_digest: bool) -> bool:
        operations = RecipeStore.SUPPORTED_OPERATIONS
        try:
            parsed_time = datetime.fromisoformat(draft.updated_at)
        except (TypeError, ValueError):
            return False
        return (
            type(draft.schema_version) is int
            and draft.schema_version == cls.SCHEMA_VERSION
            and isinstance(draft.project_id, str)
            and bool(re.fullmatch(r"[a-z0-9-]{1,64}", draft.project_id))
            and isinstance(draft.source_original_sha256, str)
            and bool(re.fullmatch(r"[0-9a-f]{64}", draft.source_original_sha256))
            and isinstance(draft.updated_at, str)
            and parsed_time.tzinfo is not None
            and type(draft.stage) is int
            and 0 <= draft.stage <= 5
            and _bounded_text(draft.name, 80)
            and _bounded_text(draft.description, 240)
            and isinstance(draft.operation, str)
            and (not draft.operation or draft.operation in operations)
            and _valid_recipe_target(draft.target, allow_blank=True)
            and _bounded_text(draft.source_input, cls.MAX_PATH_CHARS)
            and _bounded_text(draft.property_key, 256)
            and _bounded_text(draft.property_value, cls.MAX_VALUE_CHARS)
            and type(draft.remove_acknowledged) is bool
            and type(draft.replace_existing) is bool
            and isinstance(draft.steps, tuple)
            and len(draft.steps) <= cls.MAX_STEPS
            and all(cls._valid_step(step, operations) for step in draft.steps)
            and isinstance(draft.record_digest, str)
            and (
                (not require_digest and not draft.record_digest)
                or (require_digest and bool(re.fullmatch(r"[0-9a-f]{64}", draft.record_digest)))
            )
        )

    @classmethod
    def _valid_step(cls, step: RecipeStep, operations: frozenset[str]) -> bool:
        return (
            isinstance(step, RecipeStep)
            and _bounded_text(step.step_id, 80, allow_blank=False)
            and step.operation in operations
            and _valid_recipe_target(step.target, allow_blank=False)
            and isinstance(step.parameters, tuple)
            and len(step.parameters) <= cls.MAX_PARAMETERS
            and all(
                isinstance(parameter, tuple)
                and len(parameter) == 2
                and _bounded_text(parameter[0], 256, allow_blank=False)
                and _bounded_text(parameter[1], cls.MAX_VALUE_CHARS)
                for parameter in step.parameters
            )
        )


def _bounded_text(value: object, maximum: int, *, allow_blank: bool = True) -> bool:
    return (
        isinstance(value, str)
        and len(value) <= maximum
        and "\0" not in value
        and (allow_blank or bool(value))
    )


def _valid_recipe_target(value: object, *, allow_blank: bool) -> bool:
    if not isinstance(value, str) or len(value) > RecipeDraftStore.MAX_PATH_CHARS:
        return False
    if not value:
        return allow_blank
    target = Path(value)
    return not target.is_absolute() and value == target.as_posix() and ".." not in target.parts


class RecipeStore:
    NAME = "recipe.romverse"
    FORMAT = "romverse.recipe"
    STORAGE_SCHEMA_VERSION = 2
    MAX_BYTES = 512 * 1024
    MAX_STEPS = 64
    MAX_PARAMETERS = 8
    SUPPORTED_OPERATIONS = frozenset({"inspect", "replace_file", "remove_package", "set_property"})
    BASE_FIELDS = {
        "format",
        "schema_version",
        "recipe_id",
        "name",
        "description",
        "steps",
        "execution_locked",
        "recipe_digest",
    }
    CURRENT_FIELDS = BASE_FIELDS | {"persistence_schema_version", "record_digest"}
    STEP_FIELDS = {"step_id", "operation", "target", "parameters"}

    def save(self, project_dir: Path, recipe: RomRecipe) -> Path:
        if recipe.schema_version != 1 or not recipe.recipe_id or not recipe.steps:
            raise ProjectError("Recipe must have a version, identifier, and at least one step")
        step_ids = [step.step_id for step in recipe.steps if isinstance(step, RecipeStep)]
        if len(step_ids) != len(set(step_ids)):
            raise ProjectError("Recipe step IDs must be unique")
        if any(
            isinstance(step, RecipeStep) and step.operation not in self.SUPPORTED_OPERATIONS
            for step in recipe.steps
        ):
            raise ProjectError("Recipe contains an unsupported operation")
        if not self._valid(recipe):
            raise ProjectError("Recipe contains invalid, unsafe, or unbounded fields")
        path = project_dir / self.NAME
        payload = self._payload(recipe)
        payload["persistence_schema_version"] = self.STORAGE_SCHEMA_VERSION
        payload["record_digest"] = _payload_digest(payload)
        try:
            atomic_write_json(
                path,
                payload,
                boundary=project_dir,
                maximum_bytes=self.MAX_BYTES,
            )
        except LocalStoreError as exc:
            raise ProjectError(f"Recipe manifest could not be stored safely: {exc}") from exc
        return path

    def load(self, project_dir: Path) -> RomRecipe | None:
        path = project_dir / self.NAME
        try:
            data = read_json_object(
                path,
                boundary=project_dir,
                maximum_bytes=self.MAX_BYTES,
            )
            persistence_schema = data.get("persistence_schema_version", 1)
            expected_fields = self.CURRENT_FIELDS if persistence_schema == 2 else self.BASE_FIELDS
            if (
                type(persistence_schema) is not int
                or persistence_schema not in {1, 2}
                or set(data) != expected_fields
                or data.get("format") != self.FORMAT
            ):
                return None
            steps = self._parse_steps(data.get("steps"))
            if steps is None:
                return None
            recipe = RomRecipe(
                data.get("schema_version"),
                data.get("recipe_id"),
                data.get("name"),
                data.get("description"),
                steps,
                data.get("execution_locked"),
                persistence_schema,
            )
            if not self._valid(recipe) or data.get("recipe_digest") != recipe.digest():
                return None
            if persistence_schema == 2:
                record_digest = data.get("record_digest")
                unsigned = dict(data)
                unsigned.pop("record_digest", None)
                if (
                    not isinstance(record_digest, str)
                    or not re.fullmatch(r"[0-9a-f]{64}", record_digest)
                    or record_digest != _payload_digest(unsigned)
                ):
                    return None
            return recipe
        except (LocalStoreError, OSError, ValueError, TypeError, KeyError):
            return None

    @classmethod
    def _payload(cls, recipe: RomRecipe) -> dict[str, object]:
        return {
            "format": cls.FORMAT,
            "schema_version": recipe.schema_version,
            "recipe_id": recipe.recipe_id,
            "name": recipe.name,
            "description": recipe.description,
            "steps": [
                {
                    "step_id": step.step_id,
                    "operation": step.operation,
                    "target": step.target,
                    "parameters": [[key, value] for key, value in step.parameters],
                }
                for step in recipe.steps
            ],
            "execution_locked": recipe.execution_locked,
            "recipe_digest": recipe.digest(),
        }

    @classmethod
    def _parse_steps(cls, value: object) -> tuple[RecipeStep, ...] | None:
        if not isinstance(value, list) or not 0 < len(value) <= cls.MAX_STEPS:
            return None
        steps: list[RecipeStep] = []
        for item in value:
            if not isinstance(item, dict) or set(item) != cls.STEP_FIELDS:
                return None
            raw_parameters = item.get("parameters")
            if not isinstance(raw_parameters, list) or len(raw_parameters) > cls.MAX_PARAMETERS:
                return None
            parameters: list[tuple[str, str]] = []
            for parameter in raw_parameters:
                if (
                    not isinstance(parameter, list)
                    or len(parameter) != 2
                    or not all(isinstance(part, str) for part in parameter)
                ):
                    return None
                parameters.append((parameter[0], parameter[1]))
            steps.append(
                RecipeStep(
                    item.get("step_id"),
                    item.get("operation"),
                    item.get("target"),
                    tuple(parameters),
                )
            )
        return tuple(steps)

    @classmethod
    def _valid(cls, recipe: RomRecipe) -> bool:
        step_ids = [step.step_id for step in recipe.steps if isinstance(step, RecipeStep)]
        return (
            isinstance(recipe, RomRecipe)
            and type(recipe.schema_version) is int
            and recipe.schema_version == 1
            and _bounded_text(recipe.recipe_id, 120, allow_blank=False)
            and bool(re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,119}", recipe.recipe_id))
            and _bounded_text(recipe.name, 80, allow_blank=False)
            and _bounded_text(recipe.description, 4096)
            and isinstance(recipe.steps, tuple)
            and 0 < len(recipe.steps) <= cls.MAX_STEPS
            and len(step_ids) == len(recipe.steps)
            and len(step_ids) == len(set(step_ids))
            and all(cls._valid_step(step) for step in recipe.steps)
            and type(recipe.execution_locked) is bool
            and recipe.execution_locked
            and type(recipe.persistence_schema_version) is int
            and recipe.persistence_schema_version in {1, 2}
        )

    @classmethod
    def _valid_step(cls, step: RecipeStep) -> bool:
        return (
            isinstance(step, RecipeStep)
            and _bounded_text(step.step_id, 80, allow_blank=False)
            and isinstance(step.operation, str)
            and step.operation in cls.SUPPORTED_OPERATIONS
            and _valid_recipe_target(step.target, allow_blank=False)
            and isinstance(step.parameters, tuple)
            and len(step.parameters) <= cls.MAX_PARAMETERS
            and all(
                isinstance(parameter, tuple)
                and len(parameter) == 2
                and _bounded_text(parameter[0], 256, allow_blank=False)
                and _bounded_text(parameter[1], RecipeDraftStore.MAX_VALUE_CHARS)
                for parameter in step.parameters
            )
        )


@dataclass(frozen=True, slots=True)
class RecipePreview:
    recipe_id: str
    matched_targets: tuple[str, ...]
    unresolved_targets: tuple[str, ...]
    execution_locked: bool = True


@dataclass(frozen=True, slots=True)
class RecipeStepPreview:
    """A bounded, read-only explanation of one proposed Recipe change."""

    step_id: str
    operation: str
    target: str
    summary: str
    detail: str
    changed: bool


@dataclass(frozen=True, slots=True)
class RecipeApproval:
    recipe_digest: str
    tree_root: str
    issued_at: str
    approval_token: str
    tree_sha256: str = ""


@dataclass(frozen=True, slots=True)
class ExecutionReceipt:
    recipe_digest: str
    target: str
    before_sha256: str
    after_sha256: str
    rollback_available: bool
    success: bool


@dataclass(frozen=True, slots=True)
class RecipeStepReceipt:
    step_id: str
    operation: str
    target: str
    before_sha256: str
    after_sha256: str
    changed: bool


@dataclass(frozen=True, slots=True)
class RecipeSnapshot:
    schema_version: int
    snapshot_id: str
    created_at: str
    recipe_digest: str
    tree_root: str
    tree_before_sha256: str
    targets: tuple[tuple[str, str, str], ...]
    workspace_path: str
    snapshot_digest: str


@dataclass(frozen=True, slots=True)
class RecipeRunReceipt:
    schema_version: int
    run_id: str
    started_at: str
    completed_at: str
    recipe_digest: str
    tree_before_sha256: str
    tree_after_sha256: str
    snapshot_id: str
    snapshot_digest: str
    steps: tuple[RecipeStepReceipt, ...]
    rollback_available: bool
    success: bool
    receipt_digest: str = ""


@dataclass(frozen=True, slots=True)
class RecipeRollbackReceipt:
    snapshot_id: str
    snapshot_digest: str
    restored_targets: tuple[str, ...]
    tree_sha256: str
    success: bool


class RecipeExecutor:
    """Fail-closed local recipe gateway with transactional rollback material."""

    MAX_STEPS = 100
    MAX_PROPERTY_BYTES = 16 * 1024 * 1024
    MAX_SNAPSHOT_BYTES = 256 * 1024
    MAX_SNAPSHOTS = 512
    SNAPSHOT_FORMAT = "romverse.recipe-snapshot"
    SNAPSHOT_FIELDS = {
        "format",
        "schema_version",
        "snapshot_id",
        "created_at",
        "recipe_digest",
        "tree_root",
        "tree_before_sha256",
        "targets",
        "snapshot_digest",
    }

    def execute(self, recipe: RomRecipe, tree_root: Path) -> RecipePreview:
        """Preview every step without applying mutations or requiring approval."""
        return preview_recipe(recipe, tree_root)

    @staticmethod
    def issue_approval(recipe: RomRecipe, tree_root: Path) -> RecipeApproval:
        if len(recipe.steps) > RecipeExecutor.MAX_STEPS:
            raise ProjectError(f"Recipes are limited to {RecipeExecutor.MAX_STEPS} steps")
        root = tree_root.resolve()
        if not root.is_dir():
            raise ProjectError("Recipe approval requires an extracted working tree")
        _reject_tree_links(root)
        for step in recipe.steps:
            _validate_step(step, root, RecipeExecutor.MAX_PROPERTY_BYTES)
        digest = recipe.digest()
        tree_digest = _tree_sha256(root)
        token = _approval_token(recipe, root, tree_digest)
        return RecipeApproval(
            digest,
            str(root),
            datetime.now(UTC).isoformat(),
            token,
            tree_digest,
        )

    def execute_approved(
        self,
        recipe: RomRecipe,
        tree_root: Path,
        snapshot_root: Path,
        approval: RecipeApproval,
        progress: Callable[[int, int], None] | None = None,
    ) -> RecipeRunReceipt:
        root = tree_root.resolve()
        self._verify_approval(recipe, root, approval)
        mutating_targets = tuple(
            dict.fromkeys(step.target for step in recipe.steps if step.operation != "inspect")
        )
        snapshot = (
            self._create_snapshot(recipe, root, snapshot_root, mutating_targets)
            if mutating_targets
            else None
        )
        started_at = datetime.now(UTC).isoformat()
        receipts: list[RecipeStepReceipt] = []
        try:
            for index, step in enumerate(recipe.steps, 1):
                receipts.append(self._apply_step(step, root))
                if progress is not None and index < len(recipe.steps):
                    progress(index, len(recipe.steps))
        except Exception as exc:
            if snapshot is not None:
                try:
                    self._restore(snapshot, root)
                except Exception as rollback_exc:
                    raise ProjectError(
                        f"Recipe failed and automatic rollback also failed: {rollback_exc}"
                    ) from exc
            raise ProjectError(f"Recipe failed and working tree was restored: {exc}") from exc
        after = _tree_sha256(root)
        receipt = RecipeRunReceipt(
            2,
            uuid4().hex,
            started_at,
            datetime.now(UTC).isoformat(),
            recipe.digest(),
            approval.tree_sha256,
            after,
            snapshot.snapshot_id if snapshot is not None else "",
            snapshot.snapshot_digest if snapshot is not None else "",
            tuple(receipts),
            snapshot is not None,
            True,
        )
        receipt = replace(receipt, receipt_digest=_run_receipt_digest(receipt))
        if snapshot is not None:
            _write_run_receipt(
                Path(snapshot.workspace_path) / "execution-receipt.romverse",
                receipt,
                boundary=Path(snapshot.workspace_path).parent,
            )
        if progress is not None:
            terminal = len(recipe.steps) or 1
            progress(terminal, terminal)
        return receipt

    def rollback(
        self,
        tree_root: Path,
        snapshot: RecipeSnapshot,
        approval_digest: str,
    ) -> RecipeRollbackReceipt:
        root = tree_root.resolve()
        if approval_digest != snapshot.snapshot_digest:
            raise ProjectError("Rollback approval does not match the selected recipe snapshot")
        if str(root) != snapshot.tree_root:
            raise ProjectError("Recipe snapshot belongs to a different working tree")
        self._restore(snapshot, root)
        return RecipeRollbackReceipt(
            snapshot.snapshot_id,
            snapshot.snapshot_digest,
            tuple(item[0] for item in snapshot.targets),
            _tree_sha256(root),
            True,
        )

    @staticmethod
    def list_snapshots(snapshot_root: Path) -> tuple[RecipeSnapshot, ...]:
        snapshots: list[RecipeSnapshot] = []
        if not snapshot_root.is_dir() or snapshot_root.is_symlink():
            return ()
        try:
            directories: list[Path] = []
            with os.scandir(snapshot_root) as entries:
                for entry in entries:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                    directories.append(Path(entry.path))
                    if len(directories) > RecipeExecutor.MAX_SNAPSHOTS:
                        return ()
            for directory in directories:
                snapshot = RecipeExecutor.load_snapshot(directory, boundary=snapshot_root)
                if snapshot is not None:
                    snapshots.append(snapshot)
        except OSError:
            return ()
        return tuple(sorted(snapshots, key=lambda item: item.created_at, reverse=True))

    @staticmethod
    def load_snapshot(snapshot_dir: Path, *, boundary: Path | None = None) -> RecipeSnapshot | None:
        path = snapshot_dir / "snapshot.romverse"
        try:
            data = read_json_object(
                path,
                boundary=boundary or snapshot_dir.parent,
                maximum_bytes=RecipeExecutor.MAX_SNAPSHOT_BYTES,
            )
            if set(data) != RecipeExecutor.SNAPSHOT_FIELDS:
                return None
            stored_digest = data.get("snapshot_digest")
            unsigned = dict(data)
            unsigned.pop("snapshot_digest", None)
            if unsigned.pop("format", None) != RecipeExecutor.SNAPSHOT_FORMAT:
                return None
            calculated = _payload_digest(unsigned)
            if calculated != stored_digest:
                return None
            targets = _parse_snapshot_targets(data.get("targets"))
            snapshot = RecipeSnapshot(
                data.get("schema_version"),
                data.get("snapshot_id"),
                data.get("created_at"),
                data.get("recipe_digest"),
                data.get("tree_root"),
                data.get("tree_before_sha256"),
                targets or (),
                str(snapshot_dir.resolve()),
                stored_digest,
            )
            if not _valid_snapshot(snapshot) or snapshot_dir.name != snapshot.snapshot_id:
                return None
            return snapshot
        except (LocalStoreError, OSError, ValueError, TypeError, KeyError):
            return None

    @staticmethod
    def _verify_approval(recipe: RomRecipe, root: Path, approval: RecipeApproval) -> None:
        if approval.recipe_digest != recipe.digest() or approval.tree_root != str(root):
            raise ProjectError("Recipe approval does not match this recipe and working tree")
        current_tree = _tree_sha256(root)
        if not approval.tree_sha256 or approval.tree_sha256 != current_tree:
            raise ProjectError("Working tree changed after recipe approval")
        if approval.approval_token != _approval_token(recipe, root, current_tree):
            raise ProjectError("Recipe inputs changed after approval")

    @staticmethod
    def _create_snapshot(
        recipe: RomRecipe,
        root: Path,
        snapshot_root: Path,
        targets: tuple[str, ...],
    ) -> RecipeSnapshot:
        requested_root = snapshot_root.absolute()
        requested_root.mkdir(parents=True, exist_ok=True)
        if requested_root.is_symlink() or requested_root.resolve() != requested_root:
            raise ProjectError("Recipe snapshot storage cannot traverse symbolic links")
        snapshot_root = requested_root
        if snapshot_root.is_relative_to(root):
            raise ProjectError("Recipe snapshots must remain outside the working tree")
        target_records: list[tuple[str, str, str]] = []
        required = 0
        resolved_targets: list[tuple[str, Path]] = []
        for relative in targets:
            target = _safe_target(root, relative)
            if any(
                target != existing
                and (target.is_relative_to(existing) or existing.is_relative_to(target))
                for _existing_relative, existing in resolved_targets
            ):
                raise ProjectError("Recipe mutation targets cannot overlap parent and child paths")
            kind = "directory" if target.is_dir() else "file"
            required += _path_size(target)
            target_records.append((relative, kind, _path_sha256(target)))
            resolved_targets.append((relative, target))
        if shutil.disk_usage(snapshot_root).free < required + 64 * 1024 * 1024:
            raise ProjectError("Insufficient free space for automatic recipe rollback data")
        snapshot_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:8]
        temporary = snapshot_root / f".{snapshot_id}.part"
        destination = snapshot_root / snapshot_id
        files = temporary / "files"
        try:
            if (
                temporary.exists()
                or temporary.is_symlink()
                or destination.exists()
                or destination.is_symlink()
            ):
                raise ProjectError("Recipe snapshot destination already exists")
            files.mkdir(parents=True)
            for relative, target in resolved_targets:
                backup = files / relative
                backup.parent.mkdir(parents=True, exist_ok=True)
                _copy_path(target, backup)
            payload = {
                "schema_version": 2,
                "snapshot_id": snapshot_id,
                "created_at": datetime.now(UTC).isoformat(),
                "recipe_digest": recipe.digest(),
                "tree_root": str(root),
                "tree_before_sha256": _tree_sha256(root),
                "targets": target_records,
            }
            payload["snapshot_digest"] = _payload_digest(payload)
            atomic_write_json(
                temporary / "snapshot.romverse",
                {"format": RecipeExecutor.SNAPSHOT_FORMAT, **payload},
                boundary=snapshot_root,
                maximum_bytes=RecipeExecutor.MAX_SNAPSHOT_BYTES,
            )
            _make_private_tree(temporary)
            os.replace(temporary, destination)
        except Exception:
            if temporary.exists():
                shutil.rmtree(temporary)
            raise
        return RecipeSnapshot(
            2,
            snapshot_id,
            str(payload["created_at"]),
            recipe.digest(),
            str(root),
            str(payload["tree_before_sha256"]),
            tuple(target_records),
            str(destination),
            str(payload["snapshot_digest"]),
        )

    @staticmethod
    def _apply_step(step: RecipeStep, root: Path) -> RecipeStepReceipt:
        target = _safe_target(root, step.target)
        before = _path_sha256(target)
        if step.operation == "inspect":
            after = before
        elif step.operation == "replace_file":
            source = Path(dict(step.parameters)["source"]).expanduser().resolve()
            temporary = target.with_name(target.name + f".romverse-{uuid4().hex}.part")
            shutil.copy2(source, temporary)
            os.replace(temporary, target)
            after = _path_sha256(target)
            if after != _path_sha256(source):
                raise ProjectError(f"Replacement verification failed for {step.target}")
        elif step.operation == "set_property":
            values = dict(step.parameters)
            key, value = values["key"], values["value"]
            lines = target.read_text(encoding="utf-8").splitlines()
            replacement = f"{key}={value}"
            updated = [replacement if line.startswith(f"{key}=") else line for line in lines]
            if not any(line.startswith(f"{key}=") for line in lines):
                updated.append(replacement)
            temporary = target.with_name(target.name + f".romverse-{uuid4().hex}.part")
            temporary.write_text("\n".join(updated) + "\n", encoding="utf-8")
            os.replace(temporary, target)
            after = _path_sha256(target)
            if replacement not in target.read_text(encoding="utf-8").splitlines():
                raise ProjectError(f"Property verification failed for {step.target}")
        elif step.operation == "remove_package":
            _remove_path(target)
            after = ""
            if target.exists():
                raise ProjectError(f"Removal verification failed for {step.target}")
        else:
            raise ProjectError(f"Unsupported recipe operation: {step.operation}")
        return RecipeStepReceipt(
            step.step_id,
            step.operation,
            step.target,
            before,
            after,
            before != after,
        )

    @staticmethod
    def _restore(snapshot: RecipeSnapshot, root: Path) -> None:
        snapshot_dir = Path(snapshot.workspace_path).resolve()
        loaded = RecipeExecutor.load_snapshot(snapshot_dir, boundary=snapshot_dir.parent)
        if loaded is None or loaded != snapshot:
            raise ProjectError("Recipe snapshot integrity verification failed")
        files_root = snapshot_dir / "files"
        if not files_root.is_dir() or files_root.is_symlink():
            raise ProjectError("Recipe snapshot backup root is damaged")
        _reject_tree_links(files_root)
        for relative, _kind, expected_digest in loaded.targets:
            backup = (files_root / relative).resolve()
            if not backup.is_relative_to(files_root.resolve()):
                raise ProjectError("Recipe snapshot target escapes its backup root")
            if not backup.exists() or _path_sha256(backup) != expected_digest:
                raise ProjectError(f"Recipe snapshot is damaged: {relative}")
        for relative, _kind, expected_digest in loaded.targets:
            backup = snapshot_dir / "files" / relative
            target = (root / relative).resolve(strict=False)
            if not target.is_relative_to(root):
                raise ProjectError("Rollback target escapes the working tree")
            if target.exists():
                _remove_path(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            _copy_path(backup, target)
            if _path_sha256(target) != expected_digest:
                raise ProjectError(f"Rollback verification failed for {relative}")

    def apply_replace_file(
        self,
        recipe: RomRecipe,
        tree_root: Path,
        backup_root: Path,
        approved: bool = False,
        approval_digest: str = "",
    ) -> RecipePreview:
        if not approved:
            raise ProjectError("replace_file requires explicit approval")
        if approval_digest != recipe.digest():
            raise ProjectError("Approval does not match the current recipe digest")
        if len(recipe.steps) != 1 or recipe.steps[0].operation != "replace_file":
            raise ProjectError("Only a single replace_file step can be applied")
        step = recipe.steps[0]
        source_value = dict(step.parameters).get("source")
        if not source_value:
            raise ProjectError("replace_file requires a source parameter")
        target = (tree_root / step.target).resolve()
        source = Path(source_value).expanduser().resolve()
        if not target.is_relative_to(tree_root.resolve()) or not source.is_file():
            raise ProjectError("replace_file paths are invalid")
        if not target.is_file():
            raise ProjectError("replace_file target does not exist")
        before = _sha256(target)
        backup = (backup_root / step.target).resolve()
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup)
        temporary = target.with_suffix(target.suffix + ".romverse-part")
        shutil.copyfile(source, temporary)
        os.replace(temporary, target)
        if _sha256(source) != _sha256(target):
            shutil.copyfile(backup, target)
            raise ProjectError("Replacement verification failed; original target restored")
        return ExecutionReceipt(
            recipe.digest(), step.target, before, _sha256(target), backup.is_file(), True
        )

    def apply_set_property(
        self,
        recipe: RomRecipe,
        tree_root: Path,
        backup_root: Path,
        approved: bool = False,
        approval_digest: str = "",
    ) -> ExecutionReceipt:
        if not approved or approval_digest != recipe.digest():
            raise ProjectError("set_property requires approval for the current recipe digest")
        if len(recipe.steps) != 1 or recipe.steps[0].operation != "set_property":
            raise ProjectError("Only a single set_property step can be applied")
        step = recipe.steps[0]
        values = dict(step.parameters)
        key, value = values.get("key"), values.get("value")
        target = (tree_root / step.target).resolve()
        if (
            not key
            or value is None
            or not target.is_relative_to(tree_root.resolve())
            or not target.is_file()
        ):
            raise ProjectError("set_property requires a valid key, value, and text target")
        before = _sha256(target)
        backup = (backup_root / step.target).resolve()
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup)
        lines = target.read_text(encoding="utf-8").splitlines()
        replacement = f"{key}={value}"
        updated = [replacement if line.startswith(f"{key}=") else line for line in lines]
        if not any(line.startswith(f"{key}=") for line in lines):
            updated.append(replacement)
        temporary = target.with_suffix(target.suffix + ".romverse-part")
        temporary.write_text("\n".join(updated) + "\n", encoding="utf-8")
        os.replace(temporary, target)
        return ExecutionReceipt(
            recipe.digest(), step.target, before, _sha256(target), backup.is_file(), True
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def preview_recipe(recipe: RomRecipe, tree_root: Path) -> RecipePreview:
    matched: list[str] = []
    unresolved: list[str] = []
    for step in recipe.steps:
        target = (tree_root / step.target).resolve()
        if target.is_relative_to(tree_root.resolve()) and target.exists():
            matched.append(step.target)
        else:
            unresolved.append(step.target)
    return RecipePreview(recipe.recipe_id, tuple(matched), tuple(unresolved))


def preview_recipe_changes(
    recipe: RomRecipe,
    tree_root: Path,
    *,
    max_diff_lines: int = 120,
) -> tuple[RecipeStepPreview, ...]:
    """Describe proposed changes without mutating or deeply scanning the tree.

    Text diffs are deliberately bounded. Large binary verification remains part of
    the explicit Guardian approval phase, keeping Recipe Forge responsive.
    """

    root = tree_root.resolve()
    if not root.is_dir():
        raise ProjectError("Recipe preview requires an extracted working tree")
    previews: list[RecipeStepPreview] = []
    for step in recipe.steps:
        _validate_step(step, root, RecipeExecutor.MAX_PROPERTY_BYTES)
        target = _safe_target(root, step.target)
        if step.operation == "inspect":
            kind = "directory" if target.is_dir() else "file"
            size = _path_size_bounded(target)
            previews.append(
                RecipeStepPreview(
                    step.step_id,
                    step.operation,
                    step.target,
                    f"Read-only inspection of one {kind}",
                    f"Current size: {_human_bytes(size)}. No bytes will change.",
                    False,
                )
            )
        elif step.operation == "replace_file":
            source = Path(dict(step.parameters)["source"]).expanduser().resolve()
            before_size = target.stat().st_size
            after_size = source.stat().st_size
            identical = before_size == after_size and _small_files_equal(target, source)
            previews.append(
                RecipeStepPreview(
                    step.step_id,
                    step.operation,
                    step.target,
                    "Replacement file is identical"
                    if identical
                    else "File content will be replaced",
                    f"Before: {_human_bytes(before_size)}  →  After: {_human_bytes(after_size)}\n"
                    f"Source: {source.name}\nFull hashes are verified during Guardian approval.",
                    not identical,
                )
            )
        elif step.operation == "set_property":
            values = dict(step.parameters)
            original = target.read_text(encoding="utf-8")
            lines = original.splitlines()
            replacement = f"{values['key']}={values['value']}"
            updated_lines = [
                replacement if line.startswith(f"{values['key']}=") else line for line in lines
            ]
            if not any(line.startswith(f"{values['key']}=") for line in lines):
                updated_lines.append(replacement)
            updated = "\n".join(updated_lines) + "\n"
            diff = list(
                difflib.unified_diff(
                    original.splitlines(),
                    updated.splitlines(),
                    fromfile=f"before/{step.target}",
                    tofile=f"after/{step.target}",
                    lineterm="",
                )
            )
            clipped = diff[:max_diff_lines]
            if len(diff) > max_diff_lines:
                clipped.append(f"… {len(diff) - max_diff_lines} additional diff lines hidden")
            previews.append(
                RecipeStepPreview(
                    step.step_id,
                    step.operation,
                    step.target,
                    "Property already has the requested value"
                    if original == updated
                    else "Property file will change",
                    "\n".join(clipped) if clipped else "No textual difference.",
                    original != updated,
                )
            )
        elif step.operation == "remove_package":
            kind = "directory tree" if target.is_dir() else "file"
            size = _path_size_bounded(target)
            previews.append(
                RecipeStepPreview(
                    step.step_id,
                    step.operation,
                    step.target,
                    f"One {kind} will be removed from the working copy",
                    f"Rollback coverage required. Approximate content size: {_human_bytes(size)}.",
                    True,
                )
            )
    return tuple(previews)


def _path_size_bounded(path: Path, max_entries: int = 10_000) -> int:
    if path.is_file():
        return path.stat().st_size
    size = 0
    for index, item in enumerate(path.rglob("*")):
        if index >= max_entries:
            break
        if item.is_file() and not item.is_symlink():
            size += item.stat().st_size
    return size


def _small_files_equal(left: Path, right: Path, limit: int = 16 * 1024 * 1024) -> bool:
    if left.stat().st_size > limit or right.stat().st_size > limit:
        return False
    return left.read_bytes() == right.read_bytes()


def _human_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"


def _validate_step(step: RecipeStep, root: Path, max_property_bytes: int) -> None:
    target = _safe_target(root, step.target)
    values = dict(step.parameters)
    if len(values) != len(step.parameters):
        raise ProjectError(f"Recipe step {step.step_id} contains duplicate parameters")
    if step.operation == "replace_file":
        source_value = values.get("source", "")
        source = Path(source_value).expanduser().resolve() if source_value else Path()
        if set(values) != {"source"} or not source.is_file():
            raise ProjectError("replace_file requires one valid source file")
        if not target.is_file():
            raise ProjectError("replace_file target must be an existing regular file")
    elif step.operation == "set_property":
        key, value = values.get("key"), values.get("value")
        if set(values) != {"key", "value"} or not key or value is None:
            raise ProjectError("set_property requires key and value parameters")
        if not all(character.isalnum() or character in "._-" for character in key):
            raise ProjectError(
                "Property keys may contain only letters, numbers, dot, dash, underscore"
            )
        if any(character in value for character in "\r\n\0"):
            raise ProjectError("Property values cannot contain line breaks or null bytes")
        if not target.is_file() or target.stat().st_size > max_property_bytes:
            raise ProjectError("set_property target must be a text file no larger than 16 MiB")
        try:
            target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ProjectError("set_property target must be valid UTF-8 text") from exc
    elif step.operation == "remove_package":
        if values:
            raise ProjectError("remove_package does not accept parameters")
    elif step.operation == "inspect":
        if values:
            raise ProjectError("inspect does not accept parameters")
    else:
        raise ProjectError(f"Unsupported recipe operation: {step.operation}")


def _safe_target(root: Path, relative: str) -> Path:
    value = Path(relative)
    if not relative or value.is_absolute() or ".." in value.parts or "\\" in relative:
        raise ProjectError("Recipe target must be a contained relative path")
    current = root
    for part in value.parts:
        current = current / part
        if current.is_symlink():
            raise ProjectError("Recipe targets cannot traverse symbolic links")
    target = (root / value).resolve(strict=False)
    if not target.is_relative_to(root) or not target.exists():
        raise ProjectError(f"Recipe target is unresolved: {relative}")
    return target


def _reject_tree_links(root: Path) -> None:
    if any(path.is_symlink() for path in root.rglob("*")):
        raise ProjectError("Recipe execution is blocked while the working tree contains links")


def _approval_token(recipe: RomRecipe, root: Path, tree_digest: str) -> str:
    materials = hashlib.sha256()
    for step in recipe.steps:
        if step.operation == "replace_file":
            source = Path(dict(step.parameters)["source"]).expanduser().resolve()
            materials.update(step.step_id.encode("utf-8"))
            materials.update(_path_sha256(source).encode("ascii"))
    payload = f"{recipe.digest()}:{root}:{tree_digest}:{materials.hexdigest()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _tree_sha256(root: Path) -> str:
    _reject_tree_links(root)
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"D" if path.is_dir() else b"F")
        if path.is_file():
            digest.update(bytes.fromhex(_sha256(path)))
    return digest.hexdigest()


def _path_sha256(path: Path) -> str:
    if path.is_file():
        return _sha256(path)
    if path.is_dir():
        return _tree_sha256(path)
    raise ProjectError(f"Cannot hash missing recipe path: {path.name}")


def _path_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _copy_path(source: Path, destination: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        shutil.copy2(source, destination)


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def _payload_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


_RUN_RECEIPT_FORMAT = "romverse.recipe-receipt"
_RUN_RECEIPT_MAX_BYTES = 256 * 1024
_RUN_RECEIPT_BASE_FIELDS = {
    "format",
    "schema_version",
    "run_id",
    "started_at",
    "completed_at",
    "recipe_digest",
    "tree_before_sha256",
    "tree_after_sha256",
    "snapshot_id",
    "snapshot_digest",
    "steps",
    "rollback_available",
    "success",
}
_RUN_RECEIPT_CURRENT_FIELDS = _RUN_RECEIPT_BASE_FIELDS | {"receipt_digest"}
_RUN_STEP_FIELDS = {
    "step_id",
    "operation",
    "target",
    "before_sha256",
    "after_sha256",
    "changed",
}


def save_run_receipt(
    project_dir: Path,
    receipt: RecipeRunReceipt,
    *,
    recipe: RomRecipe,
    tree_root: Path,
    snapshot_root: Path,
) -> Path:
    """Persist only a fully re-derived current Recipe execution receipt."""

    if receipt.schema_version != 2 or receipt.receipt_digest != _run_receipt_digest(receipt):
        raise ProjectError("Recipe run receipt is not current verified evidence")
    if _tree_sha256(tree_root.resolve()) != receipt.tree_after_sha256:
        raise ProjectError("Working tree changed before the Recipe receipt could be stored")
    if not _valid_run_receipt_binding(
        receipt,
        recipe=recipe,
        tree_root=tree_root,
        snapshot_root=snapshot_root,
    ):
        raise ProjectError("Recipe run receipt does not match its Recipe and rollback evidence")
    path = project_dir / "latest-recipe-receipt.romverse"
    _write_run_receipt(path, receipt, boundary=project_dir)
    if (
        load_run_receipt(
            project_dir,
            recipe=recipe,
            tree_root=tree_root,
            snapshot_root=snapshot_root,
        )
        is None
    ):
        raise ProjectError("Stored Recipe run receipt failed reread verification")
    return path


def load_run_receipt(
    project_dir: Path,
    *,
    recipe: RomRecipe | None = None,
    tree_root: Path | None = None,
    snapshot_root: Path | None = None,
) -> RecipeRunReceipt | None:
    """Load bounded no-link evidence and optionally re-derive every external binding."""

    try:
        data = read_json_object(
            project_dir / "latest-recipe-receipt.romverse",
            boundary=project_dir,
            maximum_bytes=_RUN_RECEIPT_MAX_BYTES,
        )
        receipt = _parse_run_receipt(data)
        if receipt is None:
            return None
        if recipe is not None and not _valid_run_receipt_binding(
            receipt,
            recipe=recipe,
            tree_root=tree_root,
            snapshot_root=snapshot_root,
        ):
            return None
        return receipt
    except (LocalStoreError, OSError, TypeError, ValueError):
        return None


def save_rollback_receipt(project_dir: Path, receipt: RecipeRollbackReceipt) -> Path:
    path = project_dir / "latest-recipe-rollback.romverse"
    if (
        not re.fullmatch(r"\d{8}T\d{6}-[0-9a-f]{8}", receipt.snapshot_id)
        or not _valid_sha256(receipt.snapshot_digest)
        or not receipt.restored_targets
        or len(receipt.restored_targets) > RecipeStore.MAX_STEPS
        or len(set(receipt.restored_targets)) != len(receipt.restored_targets)
        or not all(
            _valid_recipe_target(item, allow_blank=False) for item in receipt.restored_targets
        )
        or not _valid_sha256(receipt.tree_sha256)
        or receipt.success is not True
    ):
        raise ProjectError("Recipe rollback receipt is invalid")
    payload: dict[str, object] = {"format": "romverse.recipe-rollback", **asdict(receipt)}
    payload["receipt_digest"] = _payload_digest(payload)
    try:
        atomic_write_json(
            path,
            payload,
            boundary=project_dir,
            maximum_bytes=_RUN_RECEIPT_MAX_BYTES,
        )
    except LocalStoreError as exc:
        raise ProjectError(f"Recipe rollback receipt could not be stored safely: {exc}") from exc
    return path


def _run_receipt_payload(receipt: RecipeRunReceipt, *, include_digest: bool) -> dict[str, object]:
    payload: dict[str, object] = {
        "format": _RUN_RECEIPT_FORMAT,
        "schema_version": receipt.schema_version,
        "run_id": receipt.run_id,
        "started_at": receipt.started_at,
        "completed_at": receipt.completed_at,
        "recipe_digest": receipt.recipe_digest,
        "tree_before_sha256": receipt.tree_before_sha256,
        "tree_after_sha256": receipt.tree_after_sha256,
        "snapshot_id": receipt.snapshot_id,
        "snapshot_digest": receipt.snapshot_digest,
        "steps": [asdict(step) for step in receipt.steps],
        "rollback_available": receipt.rollback_available,
        "success": receipt.success,
    }
    if include_digest:
        payload["receipt_digest"] = receipt.receipt_digest
    return payload


def _run_receipt_digest(receipt: RecipeRunReceipt) -> str:
    return _payload_digest(_run_receipt_payload(receipt, include_digest=False))


def _write_run_receipt(path: Path, receipt: RecipeRunReceipt, *, boundary: Path) -> None:
    if not _valid_run_receipt(receipt) or receipt.receipt_digest != _run_receipt_digest(receipt):
        raise ProjectError("Recipe run receipt failed its strict evidence contract")
    try:
        atomic_write_json(
            path,
            _run_receipt_payload(receipt, include_digest=True),
            boundary=boundary,
            maximum_bytes=_RUN_RECEIPT_MAX_BYTES,
        )
    except LocalStoreError as exc:
        raise ProjectError(f"Recipe run receipt could not be stored safely: {exc}") from exc


def _parse_run_receipt(data: dict[str, object]) -> RecipeRunReceipt | None:
    schema_version = data.get("schema_version")
    expected_fields = (
        _RUN_RECEIPT_CURRENT_FIELDS if schema_version == 2 else _RUN_RECEIPT_BASE_FIELDS
    )
    if (
        type(schema_version) is not int
        or schema_version not in {1, 2}
        or set(data) != expected_fields
        or data.get("format") != _RUN_RECEIPT_FORMAT
    ):
        return None
    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list) or not 0 < len(raw_steps) <= RecipeStore.MAX_STEPS:
        return None
    steps: list[RecipeStepReceipt] = []
    for item in raw_steps:
        if not isinstance(item, dict) or set(item) != _RUN_STEP_FIELDS:
            return None
        steps.append(
            RecipeStepReceipt(
                item.get("step_id"),
                item.get("operation"),
                item.get("target"),
                item.get("before_sha256"),
                item.get("after_sha256"),
                item.get("changed"),
            )
        )
    receipt = RecipeRunReceipt(
        schema_version,
        data.get("run_id"),
        data.get("started_at"),
        data.get("completed_at"),
        data.get("recipe_digest"),
        data.get("tree_before_sha256"),
        data.get("tree_after_sha256"),
        data.get("snapshot_id"),
        data.get("snapshot_digest"),
        tuple(steps),
        data.get("rollback_available"),
        data.get("success"),
        data.get("receipt_digest", ""),
    )
    if not _valid_run_receipt(receipt):
        return None
    if receipt.schema_version == 2 and receipt.receipt_digest != _run_receipt_digest(receipt):
        return None
    return receipt


def _valid_run_receipt(receipt: RecipeRunReceipt) -> bool:
    try:
        started = datetime.fromisoformat(receipt.started_at.replace("Z", "+00:00"))
        completed = datetime.fromisoformat(receipt.completed_at.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        return False
    snapshot_present = bool(receipt.snapshot_id and receipt.snapshot_digest)
    return (
        type(receipt.schema_version) is int
        and receipt.schema_version in {1, 2}
        and isinstance(receipt.run_id, str)
        and re.fullmatch(r"[0-9a-f]{32}", receipt.run_id) is not None
        and started.tzinfo is not None
        and completed.tzinfo is not None
        and completed >= started
        and _valid_sha256(receipt.recipe_digest)
        and _valid_sha256(receipt.tree_before_sha256)
        and _valid_sha256(receipt.tree_after_sha256)
        and isinstance(receipt.snapshot_id, str)
        and (
            not receipt.snapshot_id
            or re.fullmatch(r"\d{8}T\d{6}-[0-9a-f]{8}", receipt.snapshot_id) is not None
        )
        and isinstance(receipt.snapshot_digest, str)
        and (not receipt.snapshot_digest or _valid_sha256(receipt.snapshot_digest))
        and isinstance(receipt.steps, tuple)
        and 0 < len(receipt.steps) <= RecipeStore.MAX_STEPS
        and all(_valid_step_receipt(step) for step in receipt.steps)
        and type(receipt.rollback_available) is bool
        and receipt.rollback_available is snapshot_present
        and receipt.success is True
        and isinstance(receipt.receipt_digest, str)
        and (
            (receipt.schema_version == 1 and not receipt.receipt_digest)
            or (receipt.schema_version == 2 and _valid_sha256(receipt.receipt_digest))
        )
    )


def _valid_step_receipt(step: RecipeStepReceipt) -> bool:
    if (
        not _bounded_text(step.step_id, 80, allow_blank=False)
        or step.operation not in RecipeStore.SUPPORTED_OPERATIONS
        or not _valid_recipe_target(step.target, allow_blank=False)
        or not _valid_sha256(step.before_sha256)
        or type(step.changed) is not bool
    ):
        return False
    if step.operation == "remove_package":
        return step.after_sha256 == "" and step.changed
    if not _valid_sha256(step.after_sha256):
        return False
    if step.operation == "inspect":
        return step.after_sha256 == step.before_sha256 and not step.changed
    return step.changed is (step.before_sha256 != step.after_sha256)


def _valid_run_receipt_binding(
    receipt: RecipeRunReceipt,
    *,
    recipe: RomRecipe,
    tree_root: Path | None,
    snapshot_root: Path | None,
) -> bool:
    if receipt.recipe_digest != recipe.digest() or len(receipt.steps) != len(recipe.steps):
        return False
    if any(
        (actual.step_id, actual.operation, actual.target)
        != (expected.step_id, expected.operation, expected.target)
        for actual, expected in zip(receipt.steps, recipe.steps, strict=True)
    ):
        return False
    mutating_targets = tuple(
        dict.fromkeys(step.target for step in recipe.steps if step.operation != "inspect")
    )
    if not mutating_targets:
        return not receipt.rollback_available
    if not receipt.rollback_available or snapshot_root is None:
        return False
    snapshot = RecipeExecutor.load_snapshot(
        snapshot_root / receipt.snapshot_id,
        boundary=snapshot_root,
    )
    if (
        snapshot is None
        or snapshot.snapshot_digest != receipt.snapshot_digest
        or snapshot.recipe_digest != receipt.recipe_digest
        or snapshot.tree_before_sha256 != receipt.tree_before_sha256
        or tuple(item[0] for item in snapshot.targets) != mutating_targets
        or (tree_root is not None and snapshot.tree_root != str(tree_root.resolve()))
    ):
        return False
    first_before_by_target: dict[str, str] = {}
    for step in receipt.steps:
        if step.operation != "inspect":
            first_before_by_target.setdefault(step.target, step.before_sha256)
    return all(
        first_before_by_target[target] == digest for target, _kind, digest in snapshot.targets
    )


def _parse_snapshot_targets(value: object) -> tuple[tuple[str, str, str], ...] | None:
    if not isinstance(value, list) or not 0 < len(value) <= RecipeStore.MAX_STEPS:
        return None
    targets: list[tuple[str, str, str]] = []
    for item in value:
        if (
            not isinstance(item, list)
            or len(item) != 3
            or not all(isinstance(part, str) for part in item)
        ):
            return None
        targets.append((item[0], item[1], item[2]))
    return tuple(targets)


def _valid_snapshot(snapshot: RecipeSnapshot) -> bool:
    try:
        created = datetime.fromisoformat(snapshot.created_at.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        return False
    target_paths = [item[0] for item in snapshot.targets]
    normalized_tree = Path(snapshot.tree_root) if isinstance(snapshot.tree_root, str) else Path()
    return (
        type(snapshot.schema_version) is int
        and snapshot.schema_version in {1, 2}
        and isinstance(snapshot.snapshot_id, str)
        and re.fullmatch(r"\d{8}T\d{6}-[0-9a-f]{8}", snapshot.snapshot_id) is not None
        and created.tzinfo is not None
        and _valid_sha256(snapshot.recipe_digest)
        and isinstance(snapshot.tree_root, str)
        and len(snapshot.tree_root) <= RecipeDraftStore.MAX_PATH_CHARS
        and "\0" not in snapshot.tree_root
        and normalized_tree.is_absolute()
        and str(normalized_tree) == snapshot.tree_root
        and _valid_sha256(snapshot.tree_before_sha256)
        and isinstance(snapshot.targets, tuple)
        and 0 < len(snapshot.targets) <= RecipeStore.MAX_STEPS
        and len(target_paths) == len(set(target_paths))
        and all(
            _valid_recipe_target(target, allow_blank=False)
            and kind in {"file", "directory"}
            and _valid_sha256(digest)
            for target, kind, digest in snapshot.targets
        )
        and not any(
            left != right
            and (Path(left).is_relative_to(Path(right)) or Path(right).is_relative_to(Path(left)))
            for index, left in enumerate(target_paths)
            for right in target_paths[index + 1 :]
        )
        and isinstance(snapshot.workspace_path, str)
        and Path(snapshot.workspace_path).is_absolute()
        and _valid_sha256(snapshot.snapshot_digest)
    )


def _valid_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _make_private_tree(root: Path) -> None:
    if root.is_symlink():
        raise ProjectError("Recipe snapshot storage cannot contain symbolic links")
    root.chmod(0o700)
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ProjectError("Recipe snapshot storage cannot contain symbolic links")
        path.chmod(0o700 if path.is_dir() else 0o600)
