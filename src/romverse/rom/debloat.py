from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from romverse.rom.filesystems import PartitionFilesystemService
from romverse.rom.models import ProjectError
from romverse.rom.payloads import PayloadService
from romverse.rom.projects import RomProjectStore
from romverse.rom.recipes import (
    RecipeExecutor,
    RecipeRollbackReceipt,
    RecipeStep,
    RomRecipe,
)

ProgressCallback = Callable[[int], None]


class DebloatRisk(StrEnum):
    SAFE = "safe"
    CAUTION = "caution"
    PROTECTED = "protected"


@dataclass(frozen=True, slots=True)
class SystemAppCandidate:
    candidate_id: str
    display_name: str
    package_hint: str
    relative_path: str
    partition: str
    privileged: bool
    apk_count: int
    size_bytes: int
    risk: DebloatRisk
    reason: str


@dataclass(frozen=True, slots=True)
class DebloatScan:
    schema_version: int
    scan_id: str
    project_id: str
    created_at: str
    candidates: tuple[SystemAppCandidate, ...]
    content_digest: str
    scan_digest: str

    @property
    def safe_count(self) -> int:
        return sum(item.risk is DebloatRisk.SAFE for item in self.candidates)

    @property
    def caution_count(self) -> int:
        return sum(item.risk is DebloatRisk.CAUTION for item in self.candidates)

    @property
    def protected_count(self) -> int:
        return sum(item.risk is DebloatRisk.PROTECTED for item in self.candidates)


@dataclass(frozen=True, slots=True)
class DebloatDiscoveryReport:
    schema_version: int
    project_id: str
    created_at: str
    apk_files_examined: int
    recognized_apk_files: int
    candidate_groups: int
    excluded_apk_files: int
    partitions: tuple[str, ...]
    materialization_attempted: bool
    example_paths: tuple[str, ...]
    phone_changed: bool
    report_digest: str


@dataclass(frozen=True, slots=True)
class DebloatPlan:
    schema_version: int
    plan_id: str
    project_id: str
    created_at: str
    scan_id: str
    scan_content_digest: str
    selected_ids: tuple[str, ...]
    selected_paths: tuple[str, ...]
    caution_ids: tuple[str, ...]
    keep_all: bool
    plan_digest: str


@dataclass(frozen=True, slots=True)
class DebloatReceipt:
    schema_version: int
    receipt_id: str
    project_id: str
    created_at: str
    plan_id: str
    plan_digest: str
    scan_content_digest: str
    removed_paths: tuple[str, ...]
    removed_app_count: int
    reclaimed_bytes: int
    keep_all: bool
    snapshot_id: str
    snapshot_digest: str
    quarantine_path: str
    rollback_available: bool
    protected_original_unchanged: bool
    phone_changed: bool
    success: bool
    receipt_digest: str


