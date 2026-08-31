from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from romverse.infrastructure.process import CommandRunner
from romverse.rom.models import ProjectError
from romverse.rom.payloads import PayloadService
from romverse.rom.projects import RomProjectStore


@dataclass(frozen=True, slots=True)
class FilesystemExpansionPlan:
    partition: str
    image_format: str
    image_bytes: int
    required_free_bytes: int
    available_bytes: int
    safe: bool
    reason: str


@dataclass(frozen=True, slots=True)
class FilesystemManifest:
    schema_version: int
    project_id: str
    partition: str
    created_at: str
    source_image_path: str
    source_sha256: str
    image_format: str
    tree_path: str
    file_count: int
    directory_count: int
    symlink_count: int
    unsafe_symlink_count: int
    content_bytes: int
    tool: str
    fakeroot_state_path: str = ""
    metadata_hashes: tuple[tuple[str, str], ...] = ()


class PartitionFilesystemService:
    MANIFEST_ROOT = "filesystems"
    MIN_RESERVE = 4 * 1024 * 1024 * 1024
    MAX_FILES = 1_000_000
    MAX_CONTENT_BYTES = 256 * 1024 * 1024 * 1024
    MAX_FAKEROOT_STATE_BYTES = 32 * 1024 * 1024
    SUPER_UNPACK_NAME = "super-unpack.romverse"

    def __init__(
        self,
        store: RomProjectStore,
        payloads: PayloadService | None,
        runner: CommandRunner,
        simg2img: Path | None = None,
        debugfs: Path | None = None,
        erofs: Path | None = None,
        fakeroot: Path | None = None,
        lpunpack: Path | None = None,
    ) -> None:
        self.store = store
        self.payloads = payloads
        self.runner = runner
        self.simg2img = simg2img.resolve() if simg2img else None
        self.debugfs = debugfs.resolve() if debugfs else None
        self.erofs = erofs.resolve() if erofs else None
        self.fakeroot = fakeroot.resolve() if fakeroot else None
        self.lpunpack = lpunpack.resolve() if lpunpack else None

    def available_partitions(self, project_id: str) -> tuple[str, ...]:
        """List contained partition images from payload and fastboot source layouts."""

        names: set[str] = set()
        manifest = self.payloads.load(project_id) if self.payloads is not None else None
        if manifest is not None:
            names.update(
                item.name for item in manifest.partitions if item.category == "Android filesystem"
            )
        project_root = (self.store.working_root / project_id).resolve()
        if project_root.is_dir():
            for image in project_root.rglob("*.img"):
                if image.is_symlink() or not image.is_file():
                    continue
                resolved = image.resolve()
                if not resolved.is_relative_to(project_root):
                    continue
                partition = image.stem.removesuffix("_a").removesuffix("_b")
                if PayloadService.PARTITION_PATTERN.fullmatch(partition):
                    names.add(partition)
        return tuple(sorted(names))

    def unpack_super(
        self,
        project_id: str,
        allowed_partitions: frozenset[str],
        progress: Callable[[int, int], None] | None = None,
    ) -> tuple[str, ...]:
        """Materialize slot-A logical images from one contained super image."""

        project = self.store.get(project_id)
        if project.original is None or not self.store.verify_original(project_id).valid:
            raise ProjectError("Protected firmware integrity must pass before unpacking super.img")
        if self.lpunpack is None or not self.lpunpack.is_file():
            raise ProjectError("LP Unpack is unavailable; verify it in Forge Arsenal and retry")
        tree = (self.store.working_root / project_id / "tree").resolve()
        matches = tuple(
            path.resolve()
            for path in tree.rglob("super.img")
            if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(tree)
        )
        if len(matches) != 1:
            raise ProjectError(
                "Fastboot filesystem discovery requires exactly one contained super.img"
            )
        source = matches[0]
        required = source.stat().st_size * 2 + self.MIN_RESERVE
        free = shutil.disk_usage(self.store.workspace).free
        if free < required:
            raise ProjectError(
                f"Logical partition extraction requires {_byte_label(required)} free; "
                f"{_byte_label(free)} is available"
            )
        project_root = self.store.working_root / project_id
        staging = project_root / f".super-unpack-{uuid4().hex}.part"
        unpacked = staging / "unpacked"
        staging.mkdir()
        unpacked.mkdir()
        normalized = source
        created: list[Path] = []
        try:
            if _image_format(source) == "Android sparse image":
                if self.simg2img is None or not self.simg2img.is_file():
                    raise ProjectError("simg2img is required to normalize this sparse super image")
                normalized = staging / "super.raw.img"
                result = self.runner.run(
                    (str(self.simg2img), str(source), str(normalized)),
                    timeout=4 * 60 * 60,
                    cwd=self.store.workspace,
                )
                if not result.ok or not normalized.is_file():
                    raise ProjectError("Sparse super normalization failed")
            result = self.runner.run(
                (str(self.lpunpack), str(normalized), str(unpacked)),
                timeout=4 * 60 * 60,
                cwd=self.store.workspace,
            )
            if not result.ok:
                detail = (result.stderr or result.stdout).strip().splitlines()
                raise ProjectError(
                    "Logical partition extraction failed"
                    + (f": {detail[-1][:240]}" if detail else "")
                )
            output_root = project_root / "partitions"
            output_root.mkdir(parents=True, exist_ok=True)
            selections = []
            for partition in sorted(allowed_partitions):
                candidates = tuple(
                    path
                    for name in (f"{partition}.img", f"{partition}_a.img")
                    if (path := unpacked / name).is_file() and not path.is_symlink()
                )
                if not candidates:
                    continue
                selected = candidates[0]
                if not selected.resolve().is_relative_to(unpacked.resolve()):
                    raise ProjectError("LP Unpack output escaped contained staging")
                target = output_root / f"{partition}.img"
                if target.exists():
                    raise ProjectError(
                        f"Refusing to overwrite existing source-bound {partition}.img"
                    )
                selections.append((partition, selected, target, selected.stat().st_size))
            if not selections:
                raise ProjectError("LP Unpack produced no supported Android filesystem partitions")

            verification_total = sum(item[3] for item in selections)
            verified_bytes = 0
            records = []
            for partition, selected, target, selected_bytes in selections:
                os.replace(selected, target)
                created.append(target)

                def publish_partition_hash(
                    done: int,
                    _total: int,
                    *,
                    offset: int = verified_bytes,
                ) -> None:
                    combined = offset + done
                    if (
                        progress is not None
                        and verification_total > 0
                        and combined < verification_total
                    ):
                        progress(combined, verification_total)

                records.append(
                    {
                        "partition": partition,
                        "path": target.relative_to(self.store.workspace).as_posix(),
                        "size_bytes": target.stat().st_size,
                        "sha256": _sha256(target, publish_partition_hash),
                    }
                )
                verified_bytes += selected_bytes
            if not self.store.verify_original(project_id).valid:
                raise ProjectError("Protected firmware integrity changed during super extraction")
            _atomic_json(
                self.store.projects_root / project_id / self.MANIFEST_ROOT / self.SUPER_UNPACK_NAME,
                {
                    "format": "romverse.super-unpack",
                    "schema_version": 1,
                    "project_id": project_id,
                    "source_path": source.relative_to(self.store.workspace).as_posix(),
                    "source_sha256": _sha256(source),
                    "tool_path": str(self.lpunpack),
                    "partitions": records,
                    "phone_changed": False,
                },
            )
            if progress is not None:
                terminal = verification_total or 1
                progress(terminal, terminal)
            return tuple(str(item["partition"]) for item in records)
        except Exception:
            for target in created:
                target.unlink(missing_ok=True)
            raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def plan(self, project_id: str, partition: str) -> FilesystemExpansionPlan:
        part, image = self._partition_image(project_id, partition)
        image_format = _image_format(image)
        sparse_overhead = image.stat().st_size if image_format == "Android sparse image" else 0
        required = image.stat().st_size + sparse_overhead + self.MIN_RESERVE
        free = shutil.disk_usage(self.store.workspace).free
        tool_available = self._tool_for(image_format) is not None
        supported = image_format in {
            "Android sparse image",
            "ext4 filesystem",
            "EROFS filesystem",
        }
        safe = supported and tool_available and free >= required and not part.critical
        if part.critical:
            reason = "Critical boot-chain or radio partitions are not filesystem Recipe targets"
        elif not supported:
            reason = f"{image_format} is not a supported browsable filesystem image"
        elif not tool_available:
            reason = f"Required read-only extractor is unavailable for {image_format}"
        elif free < required:
            reason = (
                f"Filesystem expansion requires {_byte_label(required)} free; "
                f"{_byte_label(free)} is available"
            )
        else:
            reason = (
                f"Filesystem expansion budget verified: {_byte_label(image.stat().st_size)} image, "
                f"{_byte_label(free)} free"
            )
        return FilesystemExpansionPlan(
            partition,
            image_format,
            image.stat().st_size,
            required,
            free,
            safe,
            reason,
        )

    def expand(self, project_id: str, partition: str) -> FilesystemManifest:
        plan = self.plan(project_id, partition)
        if not plan.safe:
            raise ProjectError(plan.reason)
        _part, source = self._partition_image(project_id, partition)
        source_sha256 = _sha256(source)
        partition_root = self.store.working_root / project_id / "tree" / "partition_files"
        destination = partition_root / partition
        if destination.exists():
            raise ProjectError(
                f"{partition} filesystem is already expanded; restore or remove it before repeating"
            )
        partition_root.mkdir(parents=True, exist_ok=True)
        staging = partition_root / f".{partition}-{uuid4().hex}.part"
        staging.mkdir()
        tree = staging / "root"
        tree.mkdir()
        normalized = source
        tool_name = ""
        try:
            image_format = plan.image_format
            if image_format == "Android sparse image":
                if self.simg2img is None:
                    raise ProjectError("simg2img is unavailable")
                normalized = staging / "normalized.img"
                result = self.runner.run(
                    (str(self.simg2img), str(source), str(normalized)),
                    timeout=2 * 60 * 60,
                )
                if not result.ok or not normalized.is_file():
                    raise ProjectError("Sparse image conversion failed")
                image_format = _image_format(normalized)
                if image_format not in {"ext4 filesystem", "EROFS filesystem"}:
                    raise ProjectError(
                        "Converted sparse image is not a supported ext4 or EROFS filesystem"
                    )
            if image_format == "ext4 filesystem":
                if self.debugfs is None:
                    raise ProjectError("debugfs is unavailable")
                result = self.runner.run(
                    (str(self.debugfs), "-R", "rdump / root", str(normalized)),
                    timeout=2 * 60 * 60,
                    cwd=staging,
                )
                tool_name = "debugfs"
            elif image_format == "EROFS filesystem":
                if self.erofs is None or self.fakeroot is None:
                    raise ProjectError("EROFS extractor and fakeroot are required")
                fakeroot_state = staging / "fakeroot.state"
                result = self.runner.run(
                    (
                        str(self.fakeroot),
                        "-s",
                        str(fakeroot_state),
                        "--",
                        str(self.erofs),
                        "--extract=root",
                        "--preserve",
                        "--xattrs",
                        str(normalized),
                    ),
                    timeout=2 * 60 * 60,
                    cwd=staging,
                )
                tool_name = "fsck.erofs"
            else:
                raise ProjectError(f"Unsupported filesystem image: {image_format}")
            if not result.ok:
                detail = (result.stderr or result.stdout).strip().splitlines()
                raise ProjectError(
                    f"{partition} filesystem extraction failed"
                    + (f": {detail[-1][:240]}" if detail else "")
                )
            fakeroot_relative = ""
            if image_format == "EROFS filesystem":
                fakeroot_state = staging / "fakeroot.state"
                if (
                    not fakeroot_state.is_file()
                    or fakeroot_state.is_symlink()
                    or fakeroot_state.stat().st_size > self.MAX_FAKEROOT_STATE_BYTES
                ):
                    raise ProjectError("EROFS ownership metadata was not preserved safely")
                fakeroot_relative = (
                    (destination / fakeroot_state.name).relative_to(self.store.workspace).as_posix()
                )
            counts = self._summarize_tree(tree)
            metadata_hashes = self._metadata_hashes(tree)
            if normalized != source:
                normalized.unlink(missing_ok=True)
            os.replace(staging, destination)
            final_tree = destination / "root"
            manifest = FilesystemManifest(
                2,
                project_id,
                partition,
                datetime.now(UTC).isoformat(),
                source.relative_to(self.store.workspace).as_posix(),
                source_sha256,
                image_format,
                final_tree.relative_to(self.store.workspace).as_posix(),
                counts[0],
                counts[1],
                counts[2],
                counts[3],
                counts[4],
                tool_name,
                fakeroot_relative,
                metadata_hashes,
            )
            self._save(manifest)
            return manifest
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    def load(self, project_id: str, partition: str) -> FilesystemManifest | None:
        path = self._manifest_path(project_id, partition)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.pop("format") != "romverse.filesystem-manifest":
                return None
            data.setdefault("fakeroot_state_path", "")
            data["metadata_hashes"] = tuple(
                tuple(map(str, item)) for item in data.get("metadata_hashes", ())
            )
            manifest = FilesystemManifest(**data)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None
        tree = (self.store.workspace / manifest.tree_path).resolve()
        root = (self.store.working_root / project_id / "tree" / "partition_files").resolve()
        if (
            manifest.schema_version not in {1, 2}
            or manifest.project_id != project_id
            or manifest.partition != partition
            or not tree.is_relative_to(root)
            or not tree.is_dir()
        ):
            return None
        if manifest.schema_version == 2 and manifest.image_format == "EROFS filesystem":
            try:
                fakeroot_state = (self.store.workspace / manifest.fakeroot_state_path).resolve(
                    strict=True
                )
                if (
                    not fakeroot_state.is_relative_to(root)
                    or not fakeroot_state.is_file()
                    or fakeroot_state.is_symlink()
                    or fakeroot_state.stat().st_size > self.MAX_FAKEROOT_STATE_BYTES
                ):
                    return None
            except OSError:
                return None
        for relative, expected in manifest.metadata_hashes:
            try:
                unresolved = tree / relative
                if unresolved.is_symlink():
                    return None
                candidate = unresolved.resolve(strict=True)
                if (
                    not candidate.is_relative_to(tree)
                    or not candidate.is_file()
                    or _sha256(candidate) != expected
                ):
                    return None
            except OSError:
                return None
        return manifest

    def list_manifests(self, project_id: str) -> tuple[FilesystemManifest, ...]:
        root = self.store.projects_root / project_id / self.MANIFEST_ROOT
        manifests = []
        for path in root.glob("*.romverse") if root.is_dir() else ():
            manifest = self.load(project_id, path.stem)
            if manifest is not None:
                manifests.append(manifest)
        return tuple(sorted(manifests, key=lambda item: item.partition))

    def _partition_image(self, project_id: str, partition: str):
        if not PayloadService.PARTITION_PATTERN.fullmatch(partition):
            raise ProjectError("Invalid partition name")
        manifest = self.payloads.load(project_id) if self.payloads is not None else None
        if manifest is not None:
            part = next((item for item in manifest.partitions if item.name == partition), None)
            if part is not None:
                if not part.extracted_path:
                    raise ProjectError(f"Extract {partition}.img before opening its filesystem")
                image = (self.store.workspace / part.extracted_path).resolve()
                partition_root = (self.store.working_root / project_id / "partitions").resolve()
                if (
                    not image.is_relative_to(partition_root)
                    or not image.is_file()
                    or image.is_symlink()
                ):
                    raise ProjectError(
                        "Extracted partition image is missing or outside the workspace"
                    )
                return part, image

        project_root = (self.store.working_root / project_id).resolve()
        matches = tuple(
            path.resolve()
            for pattern in (f"{partition}.img", f"{partition}_a.img", f"{partition}_b.img")
            for path in project_root.rglob(pattern)
            if path.is_file()
            and not path.is_symlink()
            and path.resolve().is_relative_to(project_root)
            and "partition_files" not in path.relative_to(project_root).parts
        )
        unique = tuple(dict.fromkeys(matches))
        if not unique:
            raise ProjectError(
                f"No contained {partition}.img was found; extract the payload or logical super partition first"
            )
        unslotted = tuple(path for path in unique if path.name == f"{partition}.img")
        selected = unslotted or tuple(path for path in unique if path.name == f"{partition}_a.img")
        if len(selected) != 1:
            raise ProjectError(
                f"Multiple contained {partition} images were found; the filesystem source is ambiguous"
            )

        @dataclass(frozen=True, slots=True)
        class DirectPartition:
            name: str
            critical: bool = False

        return DirectPartition(partition), selected[0]

    def _tool_for(self, image_format: str) -> Path | None:
        if image_format == "Android sparse image":
            return self.simg2img if self.simg2img and self.simg2img.is_file() else None
        if image_format == "ext4 filesystem":
            return self.debugfs if self.debugfs and self.debugfs.is_file() else None
        if image_format == "EROFS filesystem":
            if self.erofs and self.erofs.is_file() and self.fakeroot and self.fakeroot.is_file():
                return self.erofs
            return None
        return None

    def _save(self, manifest: FilesystemManifest) -> None:
        path = self._manifest_path(manifest.project_id, manifest.partition)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"format": "romverse.filesystem-manifest", **asdict(manifest)}, indent=2)
            + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)

    def _manifest_path(self, project_id: str, partition: str) -> Path:
        return self.store.projects_root / project_id / self.MANIFEST_ROOT / f"{partition}.romverse"

    @classmethod
    def _summarize_tree(cls, root: Path) -> tuple[int, int, int, int, int]:
        files = directories = symlinks = unsafe_links = content = 0
        resolved_root = root.resolve()
        for path in root.rglob("*"):
            if path.is_symlink():
                symlinks += 1
                if not path.resolve(strict=False).is_relative_to(resolved_root):
                    unsafe_links += 1
                continue
            if path.is_dir():
                directories += 1
                continue
            if path.is_file():
                files += 1
                content += path.stat().st_size
            if files + directories + symlinks > cls.MAX_FILES:
                raise ProjectError("Expanded filesystem exceeds the safe entry limit")
            if content > cls.MAX_CONTENT_BYTES:
                raise ProjectError("Expanded filesystem exceeds the safe content-size limit")
        return files, directories, symlinks, unsafe_links, content

    @classmethod
    def _metadata_hashes(cls, root: Path) -> tuple[tuple[str, str], ...]:
        records = []
        for path in sorted(root.rglob("*file_contexts")):
            if path.is_symlink() or not path.is_file():
                continue
            if path.stat().st_size > cls.MAX_FAKEROOT_STATE_BYTES:
                raise ProjectError("Filesystem metadata file exceeds the safe size limit")
            records.append((path.relative_to(root).as_posix(), _sha256(path)))
            if len(records) > 64:
                raise ProjectError("Filesystem contains too many file-context metadata files")
        return tuple(records)


def _sha256(
    path: Path,
    progress: Callable[[int, int], None] | None = None,
) -> str:
    digest = hashlib.sha256()
    total = path.stat().st_size
    read = 0
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            digest.update(chunk)
            read += len(chunk)
            if progress is not None:
                progress(read, total)
    return digest.hexdigest()


def _image_format(path: Path) -> str:
    with path.open("rb") as stream:
        header = stream.read(4096)
    if len(header) >= 4 and struct.unpack_from("<I", header)[0] == 0xED26FF3A:
        return "Android sparse image"
    if len(header) >= 1082 and header[1080:1082] == b"\x53\xef":
        return "ext4 filesystem"
    if len(header) >= 1028 and struct.unpack_from("<I", header, 1024)[0] == 0xE0F5E1E2:
        return "EROFS filesystem"
    return "raw partition image"


def _byte_label(value: int) -> str:
    size = float(max(0, value))
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
