from __future__ import annotations

import hashlib
import json
import os
import shutil
import zipfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

from romverse.ascension.build_handoff import (
    RootRomBuildHandoffReceipt,
    RootRomBuildHandoffService,
)
from romverse.ascension.integration import RootRomIntegrationService
from romverse.ascension.models import AscensionMethod
from romverse.infrastructure.local_store import (
    LocalStoreConflictError,
    LocalStoreError,
    ensure_private_directory,
    exclusive_create_json,
    read_json_object,
)
from romverse.infrastructure.tools import ToolStatus
from romverse.rom.builds import RomBuildPlanner
from romverse.rom.models import ArtifactVerification, ProjectError
from romverse.rom.projects import RomProjectStore


@dataclass(frozen=True, slots=True)
class ForgeBundleEntry:
    path: str
    size_bytes: int
    sha256: str
    kind: str = "file"
    link_target: str = ""
    scope: str = "tree"


@dataclass(frozen=True, slots=True)
class ForgeBundleReceipt:
    schema_version: int
    project_id: str
    created_at: str
    output_path: str
    archive_sha256: str
    manifest_sha256: str
    plan_tree_sha256: str
    file_count: int
    content_bytes: int
    signed: bool
    bootable: bool
    flashable: bool
    ascension_handoff_digest: str = ""
    rooted_partition: str = ""
    rooted_artifact_sha256: str = ""
    build_plan_digest: str = ""
    source_sha256: str = ""
    toolchain_manifest_digest: str = ""
    guided_choice_digest: str = ""


