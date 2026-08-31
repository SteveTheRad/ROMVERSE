from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import struct
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from romverse.infrastructure.local_store import atomic_write_json, read_json_object
from romverse.infrastructure.process import CommandRunner
from romverse.infrastructure.tools import ToolStatus
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.rom.source_identity import identify_firmware_source

ProgressCallback = Callable[[int], None]


@dataclass(frozen=True, slots=True)
class ObservedLogicalPartition:
    name: str
    group_name: str
    size_bytes: int
    populated: bool


@dataclass(frozen=True, slots=True)
class ObservedPartitionGroup:
    name: str
    maximum_size_bytes: int


@dataclass(frozen=True, slots=True)
class FastbootSourceBlueprint:
    """Project-local facts observed from one immutable fastboot source.

    This is build evidence, not a published Device Pack and never flash authority.
    """

    schema_version: int
    blueprint_id: str
    project_id: str
    created_at: str
    manufacturer: str
    codename: str
    build_id: str
    android_version: str
    region: str
    source_archive_sha256: str
    source_super_path: str
    source_super_size_bytes: int
    source_super_modified_ns: int
    source_super_sha256: str
    raw_super_path: str
    raw_super_size_bytes: int
    raw_super_modified_ns: int
    raw_super_sha256: str
    super_total_size_bytes: int
    super_used_size_bytes: int
    groups: tuple[ObservedPartitionGroup, ...]
    partitions: tuple[ObservedLogicalPartition, ...]
    vbmeta_images: tuple[tuple[str, str], ...]
    avb_topology_verified: bool
    plan_mode: str
    plan_digest: str
    authority: str
    phone_changed: bool
    blueprint_digest: str

    @property
    def baseline_candidate_ready(self) -> bool:
        return bool(
            self.partitions
            and any(item.populated for item in self.partitions)
            and self.super_total_size_bytes >= self.super_used_size_bytes > 0
            and self.plan_mode == "verified-fastboot-baseline"
        )

    @property
    def source_kind(self) -> str:
        return "fastboot-super"

    @property
    def candidate_sha256(self) -> str:
        return self.source_super_sha256