class DebloatService:
    """Scan and transactionally remove reviewed apps from an isolated working tree."""

    FORMAT_SCAN = "romverse.debloat-scan"
    FORMAT_PLAN = "romverse.debloat-plan"
    FORMAT_RECEIPT = "romverse.debloat-receipt"
    FORMAT_DISCOVERY = "romverse.debloat-discovery"
    SCHEMA_VERSION = 1
    SCAN_NAME = "latest-scan.romverse"
    PLAN_NAME = "latest-plan.romverse"
    RECEIPT_NAME = "latest-receipt.romverse"
    DISCOVERY_NAME = "latest-discovery.romverse"
    MAX_CANDIDATES = 5_000
    PARTITIONS = frozenset(
        {"system", "system_ext", "product", "vendor", "odm", "oem", "mi_ext", "my_product"}
    )
    APP_DIRECTORIES = frozenset({"app", "priv-app"})
    PROTECTED_TOKENS = (
        "systemui",
        "settings",
        "permissioncontroller",
        "packageinstaller",
        "setupwizard",
        "telephonyprovider",
        "contactsprovider",
        "mediaprovider",
        "downloadprovider",
        "documentsui",
        "networkstack",
        "cellbroadcast",
        "bluetooth",
        "keychain",
        "credential",
        "webview",
        "launcher",
        "inputmethod",
        "comandroidphone",
        "imsservice",
        "securitycenter",
        "guardprovider",
        "gmscore",
        "googleframework",
        "vending",
    )
    SAFE_TOKENS = (
        "facebook",
        "netflix",
        "linkedin",
        "booking",
        "amazonshopping",
        "primevideo",
        "tiktok",
        "miuihybrid",
        "hybridaccessory",
        "quickapps",
        "miuiads",
        "analyticscore",
        "partnerbookmark",
        "partnerstub",
    )

    def __init__(
        self,
        store: RomProjectStore,
        payloads: PayloadService | None = None,
        filesystems: PartitionFilesystemService | None = None,
    ) -> None:
        self.store = store
        self.payloads = payloads
        self.filesystems = filesystems

    def scan(
        self,
        project_id: str,
        progress: ProgressCallback | None = None,
        *,
        persist: bool = True,
    ) -> DebloatScan:
        project = self.store.get(project_id)
        if project.original is None:
            raise ProjectError("Debloat scanning requires a protected firmware source")
        tree = self._tree(project_id)
        apk_paths = self._apk_paths(tree)
        groups, targets = self._group_apps(tree, apk_paths)
        materialization_attempted = False
        if not groups:
            materialization_attempted = True
            try:
                self._prepare_partition_trees(project_id)
            except ProjectError as exc:
                apk_paths = self._apk_paths(tree)
                groups, targets = self._group_apps(tree, apk_paths)
                discovery = self._discovery(
                    project_id,
                    tree,
                    apk_paths,
                    groups,
                    targets,
                    materialization_attempted=True,
                )
                if persist:
                    self._save_discovery(discovery)
                raise ProjectError(f"{exc}. {self._discovery_summary(discovery)}") from exc
            apk_paths = self._apk_paths(tree)
            groups, targets = self._group_apps(tree, apk_paths)
        discovery = self._discovery(
            project_id,
            tree,
            apk_paths,
            groups,
            targets,
            materialization_attempted=materialization_attempted,
        )
        if persist:
            self._save_discovery(discovery)
        if not groups:
            raise ProjectError(
                "Nebula Debloat found no reviewable Android packages. The stage was not "
                "completed; no apps were found inside a recognized system, product, vendor, "
                "odm, oem, or device partition. Extract the ROM's Android filesystems and rescan. "
                + self._discovery_summary(discovery)
            )

        ordered_groups = tuple(sorted(groups, key=str.casefold))
        candidates = []
        if progress is not None:
            progress(0)
        for index, relative in enumerate(ordered_groups, 1):
            target, partition, privileged = targets[relative]
            apks = tuple(sorted(groups[relative]))
            name = target.stem if target.is_file() else target.name
            risk, reason = self._classify(name, relative, privileged)
            size = (
                sum(path.stat().st_size for path in target.rglob("*") if path.is_file())
                if target.is_dir()
                else target.stat().st_size
            )
            identifier = hashlib.sha256(relative.encode()).hexdigest()[:24]
            candidates.append(
                SystemAppCandidate(
                    identifier,
                    name,
                    _package_hint(apks),
                    relative,
                    partition,
                    privileged,
                    len(apks),
                    size,
                    risk,
                    reason,
                )
            )
            if progress is not None:
                progress(min(99, round(index * 99 / max(1, len(ordered_groups)))))
        content_digest = _digest([_candidate_payload(item) for item in candidates])
        payload: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "scan_id": uuid4().hex,
            "project_id": project_id,
            "created_at": datetime.now(UTC).isoformat(),
            "candidates": [_candidate_payload(item) for item in candidates],
            "content_digest": content_digest,
        }
        scan = DebloatScan(
            self.SCHEMA_VERSION,
            str(payload["scan_id"]),
            project_id,
            str(payload["created_at"]),
            tuple(candidates),
            content_digest,
            _digest(payload),
        )
        if persist:
            root = self._root(project_id)
            root.mkdir(parents=True, exist_ok=True)
            _atomic_json(root / self.SCAN_NAME, {"format": self.FORMAT_SCAN, **asdict(scan)})
        if progress is not None:
            progress(100)
        return scan

    def create_plan(
        self,
        scan: DebloatScan,
        selected_ids: tuple[str, ...],
        *,
        acknowledge_caution: bool = False,
    ) -> DebloatPlan:
        current = self.load_scan(scan.project_id)
        if current is None or current.scan_digest != scan.scan_digest:
            raise ProjectError("Debloat scan changed; scan the working tree again")
        if not scan.candidates:
            raise ProjectError("Nebula Debloat cannot complete from an empty app inventory")
        if len(selected_ids) != len(set(selected_ids)):
            raise ProjectError("Debloat selection contains duplicate apps")
        by_id = {item.candidate_id: item for item in scan.candidates}
        try:
            selected = tuple(by_id[item] for item in selected_ids)
        except KeyError as exc:
            raise ProjectError("Debloat selection does not match the current scan") from exc
        if any(item.risk is DebloatRisk.PROTECTED for item in selected):
            raise ProjectError("Guardian will not remove a red protected system component")
        if len(selected) > RecipeExecutor.MAX_STEPS:
            raise ProjectError(
                f"Select no more than {RecipeExecutor.MAX_STEPS} apps in one Debloat pass"
            )
        caution = tuple(item.candidate_id for item in selected if item.risk is DebloatRisk.CAUTION)
        if caution and not acknowledge_caution:
            raise ProjectError("Orange caution apps require explicit confirmation")
        payload: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "plan_id": uuid4().hex,
            "project_id": scan.project_id,
            "created_at": datetime.now(UTC).isoformat(),
            "scan_id": scan.scan_id,
            "scan_content_digest": scan.content_digest,
            "selected_ids": tuple(item.candidate_id for item in selected),
            "selected_paths": tuple(item.relative_path for item in selected),
            "caution_ids": caution,
            "keep_all": not selected,
        }
        plan = DebloatPlan(**payload, plan_digest=_digest(payload))
        root = self._root(scan.project_id)
        root.mkdir(parents=True, exist_ok=True)
        _atomic_json(root / self.PLAN_NAME, {"format": self.FORMAT_PLAN, **asdict(plan)})
        return plan

    def apply(
        self,
        plan: DebloatPlan,
        progress: ProgressCallback | None = None,
    ) -> DebloatReceipt:
        loaded = self.load_plan(plan.project_id)
        if loaded is None or loaded.plan_digest != plan.plan_digest:
            raise ProjectError("Debloat plan failed integrity verification")
        current = self.scan(
            plan.project_id,
            None,
            persist=False,
        )
        if current.content_digest != plan.scan_content_digest:
            raise ProjectError("System apps changed after selection; scan and review them again")
        by_id = {item.candidate_id: item for item in current.candidates}
        try:
            selected = tuple(by_id[item] for item in plan.selected_ids)
        except KeyError as exc:
            raise ProjectError("A selected system app is no longer present") from exc
        if tuple(item.relative_path for item in selected) != plan.selected_paths:
            raise ProjectError("Debloat target paths changed after selection")
        if any(item.risk is DebloatRisk.PROTECTED for item in selected):
            raise ProjectError("A selected app is now protected; operation stopped")

        snapshot_id = snapshot_digest = quarantine_path = ""
        original_before = self.store.verify_original(plan.project_id)
        if not original_before.valid:
            raise ProjectError(
                "Protected firmware integrity failed before Debloat; operation stopped"
            )
        if selected:
            recipe = RomRecipe(
                1,
                f"genesis-debloat-{plan.plan_id}",
                "Genesis Debloat",
                "ROMVERSE-classified, user-reviewed, reversible working-tree app removal",
                tuple(
                    RecipeStep(
                        f"debloat-{index:04d}",
                        "remove_package",
                        item.relative_path,
                    )
                    for index, item in enumerate(selected, 1)
                ),
            )
            tree = self._tree(plan.project_id)
            executor = RecipeExecutor()
            approval = executor.issue_approval(recipe, tree)
            run = executor.execute_approved(
                recipe,
                tree,
                self.store.snapshots_root / plan.project_id / "debloat",
                approval,
            )
            snapshot_id = run.snapshot_id
            snapshot_digest = run.snapshot_digest
            snapshots = RecipeExecutor.list_snapshots(
                self.store.snapshots_root / plan.project_id / "debloat"
            )
            snapshot = next((item for item in snapshots if item.snapshot_id == snapshot_id), None)
            if snapshot is None:
                raise ProjectError("Debloat completed but rollback snapshot verification failed")
            quarantine_path = snapshot.workspace_path
        original_after = self.store.verify_original(plan.project_id)
        if (
            not original_after.valid
            or original_after.actual_sha256 != original_before.actual_sha256
        ):
            if snapshot_id and quarantine_path:
                snapshot = RecipeExecutor.load_snapshot(Path(quarantine_path))
                if snapshot is not None:
                    RecipeExecutor().rollback(
                        self._tree(plan.project_id), snapshot, snapshot.snapshot_digest
                    )
            raise ProjectError("Protected firmware integrity changed; Debloat was rolled back")

        payload: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "receipt_id": uuid4().hex,
            "project_id": plan.project_id,
            "created_at": datetime.now(UTC).isoformat(),
            "plan_id": plan.plan_id,
            "plan_digest": plan.plan_digest,
            "scan_content_digest": plan.scan_content_digest,
            "removed_paths": plan.selected_paths,
            "removed_app_count": len(selected),
            "reclaimed_bytes": sum(item.size_bytes for item in selected),
            "keep_all": plan.keep_all,
            "snapshot_id": snapshot_id,
            "snapshot_digest": snapshot_digest,
            "quarantine_path": quarantine_path,
            "rollback_available": bool(selected),
            "protected_original_unchanged": True,
            "phone_changed": False,
            "success": True,
        }
        receipt = DebloatReceipt(**payload, receipt_digest=_digest(payload))
        root = self._root(plan.project_id)
        _atomic_json(root / self.RECEIPT_NAME, {"format": self.FORMAT_RECEIPT, **asdict(receipt)})
        _atomic_json(
            root / f"receipt-{receipt.receipt_id[:12]}.romverse",
            {"format": self.FORMAT_RECEIPT, **asdict(receipt)},
        )
        if progress is not None:
            progress(100)
        return receipt

    def rollback_latest(self, project_id: str) -> RecipeRollbackReceipt:
        """Restore the most recent Debloat snapshot into the isolated working tree."""

        receipt = self.load_receipt(project_id)
        if receipt is None or not receipt.rollback_available or not receipt.quarantine_path:
            raise ProjectError("No verified Debloat rollback is available")
        snapshot = RecipeExecutor.load_snapshot(Path(receipt.quarantine_path))
        if snapshot is None or snapshot.snapshot_digest != receipt.snapshot_digest:
            raise ProjectError("Debloat rollback snapshot failed integrity verification")
        result = RecipeExecutor().rollback(
            self._tree(project_id), snapshot, snapshot.snapshot_digest
        )
        _atomic_json(
            self._root(project_id) / f"rollback-{uuid4().hex[:12]}.romverse",
            {
                "format": "romverse.debloat-rollback",
                "schema_version": 1,
                "created_at": datetime.now(UTC).isoformat(),
                "project_id": project_id,
                "receipt_id": receipt.receipt_id,
                "snapshot_id": result.snapshot_id,
                "snapshot_digest": result.snapshot_digest,
                "restored_targets": result.restored_targets,
                "tree_sha256": result.tree_sha256,
                "success": result.success,
                "protected_original_unchanged": self.store.verify_original(project_id).valid,
                "phone_changed": False,
            },
        )
        return result

    def load_scan(self, project_id: str) -> DebloatScan | None:
        try:
            data = self._read(self._root(project_id) / self.SCAN_NAME, self.FORMAT_SCAN)
            candidates = []
            for raw in data.pop("candidates"):
                item = dict(raw)
                item["risk"] = DebloatRisk(str(item["risk"]))
                candidates.append(SystemAppCandidate(**item))
            scan = DebloatScan(**data, candidates=tuple(candidates))
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None
        unsigned = asdict(scan)
        expected = str(unsigned.pop("scan_digest", ""))
        return scan if scan.candidates and expected == _digest(unsigned) else None

    def load_plan(self, project_id: str) -> DebloatPlan | None:
        try:
            data = self._read(self._root(project_id) / self.PLAN_NAME, self.FORMAT_PLAN)
            for key in ("selected_ids", "selected_paths", "caution_ids"):
                data[key] = tuple(str(item) for item in data[key])
            plan = DebloatPlan(**data)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None
        unsigned = asdict(plan)
        expected = str(unsigned.pop("plan_digest", ""))
        return plan if expected == _digest(unsigned) else None

    def load_discovery(self, project_id: str) -> DebloatDiscoveryReport | None:
        try:
            data = self._read(
                self._root(project_id) / self.DISCOVERY_NAME,
                self.FORMAT_DISCOVERY,
            )
            data["partitions"] = tuple(str(item) for item in data["partitions"])
            data["example_paths"] = tuple(str(item) for item in data["example_paths"])
            report = DebloatDiscoveryReport(**data)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None
        unsigned = asdict(report)
        expected = str(unsigned.pop("report_digest", ""))
        if (
            report.schema_version != 1
            or report.project_id != project_id
            or report.phone_changed
            or min(
                report.apk_files_examined,
                report.recognized_apk_files,
                report.candidate_groups,
                report.excluded_apk_files,
            )
            < 0
            or report.recognized_apk_files > report.apk_files_examined
            or report.candidate_groups > report.recognized_apk_files
            or report.excluded_apk_files != report.apk_files_examined - report.recognized_apk_files
            or any(partition not in self.PARTITIONS for partition in report.partitions)
            or len(report.example_paths) > 5
            or any(
                Path(path).is_absolute() or ".." in Path(path).parts or len(path) > 500
                for path in report.example_paths
            )
            or expected != _digest(unsigned)
        ):
            return None
        return report

    def load_receipt(self, project_id: str) -> DebloatReceipt | None:
        try:
            data = self._read(self._root(project_id) / self.RECEIPT_NAME, self.FORMAT_RECEIPT)
            data["removed_paths"] = tuple(str(item) for item in data["removed_paths"])
            receipt = DebloatReceipt(**data)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None
        unsigned = asdict(receipt)
        expected = str(unsigned.pop("receipt_digest", ""))
        if (
            receipt.schema_version != self.SCHEMA_VERSION
            or not receipt.success
            or not receipt.protected_original_unchanged
            or receipt.phone_changed
            or expected != _digest(unsigned)
        ):
            return None
        scan = self.load_scan(project_id)
        if scan is None or scan.content_digest != receipt.scan_content_digest:
            return None
        try:
            tree = self._tree(project_id)
        except ProjectError:
            return None
        if any((tree / relative).exists() for relative in receipt.removed_paths):
            return None
        if receipt.rollback_available:
            snapshot = RecipeExecutor.load_snapshot(Path(receipt.quarantine_path))
            if snapshot is None or snapshot.snapshot_digest != receipt.snapshot_digest:
                return None
        elif receipt.removed_paths or not receipt.keep_all:
            return None
        return receipt

    @classmethod
    def _classify(cls, name: str, relative: str, privileged: bool) -> tuple[DebloatRisk, str]:
        normalized = re.sub(r"[^a-z0-9]", "", f"{name} {relative}".casefold())
        if any(token in normalized for token in cls.PROTECTED_TOKENS):
            return (
                DebloatRisk.PROTECTED,
                "Core Android, setup, security, telephony, input, launcher, or service dependency; removal is locked.",
            )
        if privileged:
            return (
                DebloatRisk.PROTECTED,
                "Privileged app with elevated permissions; an exact Device Pack dependency proof is required before removal.",
            )
        if any(token in normalized for token in cls.SAFE_TOKENS):
            return (
                DebloatRisk.SAFE,
                "Known optional partner, promotion, quick-app, advertising, or analytics component; removal is recommended.",
            )
        return (
            DebloatRisk.CAUTION,
            "No proven critical dependency and no safe-removal proof; review the app purpose before selecting it.",
        )

    def _app_target(self, tree: Path, apk: Path) -> tuple[Path, str, bool] | None:
        relative = apk.relative_to(tree)
        parts = relative.parts
        normalized = tuple(part.casefold() for part in parts)
        for index in range(1, len(parts)):
            app_directory = normalized[index]
            if app_directory not in self.APP_DIRECTORIES:
                continue
            partition = self._partition_before_app(normalized, index)
            if not partition:
                continue
            if index + 1 >= len(parts):
                return None
            target = tree.joinpath(*parts[: index + 2])
            if not target.exists() or target.is_symlink():
                return None
            resolved = target.resolve()
            if not resolved.is_relative_to(tree):
                raise ProjectError("System app target escaped the isolated working tree")
            return resolved, partition, app_directory == "priv-app"
        return None

    @classmethod
    def _partition_before_app(cls, parts: tuple[str, ...], app_index: int) -> str:
        """Infer a partition without treating arbitrary APK folders as system apps.

        ROM archives commonly repeat a partition name below an extraction wrapper,
        for example ``system/system/app`` or ``partition_files/product/root/app``.
        Only known partition names followed by recognized root wrappers are accepted;
        a ``data`` ancestor always keeps the package outside the debloat inventory.
        """

        if "data" in parts[:app_index]:
            return ""
        wrappers = {"root", "system_root", *cls.PARTITIONS}
        for index in range(app_index - 1, -1, -1):
            candidate = parts[index]
            if candidate not in cls.PARTITIONS:
                continue
            if all(part in wrappers for part in parts[index + 1 : app_index]):
                return candidate
            return ""
        return ""

    def _group_apps(
        self,
        tree: Path,
        apk_paths: tuple[Path, ...],
    ) -> tuple[dict[str, list[Path]], dict[str, tuple[Path, str, bool]]]:
        groups: dict[str, list[Path]] = {}
        targets: dict[str, tuple[Path, str, bool]] = {}
        for apk in apk_paths:
            located = self._app_target(tree, apk)
            if located is not None:
                target, partition, privileged = located
                relative = target.relative_to(tree).as_posix()
                groups.setdefault(relative, []).append(apk)
                targets[relative] = (target, partition, privileged)
                if len(groups) > self.MAX_CANDIDATES:
                    raise ProjectError(
                        f"Debloat scan exceeds the {self.MAX_CANDIDATES:,}-app safety limit"
                    )
        return groups, targets

    @staticmethod
    def _apk_paths(tree: Path) -> tuple[Path, ...]:
        return tuple(
            sorted(
                (
                    path
                    for path in tree.rglob("*")
                    if path.suffix.casefold() == ".apk"
                    and path.is_file()
                    and not path.is_symlink()
                    and path.resolve().is_relative_to(tree)
                ),
                key=lambda path: path.as_posix().casefold(),
            )
        )

    def _discovery(
        self,
        project_id: str,
        tree: Path,
        apk_paths: tuple[Path, ...],
        groups: dict[str, list[Path]],
        targets: dict[str, tuple[Path, str, bool]],
        *,
        materialization_attempted: bool,
    ) -> DebloatDiscoveryReport:
        recognized = sum(len(paths) for paths in groups.values())
        payload: dict[str, object] = {
            "schema_version": 1,
            "project_id": project_id,
            "created_at": datetime.now(UTC).isoformat(),
            "apk_files_examined": len(apk_paths),
            "recognized_apk_files": recognized,
            "candidate_groups": len(groups),
            "excluded_apk_files": max(0, len(apk_paths) - recognized),
            "partitions": tuple(sorted({value[1] for value in targets.values()})),
            "materialization_attempted": materialization_attempted,
            "example_paths": tuple(path.relative_to(tree).as_posix() for path in apk_paths[:5]),
            "phone_changed": False,
        }
        return DebloatDiscoveryReport(**payload, report_digest=_digest(payload))

    def _save_discovery(self, report: DebloatDiscoveryReport) -> None:
        root = self._root(report.project_id)
        root.mkdir(parents=True, exist_ok=True)
        _atomic_json(
            root / self.DISCOVERY_NAME,
            {"format": self.FORMAT_DISCOVERY, **asdict(report)},
        )

    @staticmethod
    def _discovery_summary(report: DebloatDiscoveryReport) -> str:
        partitions = ", ".join(report.partitions) if report.partitions else "none recognized"
        materialization = (
            "image filesystem preparation was attempted"
            if report.materialization_attempted
            else "existing extracted files were inspected"
        )
        return (
            f"Discovery evidence: {report.apk_files_examined} APK file(s) examined, "
            f"{report.recognized_apk_files} recognized in {report.candidate_groups} app "
            f"group(s), {report.excluded_apk_files} excluded as overlays, user-data, or "
            f"unrecognized layout; partitions: {partitions}; {materialization}; phone changed: NO."
        )

    def _prepare_partition_trees(
        self,
        project_id: str,
    ) -> None:
        """Materialize OTA app filesystems locally before an inventory scan.

        This never contacts or changes a phone. It only uses source-bound payload images
        inside the project's isolated working tree.
        """
        if self.filesystems is None:
            raise ProjectError(
                "Nebula Debloat needs verified filesystem extractors to scan this image-based "
                "firmware. Open Forge Arsenal, verify the managed tools, and rescan."
            )
        manifest = self.payloads.load(project_id) if self.payloads is not None else None
        if manifest is None and self.payloads is not None:
            try:
                manifest = self.payloads.scan(project_id)
            except ProjectError:
                manifest = None
        available = (
            self.filesystems.available_partitions(project_id)
            if hasattr(self.filesystems, "available_partitions")
            else tuple(item.name for item in manifest.partitions)
            if manifest is not None
            else ()
        )
        partitions = tuple(name for name in available if name in self.PARTITIONS)
        if not partitions:
            tree = self._tree(project_id)
            if any(tree.rglob("super.img")):
                unpack_super = getattr(self.filesystems, "unpack_super", None)
                if not callable(unpack_super):
                    raise ProjectError(
                        "This fastboot source keeps Android apps inside super.img. Verify LP Unpack "
                        "in Forge Arsenal, materialize the logical system/product partitions, and rescan."
                    )
                unpack_super(
                    project_id,
                    self.PARTITIONS,
                    _ignore_progress,
                )
                partitions = tuple(
                    name
                    for name in self.filesystems.available_partitions(project_id)
                    if name in self.PARTITIONS
                )
                if not partitions:
                    raise ProjectError(
                        "LP Unpack completed but no supported Android app partitions were materialized"
                    )
            if not partitions:
                raise ProjectError(
                    "The firmware exposes no supported Android app filesystem partitions."
                )
        existing = {item.partition for item in self.filesystems.list_manifests(project_id)}
        records = {item.name: item for item in manifest.partitions} if manifest is not None else {}
        missing_images = tuple(
            name
            for name in partitions
            if name not in existing and name in records and not records[name].extracted_path
        )
        if missing_images:
            assert self.payloads is not None
            manifest = self.payloads.extract(
                project_id,
                missing_images,
                _ignore_progress,
            )
        failures = []
        for partition in partitions:
            if partition in existing:
                continue
            try:
                plan = self.filesystems.plan(project_id, partition)
                if not plan.safe:
                    raise ProjectError(plan.reason)
                self.filesystems.expand(project_id, partition)
            except ProjectError as exc:
                failures.append(f"{partition}: {exc}")
        if failures:
            raise ProjectError(
                "Nebula Debloat could not build a complete app inventory: " + "; ".join(failures)
            )

    def _tree(self, project_id: str) -> Path:
        self.store.get(project_id)
        tree = (self.store.working_root / project_id / "tree").resolve()
        if not tree.is_dir():
            raise ProjectError("Debloat requires an extracted working tree")
        return tree

    def _root(self, project_id: str) -> Path:
        self.store.get(project_id)
        return self.store.projects_root / project_id / "debloat"

    @staticmethod
    def _read(path: Path, expected_format: str) -> dict[str, object]:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.pop("format") != expected_format:
            raise ValueError("unexpected debloat record format")
        return data


def _package_hint(apks: tuple[Path, ...]) -> str:
    stems = tuple(dict.fromkeys(path.stem for path in apks))
    return ", ".join(stems[:3]) + (" …" if len(stems) > 3 else "")


def _ignore_progress(*_values: object) -> None:
    """Consume nested-tool progress while the enclosing workflow has no bounded total."""


def _candidate_payload(item: SystemAppCandidate) -> dict[str, object]:
    payload = asdict(item)
    payload["risk"] = item.risk.value
    return payload


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