class ForgeBundleService:
    """Create a deterministic, verified workspace bundle without building or signing a ROM."""

    MANIFEST_MEMBER = "ROMVERSE-FORGE-MANIFEST.json"
    RECEIPT_NAME = "latest-forge-bundle.romverse"
    CHUNK_SIZE = 4 * 1024 * 1024
    MAX_ENTRIES = 500_000
    MAX_MANIFEST_BYTES = 16 * 1024 * 1024
    MAX_PATH_LENGTH = 4_096
    MAX_RECEIPT_BYTES = 256 * 1024
    FREE_SPACE_RESERVE = 512 * 1024 * 1024
    ZIP_TIMESTAMP = (2020, 1, 1, 0, 0, 0)

    def __init__(
        self,
        store: RomProjectStore,
        tool_statuses: tuple[ToolStatus, ...] = (),
    ) -> None:
        self.store = store
        self.tool_statuses = tool_statuses

    def create(
        self,
        project_id: str,
        progress: Callable[[int, int], None] | None = None,
    ) -> ForgeBundleReceipt:
        planner = RomBuildPlanner(self.store)
        plan = planner.load(project_id)
        if plan is None:
            raise ProjectError("Create a deterministic build plan before forging a bundle")
        if plan.schema_version >= 3:
            if not self.tool_statuses:
                raise ProjectError(
                    "Fresh source-scoped tool evidence is required before forging this bundle"
                )
            planner = RomBuildPlanner(self.store, self.tool_statuses, plan.required_tools)
        if plan.project_id != project_id:
            raise ProjectError("Build plan project identity does not match this project")
        planned_paths = (*plan.input_files, *(path for path, _target in plan.input_symlinks))
        if len({value.casefold() for value in planned_paths}) != len(planned_paths):
            raise ProjectError("Build plan contains duplicate input paths")
        if len(planned_paths) > self.MAX_ENTRIES:
            raise ProjectError("Build plan exceeds the Forge Bundle file-count limit")
        root = self._tree_root(plan.source_tree)
        paths = tuple((relative, self._input_path(root, relative)) for relative in plan.input_files)
        verification = planner.verify_tree(project_id)
        if not verification.valid:
            raise ProjectError(verification.status)
        receipt_path = self._receipt_path(project_id)
        existing_receipt = self.load_receipt(project_id)
        if os.path.lexists(receipt_path) and existing_receipt is None:
            raise ProjectError(
                "The saved Forge receipt is unreadable or ambiguous and was not overwritten"
            )
        if existing_receipt is not None and not self.receipt_matches_plan(existing_receipt, plan):
            if not self.verify_receipt(project_id, existing_receipt).valid:
                raise ProjectError(
                    "The saved Forge receipt does not match this plan and failed historical "
                    "verification; nothing was overwritten"
                )
            self.preserve_history(project_id, existing_receipt)

        ascension = self._ascension_handoff(project_id)
        if (
            ascension is not None
            and ascension.schema_version < RootRomBuildHandoffService.SCHEMA_VERSION
        ):
            ascension = RootRomBuildHandoffService(self.store).seal(project_id, ascension.method)
        if ascension is None and any(
            RootRomIntegrationService(self.store).load(project_id, method) is not None
            for method in AscensionMethod
        ):
            raise ProjectError(
                "The rooted ROM input must pass Ascension Build Seal before Forge export"
            )

        entries: list[ForgeBundleEntry] = []
        sources: dict[tuple[str, str], Path] = {
            ("tree", relative): path for relative, path in paths
        }
        if ascension is not None and ascension.packaging_route == "payload-partition":
            logical = f"rooted-{ascension.target_partition}.img"
            sources[("ascension", logical)] = RootRomBuildHandoffService(self.store).artifact_path(
                ascension
            )
        if len(planned_paths) + (len(sources) - len(paths)) > self.MAX_ENTRIES:
            raise ProjectError("Build plan exceeds the Forge Bundle file-count limit")
        total_bytes = sum(path.stat().st_size for path in sources.values())
        progressed = 0
        # Input hashing, archive streaming, and final archive hashing are all
        # potentially multi-minute phases for Android super images. Give each a
        # real byte-weighted progress segment instead of appearing frozen.
        progress_total = max(1, total_bytes * 3)
        for (scope, relative), path in sources.items():
            digest, size = self._hash_file(
                path,
                (
                    lambda done, base=progressed: (
                        progress(min(base + done, progress_total), progress_total)
                        if progress is not None
                        else None
                    )
                ),
            )
            entries.append(ForgeBundleEntry(relative, size, digest, scope=scope))
            progressed += size
            if progress is not None:
                progress(progressed, progress_total)
        for relative, target in plan.input_symlinks:
            self._validate_relative(relative)
            target_bytes = target.encode("utf-8")
            entries.append(
                ForgeBundleEntry(
                    relative,
                    len(target_bytes),
                    hashlib.sha256(target_bytes).hexdigest(),
                    "symlink",
                    target,
                )
            )
        entries.sort(key=lambda entry: (entry.scope, entry.path))
        ascension_member = ""
        if ascension is not None:
            ascension_member = (
                f"tree/{ascension.target_relative_path}"
                if ascension.packaging_route == "fastboot-image-tree"
                else f"ascension/rooted-{ascension.target_partition}.img"
            )
            matching = next(
                (entry for entry in entries if self._member(entry) == ascension_member),
                None,
            )
            if (
                matching is None
                or matching.sha256 != ascension.artifact_sha256
                or matching.size_bytes != ascension.artifact_size_bytes
            ):
                raise ProjectError(
                    "Ascension Build Seal does not match the deterministic Forge input"
                )
        content_bytes = sum(entry.size_bytes for entry in entries)

        manifest_payload = {
            "format": "romverse.forge-bundle",
            "schema_version": 4 if plan.schema_version >= 3 else 3,
            "project_id": project_id,
            "plan_created_at": plan.created_at,
            "plan_tree_sha256": plan.tree_sha256,
            "build_plan_digest": plan.plan_digest if plan.schema_version >= 3 else "",
            "source_sha256": plan.source_sha256 if plan.schema_version >= 3 else "",
            "toolchain_manifest_digest": (
                plan.toolchain_manifest_digest if plan.schema_version >= 3 else ""
            ),
            "guided_choice_digest": (
                plan.guided_choice_digest if plan.schema_version >= 3 else ""
            ),
            "recipe_digest": plan.recipe_digest,
            "device_pack_id": plan.device_pack_id,
            "entries": [asdict(entry) for entry in entries],
            "content_bytes": content_bytes,
            "ascension": (
                {
                    "method": ascension.method.value,
                    "build_handoff_digest": ascension.handoff_digest,
                    "target_partition": ascension.target_partition,
                    "target_relative_path": ascension.target_relative_path,
                    "artifact_sha256": ascension.artifact_sha256,
                    "artifact_size_bytes": ascension.artifact_size_bytes,
                    "packaging_route": ascension.packaging_route,
                    "member": ascension_member,
                    "flash_authority": False,
                    "phone_changed": False,
                    "bootloader_relock_allowed": False,
                }
                if ascension is not None
                else None
            ),
            "safety": {
                "protected_original_included": False,
                "signed": False,
                "bootable": False,
                "flashable": False,
                "phone_changed": False,
            },
        }
        manifest_bytes = (
            json.dumps(manifest_payload, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        output_root = self._output_root(project_id)
        required_free = content_bytes + len(manifest_bytes) + self.FREE_SPACE_RESERVE
        available_free = shutil.disk_usage(output_root).free
        if available_free < required_free:
            raise ProjectError(
                "Forge Bundle needs "
                f"{_human_bytes(required_free)} free including its safety reserve; "
                f"{_human_bytes(available_free)} is available in {output_root}"
            )
        partial = output_root / f".{uuid4().hex}.forge.part"
        try:
            with zipfile.ZipFile(
                partial,
                "w",
                compression=zipfile.ZIP_STORED,
                allowZip64=True,
            ) as archive:
                archive.writestr(self._zip_info(self.MANIFEST_MEMBER), manifest_bytes)
                for entry in entries:
                    if entry.kind == "symlink":
                        archive.writestr(
                            self._zip_info(self._member(entry), symlink=True),
                            entry.link_target.encode("utf-8"),
                        )
                        continue
                    path = sources[(entry.scope, entry.path)]
                    digest = hashlib.sha256()
                    copied = 0
                    info = self._zip_info(self._member(entry))
                    # ZipFile.open() otherwise assumes a zero-sized streamed
                    # member. Supplying the exact size and forcing ZIP64 for a
                    # large member prevents Python's late "File size too large"
                    # failure after gigabytes have already been copied.
                    info.file_size = entry.size_bytes
                    with (
                        path.open("rb") as source,
                        archive.open(
                            info,
                            "w",
                            force_zip64=entry.size_bytes >= zipfile.ZIP64_LIMIT,
                        ) as destination,
                    ):
                        while chunk := source.read(self.CHUNK_SIZE):
                            destination.write(chunk)
                            digest.update(chunk)
                            copied += len(chunk)
                            if progress is not None:
                                progress(progressed + copied, progress_total)
                    if copied != entry.size_bytes or digest.hexdigest() != entry.sha256:
                        raise ProjectError(
                            f"Working-tree input changed while bundling: {entry.path}"
                        )
                    progressed += copied
            archive_sha256, _archive_size = self._hash_file(
                partial,
                (
                    lambda done: (
                        progress(
                            min(progressed + done, max(0, progress_total - 1)),
                            progress_total,
                        )
                        if progress is not None
                        else None
                    )
                ),
            )
            output = output_root / f"forge-{archive_sha256[:20]}.romverse.zip"
            if output.exists():
                if output.is_symlink() or not output.is_file():
                    raise ProjectError("Forge output path is not a regular file")
                existing_sha256, _size = self._hash_file(output)
                if existing_sha256 != archive_sha256:
                    raise ProjectError("Existing Forge output does not match its content address")
                partial.unlink()
            else:
                os.replace(partial, output)
        finally:
            if partial.exists():
                partial.unlink()

        receipt = ForgeBundleReceipt(
            3 if plan.schema_version >= 3 else 2,
            project_id,
            datetime.now(UTC).isoformat(),
            output.relative_to(self.store.workspace).as_posix(),
            archive_sha256,
            manifest_sha256,
            plan.tree_sha256,
            len(entries),
            content_bytes,
            False,
            False,
            False,
            ascension.handoff_digest if ascension is not None else "",
            ascension.target_partition if ascension is not None else "",
            ascension.artifact_sha256 if ascension is not None else "",
            plan.plan_digest if plan.schema_version >= 3 else "",
            plan.source_sha256 if plan.schema_version >= 3 else "",
            plan.toolchain_manifest_digest if plan.schema_version >= 3 else "",
            plan.guided_choice_digest if plan.schema_version >= 3 else "",
        )
        self._write_receipt(project_id, receipt)
        if progress is not None:
            progress(progress_total, progress_total)
        return receipt

    def verify(
        self,
        project_id: str,
        progress: Callable[[int, int], None] | None = None,
    ) -> ArtifactVerification:
        receipt = self.load_receipt(project_id)
        if receipt is None:
            return ArtifactVerification(False, "No Forge Bundle receipt")
        return self.verify_receipt(project_id, receipt, progress)

    def verify_receipt(
        self,
        project_id: str,
        receipt: ForgeBundleReceipt,
        progress: Callable[[int, int], None] | None = None,
    ) -> ArtifactVerification:
        """Verify one exact current or historical receipt without changing latest evidence."""

        if receipt is None:
            return ArtifactVerification(False, "No Forge Bundle receipt")
        if receipt.schema_version not in {1, 2, 3} or receipt.project_id != project_id:
            return ArtifactVerification(False, "Forge Bundle receipt project identity is invalid")
        if receipt.signed or receipt.bootable or receipt.flashable:
            return ArtifactVerification(False, "Forge Bundle receipt safety contract is invalid")
        try:
            output = self._receipt_output(receipt.output_path, project_id)
            archive_size = output.stat().st_size
            verify_total = max(1, archive_size + receipt.content_bytes)
            actual_archive_sha256, _size = self._hash_file(
                output,
                (
                    lambda done: (
                        progress(min(done, max(0, verify_total - 1)), verify_total)
                        if progress is not None
                        else None
                    )
                ),
            )
            if actual_archive_sha256 != receipt.archive_sha256:
                return ArtifactVerification(
                    False,
                    "Forge Bundle archive hash mismatch",
                    receipt.archive_sha256,
                    actual_archive_sha256,
                )
            with zipfile.ZipFile(output) as archive:
                names = archive.namelist()
                if (
                    not names
                    or len(names) > self.MAX_ENTRIES + 1
                    or names[0] != self.MANIFEST_MEMBER
                ):
                    return ArtifactVerification(False, "Forge Bundle manifest is missing")
                manifest_info = archive.getinfo(self.MANIFEST_MEMBER)
                if (
                    manifest_info.file_size > self.MAX_MANIFEST_BYTES
                    or manifest_info.compress_type != zipfile.ZIP_STORED
                ):
                    return ArtifactVerification(False, "Forge Bundle manifest is unsafe")
                manifest_bytes = archive.read(self.MANIFEST_MEMBER)
                if hashlib.sha256(manifest_bytes).hexdigest() != receipt.manifest_sha256:
                    return ArtifactVerification(False, "Forge Bundle manifest hash mismatch")
                manifest = json.loads(manifest_bytes)
                if (
                    manifest.get("format") != "romverse.forge-bundle"
                    or manifest.get("schema_version") not in {1, 2, 3, 4}
                    or manifest.get("project_id") != project_id
                    or manifest.get("plan_tree_sha256") != receipt.plan_tree_sha256
                ):
                    return ArtifactVerification(False, "Forge Bundle identity is invalid")
                exact_binding_invalid = receipt.schema_version >= 3 and (
                    manifest.get("schema_version") != 4
                    or manifest.get("build_plan_digest") != receipt.build_plan_digest
                    or manifest.get("source_sha256") != receipt.source_sha256
                    or manifest.get("toolchain_manifest_digest")
                    != receipt.toolchain_manifest_digest
                    or manifest.get("guided_choice_digest") != receipt.guided_choice_digest
                )
                downgraded_binding = (
                    receipt.schema_version < 3 and manifest.get("schema_version") == 4
                )
                if exact_binding_invalid or downgraded_binding:
                    return ArtifactVerification(
                        False, "Forge Bundle exact build-plan binding is invalid"
                    )
                safety = manifest.get("safety", {})
                if not isinstance(safety, dict) or any(
                    safety.get(key) is not False
                    for key in (
                        "protected_original_included",
                        "signed",
                        "bootable",
                        "flashable",
                        "phone_changed",
                    )
                ):
                    return ArtifactVerification(False, "Forge Bundle safety contract is invalid")
                raw_entries = manifest.get("entries")
                if not isinstance(raw_entries, list):
                    return ArtifactVerification(False, "Forge Bundle entries are invalid")
                if len(raw_entries) != receipt.file_count:
                    return ArtifactVerification(False, "Forge Bundle file count is invalid")
                expected_names = {self.MANIFEST_MEMBER}
                seen_paths: set[str] = set()
                entries_by_member: dict[str, dict] = {}
                content_bytes = 0
                for value in raw_entries:
                    if not isinstance(value, dict):
                        return ArtifactVerification(False, "Forge Bundle entry is invalid")
                    relative = str(value.get("path", ""))
                    self._validate_relative(relative)
                    kind = str(value.get("kind", "file"))
                    link_target = str(value.get("link_target", ""))
                    scope = str(value.get("scope", "tree"))
                    if kind not in {"file", "symlink"}:
                        return ArtifactVerification(False, "Forge Bundle entry kind is invalid")
                    if scope not in {"tree", "ascension"} or (
                        scope == "ascension" and kind != "file"
                    ):
                        return ArtifactVerification(False, "Forge Bundle entry scope is invalid")
                    normalized = f"{scope}/{relative}".casefold()
                    if normalized in seen_paths:
                        return ArtifactVerification(False, "Forge Bundle contains duplicate paths")
                    seen_paths.add(normalized)
                    member = f"{scope}/{relative}"
                    expected_names.add(member)
                    entries_by_member[member] = value
                    info = archive.getinfo(member)
                    expected_size = int(value.get("size_bytes", -1))
                    unix_kind = (info.external_attr >> 16) & 0o170000
                    if (
                        info.compress_type != zipfile.ZIP_STORED
                        or expected_size < 0
                        or info.file_size != expected_size
                    ):
                        return ArtifactVerification(
                            False, f"Forge Bundle member is unsafe: {relative}"
                        )
                    digest = hashlib.sha256()
                    size = 0
                    with archive.open(member) as stream:
                        while chunk := stream.read(self.CHUNK_SIZE):
                            digest.update(chunk)
                            size += len(chunk)
                            if progress is not None:
                                progress(
                                    min(
                                        archive_size + content_bytes + size,
                                        max(0, verify_total - 1),
                                    ),
                                    verify_total,
                                )
                    if kind == "symlink":
                        try:
                            encoded_target = link_target.encode("utf-8")
                        except UnicodeError:
                            return ArtifactVerification(
                                False, f"Forge Bundle link target is invalid: {relative}"
                            )
                        if (
                            unix_kind != 0o120000
                            or len(encoded_target) > self.MAX_PATH_LENGTH
                            or any(ord(character) < 32 for character in link_target)
                            or size != len(encoded_target)
                            or archive.read(member) != encoded_target
                        ):
                            return ArtifactVerification(
                                False, f"Forge Bundle symbolic link is unsafe: {relative}"
                            )
                    elif unix_kind == 0o120000:
                        return ArtifactVerification(
                            False, f"Forge Bundle member is unsafe: {relative}"
                        )
                    if size != expected_size or digest.hexdigest() != str(value.get("sha256", "")):
                        return ArtifactVerification(
                            False, f"Forge Bundle entry failed verification: {relative}"
                        )
                    content_bytes += size
                if content_bytes != receipt.content_bytes:
                    return ArtifactVerification(False, "Forge Bundle content size is invalid")
                if set(names) != expected_names or len(names) != len(expected_names):
                    return ArtifactVerification(False, "Forge Bundle contains unexpected entries")
                ascension = manifest.get("ascension")
                if receipt.ascension_handoff_digest:
                    current = self._ascension_handoff(project_id)
                    if (
                        current is None
                        or not isinstance(ascension, dict)
                        or current.handoff_digest != receipt.ascension_handoff_digest
                        or current.target_partition != receipt.rooted_partition
                        or current.artifact_sha256 != receipt.rooted_artifact_sha256
                        or ascension
                        != {
                            "method": current.method.value,
                            "build_handoff_digest": current.handoff_digest,
                            "target_partition": current.target_partition,
                            "target_relative_path": current.target_relative_path,
                            "artifact_sha256": current.artifact_sha256,
                            "artifact_size_bytes": current.artifact_size_bytes,
                            "packaging_route": current.packaging_route,
                            "member": (
                                f"tree/{current.target_relative_path}"
                                if current.packaging_route == "fastboot-image-tree"
                                else f"ascension/rooted-{current.target_partition}.img"
                            ),
                            "flash_authority": False,
                            "phone_changed": False,
                            "bootloader_relock_allowed": False,
                        }
                        or str(ascension.get("member", "")) not in entries_by_member
                        or str(entries_by_member[str(ascension["member"])].get("sha256", ""))
                        != current.artifact_sha256
                    ):
                        return ArtifactVerification(
                            False, "Forge Bundle Ascension provenance is invalid"
                        )
                elif ascension is not None:
                    return ArtifactVerification(
                        False, "Forge Bundle contains unreceipted Ascension provenance"
                    )
        except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, ProjectError) as exc:
            return ArtifactVerification(False, f"Forge Bundle verification failed: {exc}")
        root_state = (
            f"; Ascension {receipt.rooted_partition} provenance verified"
            if receipt.ascension_handoff_digest
            else "; unrooted bundle"
        )
        if progress is not None:
            progress(verify_total, verify_total)
        return ArtifactVerification(
            True,
            "Forge Bundle verified" + root_state + "; unsigned, non-bootable, and non-flashable",
            receipt.archive_sha256,
            receipt.archive_sha256,
        )

    def load_receipt(self, project_id: str) -> ForgeBundleReceipt | None:
        path = self._receipt_path(project_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return self._receipt_from_mapping(data)
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return None

    def preserve_history(self, project_id: str, receipt: ForgeBundleReceipt) -> str:
        """Exclusively retain one valid receipt while immutable archive bytes stay in place."""

        if receipt.project_id != project_id:
            raise ProjectError("Forge history receipt belongs to another project")
        payload = self._receipt_mapping(receipt)
        digest = _mapping_digest(payload)
        root = self.store.projects_root / project_id / "forge-history"
        destination = root / f"{digest}.romverse"
        try:
            ensure_private_directory(root, boundary=self.store.workspace)
            exclusive_create_json(
                destination,
                payload,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
        except LocalStoreConflictError:
            try:
                existing = read_json_object(
                    destination,
                    boundary=self.store.workspace,
                    maximum_bytes=self.MAX_RECEIPT_BYTES,
                )
            except LocalStoreError as exc:
                raise ProjectError("Existing Forge history evidence is ambiguous") from exc
            if existing != payload:
                raise ProjectError(
                    "Forge history content-address collision; nothing was replaced"
                ) from None
        except LocalStoreError as exc:
            raise ProjectError(f"Forge history could not be preserved safely: {exc}") from exc
        return digest

    def load_history_receipt(self, project_id: str, receipt_digest: str) -> ForgeBundleReceipt | None:
        if not _is_sha256(receipt_digest):
            return None
        try:
            payload = read_json_object(
                self.store.projects_root
                / project_id
                / "forge-history"
                / f"{receipt_digest}.romverse",
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
        except LocalStoreError:
            return None
        if _mapping_digest(payload) != receipt_digest:
            return None
        try:
            receipt = self._receipt_from_mapping(payload)
        except (ValueError, KeyError, TypeError):
            return None
        return receipt if receipt is not None and receipt.project_id == project_id else None

    @staticmethod
    def receipt_matches_plan(receipt: ForgeBundleReceipt, plan) -> bool:
        if receipt.project_id != plan.project_id or receipt.plan_tree_sha256 != plan.tree_sha256:
            return False
        if plan.schema_version >= 3:
            return (
                receipt.schema_version == 3
                and receipt.build_plan_digest == plan.plan_digest
                and receipt.source_sha256 == plan.source_sha256
                and receipt.toolchain_manifest_digest == plan.toolchain_manifest_digest
                and receipt.guided_choice_digest == plan.guided_choice_digest
            )
        return receipt.schema_version in {1, 2}

    def _tree_root(self, source_tree: str) -> Path:
        relative = self._validate_relative(source_tree)
        root = self.store.workspace.joinpath(*relative.parts)
        if root.is_symlink() or not root.is_dir():
            raise ProjectError("Forge source tree is missing or unsafe")
        resolved = root.resolve()
        if not resolved.is_relative_to(self.store.working_root.resolve()):
            raise ProjectError("Forge source tree escapes the contained working store")
        return root

    def _input_path(self, root: Path, relative: str) -> Path:
        safe_relative = self._validate_relative(relative)
        path = root.joinpath(*safe_relative.parts)
        if path.is_symlink() or not path.is_file():
            raise ProjectError(f"Forge input is missing or unsafe: {relative}")
        if not path.resolve().is_relative_to(root.resolve()):
            raise ProjectError(f"Forge input escapes the working tree: {relative}")
        return path

    def _output_root(self, project_id: str) -> Path:
        builds_root = self.store.workspace / "builds"
        if builds_root.is_symlink():
            raise ProjectError("Build output root cannot be a symbolic link")
        builds_root.mkdir(parents=True, exist_ok=True)
        output = builds_root / project_id
        if output.is_symlink():
            raise ProjectError("Project build output cannot be a symbolic link")
        output.mkdir(parents=True, exist_ok=True)
        if not output.resolve().is_relative_to(builds_root.resolve()):
            raise ProjectError("Forge output escapes the build store")
        return output

    def _receipt_output(self, output_path: str, project_id: str) -> Path:
        relative = self._validate_relative(output_path)
        output = self.store.workspace.joinpath(*relative.parts)
        expected_root = self._output_root(project_id).resolve()
        if output.is_symlink() or not output.is_file():
            raise ProjectError("Forge Bundle output is missing or unsafe")
        if not output.resolve().is_relative_to(expected_root):
            raise ProjectError("Forge Bundle receipt path escapes the project build store")
        return output

    def _ascension_handoff(self, project_id: str) -> RootRomBuildHandoffReceipt | None:
        service = RootRomBuildHandoffService(self.store)
        receipts = tuple(
            receipt
            for method in AscensionMethod
            if (receipt := service.load(project_id, method)) is not None
        )
        if len(receipts) > 1:
            raise ProjectError("Forge Bundle found multiple active Ascension Build Seals")
        return receipts[0] if receipts else None

    @staticmethod
    def _member(entry: ForgeBundleEntry) -> str:
        return f"{entry.scope}/{entry.path}"

    @staticmethod
    def _validate_relative(value: str) -> PurePosixPath:
        relative = PurePosixPath(value)
        if (
            not value
            or len(value) > ForgeBundleService.MAX_PATH_LENGTH
            or "\\" in value
            or relative.is_absolute()
            or ".." in relative.parts
            or "." in relative.parts
            or relative.parts[0].endswith(":")
        ):
            raise ProjectError("Forge manifest contains an unsafe relative path")
        return relative

    @classmethod
    def _hash_file(
        cls,
        path: Path,
        progress: Callable[[int], None] | None = None,
    ) -> tuple[str, int]:
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as stream:
            while chunk := stream.read(cls.CHUNK_SIZE):
                digest.update(chunk)
                size += len(chunk)
                if progress is not None:
                    progress(size)
        return digest.hexdigest(), size

    @classmethod
    def _zip_info(cls, name: str, *, symlink: bool = False) -> zipfile.ZipInfo:
        info = zipfile.ZipInfo(name, cls.ZIP_TIMESTAMP)
        info.compress_type = zipfile.ZIP_STORED
        info.create_system = 3
        info.external_attr = (0o120777 if symlink else 0o100644) << 16
        return info

    def _write_receipt(self, project_id: str, receipt: ForgeBundleReceipt) -> None:
        path = self._receipt_path(project_id)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps({"format": "romverse.forge-bundle-receipt", **asdict(receipt)}, indent=2)
            + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)

    def _receipt_path(self, project_id: str) -> Path:
        return self.store.projects_root / project_id / self.RECEIPT_NAME

    @staticmethod
    def _receipt_mapping(receipt: ForgeBundleReceipt) -> dict[str, object]:
        return {"format": "romverse.forge-bundle-receipt", **asdict(receipt)}

    @staticmethod
    def _receipt_from_mapping(data: dict[str, object]) -> ForgeBundleReceipt | None:
        if data.get("format") != "romverse.forge-bundle-receipt":
            return None
        receipt = ForgeBundleReceipt(
            int(data["schema_version"]),
            str(data["project_id"]),
            str(data["created_at"]),
            str(data["output_path"]),
            str(data["archive_sha256"]),
            str(data["manifest_sha256"]),
            str(data["plan_tree_sha256"]),
            int(data["file_count"]),
            int(data["content_bytes"]),
            bool(data["signed"]),
            bool(data["bootable"]),
            bool(data["flashable"]),
            str(data.get("ascension_handoff_digest", "")),
            str(data.get("rooted_partition", "")),
            str(data.get("rooted_artifact_sha256", "")),
            str(data.get("build_plan_digest", "")),
            str(data.get("source_sha256", "")),
            str(data.get("toolchain_manifest_digest", "")),
            str(data.get("guided_choice_digest", "")),
        )
        exact_fields = (
            receipt.build_plan_digest,
            receipt.source_sha256,
            receipt.toolchain_manifest_digest,
            receipt.guided_choice_digest,
        )
        if (
            receipt.schema_version not in {1, 2, 3}
            or (
                receipt.schema_version == 3
                and not all(_is_sha256(item) for item in exact_fields)
            )
            or (receipt.schema_version < 3 and any(exact_fields))
        ):
            return None
        return receipt


def _human_bytes(value: int) -> str:
    size = float(max(0, value))
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} TiB"


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _mapping_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