class FastbootSourceBlueprintService:
    """Derive a source-bound local contract from a Xiaomi-style fastboot super image."""

    NAME = "source-blueprint.romverse"
    RAW_NAME = "super.raw.img"
    SPARSE_MAGIC = 0xED26FF3A
    MIN_RESERVE = 2 * 1024 * 1024 * 1024
    MAX_RECEIPT_BYTES = 512 * 1024
    MAX_GROUPS = 128
    MAX_PARTITIONS = 1_024
    MAX_VBMETA_IMAGES = 32

    def __init__(
        self,
        store: RomProjectStore,
        tool_statuses: tuple[ToolStatus, ...],
        runner: CommandRunner,
    ) -> None:
        self.store = store
        self.tool_statuses = tool_statuses
        self.runner = runner

    def prepare(
        self,
        project_id: str,
        progress: ProgressCallback | None = None,
    ) -> FastbootSourceBlueprint:
        project = self.store.get(project_id)
        if project.original is None:
            raise ProjectError("Import and verify a protected firmware source first")
        source_verification = self.store.verify_original(project_id)
        if not source_verification.valid:
            raise ProjectError(
                f"Protected source failed verification: {source_verification.status}"
            )
        tree = (self.store.working_root / project_id / "tree").resolve()
        if not tree.is_dir():
            raise ProjectError("Create the isolated firmware tree first")
        super_image = self._one_source_super(tree)
        existing = self.load(project_id)
        if existing is not None and (
            existing.avb_topology_verified or not self._tool_candidates("AVBTool", ("avbtool",))
        ):
            self._report(progress, 100)
            return existing
        source_stat = super_image.stat()
        sparse = self._is_sparse(super_image)
        blueprint_root = self.store.working_root / project_id / "source-blueprint"
        blueprint_root.mkdir(parents=True, exist_ok=True)
        raw_super = blueprint_root / self.RAW_NAME
        if sparse:
            required = source_stat.st_size + self.MIN_RESERVE
            if not raw_super.is_file() and shutil.disk_usage(blueprint_root).free < required:
                raise ProjectError(
                    "ROMVERSE needs additional local disk space to inspect the sparse super image"
                )
            if raw_super.exists() and existing is None:
                raw_super.unlink()
            if not raw_super.is_file():
                self._convert_sparse(super_image, raw_super)
        else:
            raw_super = super_image
        metadata = self._dump_metadata(raw_super)
        groups = self._groups(metadata)
        partitions = self._partitions(metadata)
        total_size, used_size = self._super_sizes(metadata)
        if not partitions or not any(item.populated for item in partitions):
            raise ProjectError("The super image contains no populated logical partitions")
        if total_size <= 0 or used_size <= 0 or used_size > total_size:
            raise ProjectError("The super image reported an invalid logical-partition geometry")
        raw_stat = raw_super.stat()
        hash_total = source_stat.st_size + (raw_stat.st_size if raw_super != super_image else 0)
        completed_hash_bytes = 0

        def measured_hash(path: Path) -> str:
            nonlocal completed_hash_bytes
            base = completed_hash_bytes

            def publish_hash(done: int, _total: int) -> None:
                combined = base + done
                if progress is not None and hash_total > 0 and combined < hash_total:
                    progress(max(0, min(99, int(combined * 100 / hash_total))))

            digest = _sha256(path, publish_hash)
            completed_hash_bytes += path.stat().st_size
            return digest

        source_sha = measured_hash(super_image)
        raw_sha = source_sha if raw_super == super_image else measured_hash(raw_super)
        source_after = super_image.stat()
        raw_after = raw_super.stat()
        if (
            source_after.st_size != source_stat.st_size
            or source_after.st_mtime_ns != source_stat.st_mtime_ns
            or raw_after.st_size != raw_stat.st_size
            or raw_after.st_mtime_ns != raw_stat.st_mtime_ns
        ):
            raise ProjectError("The super image changed while ROMVERSE was hashing it")
        identity = identify_firmware_source(project.original.original_name)
        vbmeta_images, avb_verified = self._vbmeta_evidence(super_image.parent)
        plan_payload = {
            "mode": "verified-fastboot-baseline",
            "source_archive_sha256": project.original.sha256,
            "source_super_sha256": source_sha,
            "raw_super_sha256": raw_sha,
            "super_total_size_bytes": total_size,
            "groups": [asdict(item) for item in groups],
            "partitions": [asdict(item) for item in partitions],
            "phone_changed": False,
        }
        plan_digest = _digest(plan_payload)
        payload = {
            "schema_version": 1,
            "blueprint_id": uuid4().hex,
            "project_id": project_id,
            "created_at": datetime.now(UTC).isoformat(),
            "manufacturer": identity.manufacturer,
            "codename": identity.codename,
            "build_id": identity.build_id,
            "android_version": identity.android_version,
            "region": identity.region,
            "source_archive_sha256": project.original.sha256,
            "source_super_path": super_image.relative_to(self.store.workspace).as_posix(),
            "source_super_size_bytes": source_stat.st_size,
            "source_super_modified_ns": source_stat.st_mtime_ns,
            "source_super_sha256": source_sha,
            "raw_super_path": raw_super.relative_to(self.store.workspace).as_posix(),
            "raw_super_size_bytes": raw_stat.st_size,
            "raw_super_modified_ns": raw_stat.st_mtime_ns,
            "raw_super_sha256": raw_sha,
            "super_total_size_bytes": total_size,
            "super_used_size_bytes": used_size,
            "groups": [asdict(item) for item in groups],
            "partitions": [asdict(item) for item in partitions],
            "vbmeta_images": list(vbmeta_images),
            "avb_topology_verified": avb_verified,
            "plan_mode": "verified-fastboot-baseline",
            "plan_digest": plan_digest,
            "authority": "project-local-build-evidence-only",
            "phone_changed": False,
        }
        blueprint_digest = _digest(payload)
        blueprint_values = dict(payload)
        blueprint_values.pop("groups")
        blueprint_values.pop("partitions")
        blueprint_values.pop("vbmeta_images")
        blueprint = FastbootSourceBlueprint(
            **blueprint_values,
            groups=groups,
            partitions=partitions,
            vbmeta_images=vbmeta_images,
            blueprint_digest=blueprint_digest,
        )
        atomic_write_json(
            self.store.projects_root / project_id / self.NAME,
            {"format": "romverse.source-blueprint", **asdict(blueprint)},
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_RECEIPT_BYTES,
        )
        self._report(progress, 100)
        return blueprint

    def load(self, project_id: str) -> FastbootSourceBlueprint | None:
        path = self.store.projects_root / project_id / self.NAME
        try:
            data = read_json_object(
                path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
            if (
                set(data) != {"format", *(field.name for field in fields(FastbootSourceBlueprint))}
                or data.pop("format") != "romverse.source-blueprint"
            ):
                return None
            raw_groups = data.pop("groups")
            raw_partitions = data.pop("partitions")
            raw_vbmeta = data.pop("vbmeta_images")
            if (
                not isinstance(raw_groups, list)
                or not isinstance(raw_partitions, list)
                or not isinstance(raw_vbmeta, list)
                or len(raw_groups) > self.MAX_GROUPS
                or len(raw_partitions) > self.MAX_PARTITIONS
                or len(raw_vbmeta) > self.MAX_VBMETA_IMAGES
            ):
                return None
            groups = tuple(ObservedPartitionGroup(**item) for item in raw_groups)
            partitions = tuple(ObservedLogicalPartition(**item) for item in raw_partitions)
            vbmeta_images = tuple(tuple(item) for item in raw_vbmeta)
            blueprint = FastbootSourceBlueprint(
                **data,
                groups=groups,
                partitions=partitions,
                vbmeta_images=vbmeta_images,
            )
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None
        payload = asdict(blueprint)
        expected_digest = str(payload.pop("blueprint_digest"))
        try:
            project = self.store.get(project_id)
            source = self._workspace_path(blueprint.source_super_path)
            raw = self._workspace_path(blueprint.raw_super_path)
            source_stat = source.stat()
            raw_stat = raw.stat()
        except (OSError, ProjectError):
            return None
        if (
            blueprint.schema_version != 1
            or not _hex_value(blueprint.blueprint_id, 32)
            or not _aware_timestamp(blueprint.created_at)
            or blueprint.project_id != project_id
            or project.original is None
            or blueprint.source_archive_sha256 != project.original.sha256
            or blueprint.authority != "project-local-build-evidence-only"
            or blueprint.phone_changed
            or source_stat.st_size != blueprint.source_super_size_bytes
            or source_stat.st_mtime_ns != blueprint.source_super_modified_ns
            or raw_stat.st_size != blueprint.raw_super_size_bytes
            or raw_stat.st_mtime_ns != blueprint.raw_super_modified_ns
            or _digest(payload) != expected_digest
            or not blueprint.baseline_candidate_ready
            or any(not _valid_group(item) for item in groups)
            or any(not _valid_partition(item) for item in partitions)
            or any(not _valid_vbmeta(item) for item in vbmeta_images)
        ):
            return None
        return blueprint

    def _one_source_super(self, tree: Path) -> Path:
        matches = tuple(
            path.resolve()
            for path in tree.rglob("super.img")
            if path.is_file() and not path.is_symlink()
        )
        if len(matches) != 1 or not matches[0].is_relative_to(tree):
            raise ProjectError(
                "ROMVERSE requires exactly one contained super.img in this fastboot source"
            )
        return matches[0]

    @classmethod
    def _is_sparse(cls, path: Path) -> bool:
        with path.open("rb") as stream:
            header = stream.read(4)
        return len(header) == 4 and struct.unpack("<I", header)[0] == cls.SPARSE_MAGIC

    def _convert_sparse(self, source: Path, output: Path) -> None:
        temporary = output.with_suffix(output.suffix + ".part")
        if temporary.exists():
            temporary.unlink()
        failures = []
        for tool in self._tool_candidates("simg2img", ("simg2img", "/usr/bin/simg2img")):
            result = self.runner.run(
                (str(tool), str(source), str(temporary)),
                timeout=4 * 60 * 60,
                cwd=self.store.workspace,
            )
            if (
                result.ok
                and temporary.is_file()
                and temporary.stat().st_size > source.stat().st_size
            ):
                os.replace(temporary, output)
                return
            failures.append((result.stderr or result.stdout).strip().splitlines()[-1:])
            if temporary.exists():
                temporary.unlink()
        detail = next((item[0] for item in reversed(failures) if item), "tool unavailable")
        raise ProjectError(f"Sparse super conversion failed: {detail[:240]}")

    def _dump_metadata(self, raw_super: Path) -> dict[str, object]:
        failures = []
        for tool in self._tool_candidates("LP Dump", ("lpdumps", "lpdump")):
            result = self.runner.run(
                (str(tool), "-j", str(raw_super)),
                timeout=10 * 60,
                cwd=self.store.workspace,
            )
            if result.ok:
                try:
                    value = json.loads(result.stdout)
                    if isinstance(value, dict) and value.get("partitions"):
                        return value
                except json.JSONDecodeError:
                    pass
            failures.extend((result.stderr or result.stdout).strip().splitlines()[-1:])
        detail = failures[-1] if failures else "LP Dump is unavailable"
        raise ProjectError(f"Logical partition inspection failed: {detail[:240]}")

    def _vbmeta_evidence(self, image_root: Path) -> tuple[tuple[tuple[str, str], ...], bool]:
        images = tuple(
            sorted(
                path
                for path in image_root.glob("vbmeta*.img")
                if path.is_file() and not path.is_symlink()
            )
        )
        evidence = tuple((path.name, _sha256(path)) for path in images)
        tools = self._tool_candidates("AVBTool", ("avbtool",))
        if not images or not tools:
            return evidence, False
        for path in images:
            if not any(
                self.runner.run(
                    (str(tool), "info_image", "--image", str(path)),
                    timeout=60,
                    cwd=self.store.workspace,
                ).ok
                for tool in tools
            ):
                return evidence, False
        return evidence, True

    def _tool_candidates(
        self, status_name: str, fallback_names: tuple[str, ...]
    ) -> tuple[Path, ...]:
        candidates: list[Path] = []
        for status in self.tool_statuses:
            if status.name == status_name and status.available and status.path:
                candidate = Path(status.path).resolve()
                if candidate.is_file() and candidate not in candidates:
                    candidates.append(candidate)
        managed_names = {
            "AVBTool": ("avbtool/avbtool",),
            "simg2img": ("aosp-partition-tools/simg2img",),
            "LP Dump": (
                "aosp-partition-tools/lpdumps",
                "aosp-partition-tools/lpdump",
            ),
        }
        managed_root = self.store.workspace / "tools" / "downloads"
        for relative in managed_names.get(status_name, ()):
            candidate = (managed_root / relative).resolve()
            if candidate.is_file() and candidate not in candidates:
                candidates.append(candidate)
        for name in fallback_names:
            located = Path(name) if name.startswith("/") else None
            if located is None:
                found = shutil.which(name)
                located = Path(found) if found else None
            if located is not None and located.is_file():
                resolved = located.resolve()
                if resolved not in candidates:
                    candidates.append(resolved)
        return tuple(candidates)

    def _workspace_path(self, relative: str) -> Path:
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ProjectError("Source blueprint contains an unsafe path")
        path = (self.store.workspace / candidate).resolve(strict=True)
        if not path.is_relative_to(self.store.workspace.resolve()) or not path.is_file():
            raise ProjectError("Source blueprint path escaped the workspace")
        return path

    @staticmethod
    def _groups(metadata: dict[str, object]) -> tuple[ObservedPartitionGroup, ...]:
        values = []
        for item in metadata.get("groups", ()):
            if isinstance(item, dict) and str(item.get("name", "")):
                values.append(
                    ObservedPartitionGroup(str(item["name"]), int(item.get("maximum_size", 0) or 0))
                )
        return tuple(values)

    @staticmethod
    def _partitions(metadata: dict[str, object]) -> tuple[ObservedLogicalPartition, ...]:
        values = []
        for item in metadata.get("partitions", ()):
            if isinstance(item, dict) and str(item.get("name", "")):
                size = int(item.get("size", 0) or 0)
                values.append(
                    ObservedLogicalPartition(
                        str(item["name"]),
                        str(item.get("group_name", "")),
                        size,
                        size > 0,
                    )
                )
        return tuple(values)

    @staticmethod
    def _super_sizes(metadata: dict[str, object]) -> tuple[int, int]:
        item = metadata.get("super_device", {})
        if not isinstance(item, dict):
            return 0, 0
        return int(item.get("total_size", 0) or 0), int(item.get("used_size", 0) or 0)

    @staticmethod
    def _report(progress: ProgressCallback | None, value: int) -> None:
        if progress is not None:
            progress(value)


def _sha256(
    path: Path,
    progress: Callable[[int, int], None] | None = None,
) -> str:
    digest = hashlib.sha256()
    total = path.stat().st_size
    read = 0
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
            read += len(chunk)
            if progress is not None:
                progress(read, total)
    return digest.hexdigest()


def _digest(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _valid_group(item: ObservedPartitionGroup) -> bool:
    return bool(
        re.fullmatch(r"[A-Za-z0-9._-]{1,80}", item.name)
        and type(item.maximum_size_bytes) is int
        and item.maximum_size_bytes >= 0
    )


def _valid_partition(item: ObservedLogicalPartition) -> bool:
    return bool(
        re.fullmatch(r"[A-Za-z0-9._-]{1,80}", item.name)
        and re.fullmatch(r"[A-Za-z0-9._-]{0,80}", item.group_name)
        and type(item.size_bytes) is int
        and item.size_bytes >= 0
        and type(item.populated) is bool
    )


def _valid_vbmeta(item: tuple[object, ...]) -> bool:
    return bool(
        len(item) == 2
        and isinstance(item[0], str)
        and re.fullmatch(r"vbmeta[A-Za-z0-9._-]*\.img", item[0])
        and _hex_value(item[1], 64)
    )


def _hex_value(value: object, length: int) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(rf"[0-9a-f]{{{length}}}", value))


def _aware_timestamp(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 80:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed <= datetime.now(UTC) + timedelta(minutes=5)
