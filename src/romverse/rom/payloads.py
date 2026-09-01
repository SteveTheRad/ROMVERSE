from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import struct
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, fields, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from romverse.infrastructure.local_store import atomic_write_json, read_json_object
from romverse.infrastructure.process import CommandRunner
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore

ProgressCallback = Callable[[int, int], None]


@dataclass(frozen=True, slots=True)
class PayloadPartition:
    name: str
    estimated_bytes: int
    category: str
    recommended: bool
    critical: bool
    extracted_path: str = ""
    actual_bytes: int = 0
    sha256: str = ""
    image_format: str = "unknown"


@dataclass(frozen=True, slots=True)
class PayloadManifest:
    schema_version: int
    project_id: str
    generated_at: str
    source_original_sha256: str
    payload_path: str
    payload_size: int
    payload_sha256: str
    tool_path: str
    partitions: tuple[PayloadPartition, ...]
    payload_modified_ns: int = 0
    tool_sha256: str = ""
    record_digest: str = ""


@dataclass(frozen=True, slots=True)
class PartitionExtractionPlan:
    selected: tuple[str, ...]
    expected_bytes: int
    free_bytes: int
    reserve_bytes: int
    safe: bool
    reason: str


class PayloadService:
    MANIFEST_NAME = "payload-manifest.romverse"
    SCHEMA_VERSION = 2
    MAX_MANIFEST_BYTES = 512 * 1024
    MAX_PARTITIONS = 256
    MAX_PARTITION_BYTES = 128 * 1024 * 1024 * 1024
    MAX_TOTAL_BYTES = 256 * 1024 * 1024 * 1024
    MIN_RESERVE = 4 * 1024 * 1024 * 1024
    PARTITION_PATTERN = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}")
    RECOMMENDED = frozenset(
        {
            "boot",
            "init_boot",
            "vendor_boot",
            "dtbo",
            "vbmeta",
            "vbmeta_system",
            "system",
            "system_ext",
            "product",
            "vendor",
            "odm",
            "system_dlkm",
            "vendor_dlkm",
            "mi_ext",
            "mi_product",
        }
    )
    CRITICAL = frozenset(
        {
            "abl",
            "xbl",
            "xbl_config",
            "devcfg",
            "hyp",
            "tz",
            "keymaster",
            "uefi",
            "uefisecapp",
            "modem",
            "modemfirmware",
            "aop",
            "dsp",
        }
    )

    def __init__(
        self,
        store: RomProjectStore,
        executable: Path,
        runner: CommandRunner,
    ) -> None:
        self.store = store
        self.executable = executable.expanduser().resolve()
        self.runner = runner

    def scan(
        self,
        project_id: str,
        progress: ProgressCallback | None = None,
    ) -> PayloadManifest:
        project = self.store.get(project_id)
        if project.original is None:
            raise ProjectError("Import a protected original before scanning an OTA payload")
        payload = self.payload_path(project_id)
        if not self.executable.is_file():
            raise ProjectError("Payload Dumper is unavailable; install it through Forge Arsenal")
        payload_before = payload.stat()
        digest = _sha256(payload)
        payload_after = payload.stat()
        if (
            payload_after.st_size != payload_before.st_size
            or payload_after.st_mtime_ns != payload_before.st_mtime_ns
        ):
            raise ProjectError("payload.bin changed while ROMVERSE was hashing it")
        tool_before = self.executable.stat()
        tool_sha256 = _sha256(self.executable)
        tool_after = self.executable.stat()
        if (
            tool_after.st_size != tool_before.st_size
            or tool_after.st_mtime_ns != tool_before.st_mtime_ns
        ):
            raise ProjectError("Payload Dumper changed while ROMVERSE was verifying it")
        result = self.runner.run(
            (str(self.executable), "-l", "-m", str(payload)),
            timeout=120,
        )
        if not result.ok:
            detail = (result.stderr or result.stdout).strip().splitlines()
            raise ProjectError(
                "Payload partition scan failed" + (f": {detail[-1][:240]}" if detail else "")
            )
        final_payload_stat = payload.stat()
        if (
            final_payload_stat.st_size != payload_after.st_size
            or final_payload_stat.st_mtime_ns != payload_after.st_mtime_ns
            or not self.executable.is_file()
            or _sha256(self.executable) != tool_sha256
        ):
            raise ProjectError(
                "Payload source or verified dumper changed during the partition scan"
            )
        partitions = self.parse_partition_list(result.stdout)
        manifest = _seal_manifest(
            PayloadManifest(
                self.SCHEMA_VERSION,
                project_id,
                datetime.now(UTC).isoformat(),
                project.original.sha256,
                payload.relative_to(self.store.workspace).as_posix(),
                payload_after.st_size,
                digest,
                str(self.executable),
                partitions,
                payload_after.st_mtime_ns,
                tool_sha256,
                "",
            )
        )
        self._save(manifest)
        if progress is not None:
            progress(payload_after.st_size, payload_after.st_size)
        return manifest

    def payload_path(self, project_id: str) -> Path:
        unresolved_root = self.store.working_root / project_id / "tree"
        if unresolved_root.is_symlink():
            raise ProjectError("The OTA working tree cannot be a symbolic link")
        root = unresolved_root.resolve()
        if not root.is_dir():
            raise ProjectError("Extract the OTA archive before scanning payload.bin")
        matches = tuple(
            path.resolve()
            for path in root.rglob("*")
            if path.name.casefold() == "payload.bin"
            and path.is_file()
            and not path.is_symlink()
            and path.resolve().is_relative_to(root)
        )
        if not matches:
            raise ProjectError("Extract the OTA archive before scanning payload.bin")
        if len(matches) != 1:
            raise ProjectError("Multiple payload.bin files were found; source is ambiguous")
        return matches[0]

    @classmethod
    def parse_partition_list(cls, output: str) -> tuple[PayloadPartition, ...]:
        partitions: list[PayloadPartition] = []
        names: set[str] = set()
        for raw_line in output.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            name, separator, size_text = line.partition(":")
            name = name.strip().casefold()
            if not separator or not cls.PARTITION_PATTERN.fullmatch(name) or name in names:
                raise ProjectError("Payload Dumper returned an invalid partition list")
            try:
                # payload-dumper-go machine output reports partition sizes in KiB.
                estimated = int(size_text.strip()) * 1024
            except ValueError as exc:
                raise ProjectError("Payload Dumper returned an invalid partition size") from exc
            if estimated < 0 or estimated > cls.MAX_PARTITION_BYTES:
                raise ProjectError(f"Payload partition size is unsafe: {name}")
            names.add(name)
            partitions.append(
                PayloadPartition(
                    name,
                    estimated,
                    _category(name),
                    name in cls.RECOMMENDED,
                    name in cls.CRITICAL,
                )
            )
            if len(partitions) > cls.MAX_PARTITIONS:
                raise ProjectError("Payload exceeds the safe partition-count limit")
        if not partitions:
            raise ProjectError("Payload contains no readable partition manifest")
        if sum(item.estimated_bytes for item in partitions) > cls.MAX_TOTAL_BYTES:
            raise ProjectError("Payload declares an unsafe total partition size")
        return tuple(partitions)

    def plan_extraction(
        self,
        project_id: str,
        selected: Sequence[str] | None = None,
    ) -> PartitionExtractionPlan:
        manifest = self.load(project_id)
        if manifest is None:
            raise ProjectError("Scan payload.bin before planning partition extraction")
        known = {item.name: item for item in manifest.partitions}
        requested = tuple(dict.fromkeys(selected or ()))
        if not requested:
            requested = tuple(item.name for item in manifest.partitions if item.recommended)
        if not requested:
            raise ProjectError("Select at least one partition to extract")
        if any(name not in known for name in requested):
            raise ProjectError("Partition selection does not match the scanned payload")
        expected = sum(known[name].estimated_bytes for name in requested)
        reserve = max(self.MIN_RESERVE, expected // 10)
        free = shutil.disk_usage(self.store.workspace).free
        safe = expected <= self.MAX_TOTAL_BYTES and free >= expected + reserve
        reason = (
            f"Partition extraction budget verified: {_byte_label(expected)} selected, "
            f"{_byte_label(free)} free, {_byte_label(reserve)} retained as reserve"
            if safe
            else f"Partition extraction requires {_byte_label(expected + reserve)} free; "
            f"{_byte_label(free)} is available"
        )
        return PartitionExtractionPlan(requested, expected, free, reserve, safe, reason)

    def extract(
        self,
        project_id: str,
        selected: Sequence[str] | None = None,
        progress: ProgressCallback | None = None,
    ) -> PayloadManifest:
        manifest = self.load(project_id)
        if manifest is None:
            raise ProjectError("Scan payload.bin before extracting partitions")
        legacy_upgrade = manifest.schema_version != self.SCHEMA_VERSION
        if legacy_upgrade:
            manifest = self.scan(project_id)
        project = self.store.get(project_id)
        if project.original is None or project.original.sha256 != manifest.source_original_sha256:
            raise ProjectError("Payload manifest no longer matches the protected original")
        payload = self.payload_path(project_id)
        payload_stat = payload.stat()
        if (
            payload.relative_to(self.store.workspace).as_posix() != manifest.payload_path
            or payload_stat.st_size != manifest.payload_size
            or payload_stat.st_mtime_ns != manifest.payload_modified_ns
        ):
            raise ProjectError("payload.bin identity changed after inspection; rescan is required")
        payload_sha256 = _sha256(payload)
        if payload_sha256 != manifest.payload_sha256:
            raise ProjectError("payload.bin SHA-256 changed after inspection; rescan is required")
        if (
            str(self.executable) != manifest.tool_path
            or not self.executable.is_file()
            or _sha256(self.executable) != manifest.tool_sha256
        ):
            raise ProjectError(
                "Payload Dumper identity changed after inspection; reverify the tool and rescan"
            )
        plan = self.plan_extraction(project_id, selected)
        if not plan.safe:
            raise ProjectError(plan.reason)
        destination = self.store.working_root / project_id / "partitions"
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = destination.parent / f".partitions-{uuid4().hex}.part"
        staging.mkdir(parents=False, exist_ok=False)
        try:
            result = self.runner.run(
                (
                    str(self.executable),
                    "-m",
                    "-o",
                    str(staging),
                    "-p",
                    ",".join(plan.selected),
                    str(payload),
                ),
                timeout=4 * 60 * 60,
            )
            if not result.ok:
                detail = (result.stderr or result.stdout).strip().splitlines()
                raise ProjectError(
                    "Payload extraction failed" + (f": {detail[-1][:240]}" if detail else "")
                )
            final_payload_stat = payload.stat()
            if (
                final_payload_stat.st_size != payload_stat.st_size
                or final_payload_stat.st_mtime_ns != payload_stat.st_mtime_ns
                or not self.executable.is_file()
                or _sha256(self.executable) != manifest.tool_sha256
            ):
                raise ProjectError(
                    "Payload source or verified dumper changed during extraction; outputs were discarded"
                )
            produced = self._verify_outputs(staging, plan.selected)
            destination.mkdir(parents=True, exist_ok=True)
            updated = {item.name: item for item in manifest.partitions}
            existing_targets: dict[str, Path] = {}
            verification_total = sum(source.stat().st_size for source in produced.values())
            for name, source in produced.items():
                target = destination / source.name
                if target.exists():
                    if target.is_symlink() or not target.is_file():
                        raise ProjectError(
                            f"Existing extracted partition is not a regular contained file: {name}"
                        )
                    existing_targets[name] = target
                    verification_total += target.stat().st_size
            verified_bytes = 0
            if progress is not None and verification_total:
                progress(0, verification_total)
            for name, source in produced.items():
                target = destination / source.name
                source_size = source.stat().st_size

                def publish_source(done: int, _size: int, offset: int = verified_bytes) -> None:
                    current = offset + done
                    if progress is not None and current < verification_total:
                        progress(current, verification_total)

                digest = _sha256(
                    source,
                    publish_source,
                )
                verified_bytes += source_size
                if existing := existing_targets.get(name):
                    existing_size = existing.stat().st_size

                    def publish_existing(
                        done: int,
                        _size: int,
                        offset: int = verified_bytes,
                    ) -> None:
                        current = offset + done
                        if progress is not None and current < verification_total:
                            progress(current, verification_total)

                    if _sha256(existing, publish_existing) != digest:
                        raise ProjectError(
                            f"Existing extracted partition differs; remove or restore it first: {name}"
                        )
                    verified_bytes += existing_size
                    source.unlink()
                else:
                    os.replace(source, target)
                updated[name] = replace(
                    updated[name],
                    extracted_path=target.relative_to(self.store.workspace).as_posix(),
                    actual_bytes=target.stat().st_size,
                    sha256=digest,
                    image_format=_image_format(target),
                )
            manifest = _seal_manifest(
                replace(
                    manifest,
                    generated_at=datetime.now(UTC).isoformat(),
                    partitions=tuple(updated[item.name] for item in manifest.partitions),
                    record_digest="",
                )
            )
            self._save(manifest)
            if progress is not None:
                terminal = verification_total or 1
                progress(terminal, terminal)
            return manifest
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def load(self, project_id: str) -> PayloadManifest | None:
        path = self.store.projects_root / project_id / self.MANIFEST_NAME
        try:
            data = read_json_object(
                path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_MANIFEST_BYTES,
            )
            schema_version = data.get("schema_version")
            expected = {
                "format",
                "schema_version",
                "project_id",
                "generated_at",
                "source_original_sha256",
                "payload_path",
                "payload_size",
                "payload_sha256",
                "tool_path",
                "partitions",
            }
            if schema_version == self.SCHEMA_VERSION:
                expected.update({"payload_modified_ns", "tool_sha256", "record_digest"})
            elif schema_version != 1:
                return None
            if set(data) != expected or data.pop("format") != "romverse.payload-manifest":
                return None
            raw_partitions = data.pop("partitions")
            if (
                not isinstance(raw_partitions, list)
                or not 1 <= len(raw_partitions) <= self.MAX_PARTITIONS
            ):
                return None
            partitions = tuple(_parse_partition(item) for item in raw_partitions)
            if any(not _valid_partition_shape(item) for item in partitions):
                return None
            manifest = PayloadManifest(
                data["schema_version"],
                data["project_id"],
                data["generated_at"],
                data["source_original_sha256"],
                data["payload_path"],
                data["payload_size"],
                data["payload_sha256"],
                data["tool_path"],
                partitions,
                data.get("payload_modified_ns", 0),
                data.get("tool_sha256", ""),
                data.get("record_digest", ""),
            )
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None
        try:
            project = self.store.get(project_id)
            payload = self.payload_path(project_id)
            payload_stat = payload.stat()
        except (OSError, ProjectError):
            return None
        if (
            not _valid_manifest_shape(manifest)
            or manifest.project_id != project_id
            or project.original is None
            or manifest.source_original_sha256 != project.original.sha256
            or payload.relative_to(self.store.workspace).as_posix() != manifest.payload_path
            or payload_stat.st_size != manifest.payload_size
            or (
                manifest.schema_version == self.SCHEMA_VERSION
                and (
                    payload_stat.st_mtime_ns != manifest.payload_modified_ns
                    or manifest.record_digest != _manifest_digest(manifest)
                )
            )
            or any(
                not self._valid_extracted_partition(project_id, item)
                for item in manifest.partitions
            )
        ):
            return None
        return manifest

    def _save(self, manifest: PayloadManifest) -> None:
        path = self.store.projects_root / manifest.project_id / self.MANIFEST_NAME
        if manifest.schema_version != self.SCHEMA_VERSION:
            raise ProjectError("Only current payload evidence can be saved")
        sealed = manifest if manifest.record_digest else _seal_manifest(manifest)
        if sealed.record_digest != _manifest_digest(sealed):
            raise ProjectError("Payload manifest digest does not match its evidence")
        atomic_write_json(
            path,
            {"format": "romverse.payload-manifest", **asdict(sealed)},
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_MANIFEST_BYTES,
        )

    def _valid_extracted_partition(
        self,
        project_id: str,
        item: PayloadPartition,
    ) -> bool:
        if not item.extracted_path:
            return item.actual_bytes == 0 and not item.sha256 and item.image_format == "unknown"
        try:
            relative = Path(item.extracted_path)
            if relative.is_absolute() or ".." in relative.parts:
                return False
            unresolved_target = self.store.workspace / relative
            unresolved_root = self.store.working_root / project_id / "partitions"
            if unresolved_target.is_symlink() or unresolved_root.is_symlink():
                return False
            target = unresolved_target.resolve(strict=True)
            root = unresolved_root.resolve(strict=True)
            details = target.stat()
        except OSError:
            return False
        return bool(
            target.is_file()
            and not target.is_symlink()
            and target.is_relative_to(root)
            and target.stem.casefold() == item.name
            and details.st_size == item.actual_bytes
            and _image_format(target) == item.image_format
        )

    @staticmethod
    def _verify_outputs(root: Path, selected: Sequence[str]) -> dict[str, Path]:
        expected = set(selected)
        produced: dict[str, Path] = {}
        for path in root.rglob("*"):
            if path.is_symlink():
                raise ProjectError("Payload Dumper produced a symbolic link")
            if path.is_dir():
                continue
            if (
                not path.resolve().is_relative_to(root.resolve())
                or path.suffix.casefold() != ".img"
            ):
                raise ProjectError("Payload Dumper produced an unexpected output")
            name = path.stem.casefold()
            if name not in expected or name in produced:
                raise ProjectError("Payload Dumper output does not match the selected partitions")
            produced[name] = path
        missing = expected - produced.keys()
        if missing:
            raise ProjectError("Payload Dumper did not produce: " + ", ".join(sorted(missing)))
        return produced


def _category(name: str) -> str:
    if name in PayloadService.CRITICAL:
        return "Firmware / boot chain"
    if name in {"boot", "init_boot", "vendor_boot", "recovery", "dtbo"}:
        return "Boot"
    if name.startswith("vbmeta"):
        return "Verified Boot"
    if name in {
        "system",
        "system_ext",
        "product",
        "vendor",
        "odm",
        "mi_ext",
        "mi_product",
    }:
        return "Android filesystem"
    if name.endswith("_dlkm"):
        return "Kernel modules"
    return "Device firmware"


def _parse_partition(value: object) -> PayloadPartition:
    expected = {field.name for field in fields(PayloadPartition)}
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("payload partition evidence has an invalid shape")
    return PayloadPartition(**value)


def _valid_manifest_shape(manifest: PayloadManifest) -> bool:
    if manifest.schema_version not in {1, PayloadService.SCHEMA_VERSION}:
        return False
    if (
        type(manifest.project_id) is not str
        or not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", manifest.project_id)
        or not _aware_timestamp(manifest.generated_at)
        or not _sha256_value(manifest.source_original_sha256)
        or type(manifest.payload_path) is not str
        or not 0 < len(manifest.payload_path) <= 4_096
        or type(manifest.payload_size) is not int
        or not 0 < manifest.payload_size <= PayloadService.MAX_TOTAL_BYTES
        or not _sha256_value(manifest.payload_sha256)
        or type(manifest.tool_path) is not str
        or not 0 < len(manifest.tool_path) <= 4_096
        or not 1 <= len(manifest.partitions) <= PayloadService.MAX_PARTITIONS
        or len({item.name for item in manifest.partitions}) != len(manifest.partitions)
        or sum(item.estimated_bytes for item in manifest.partitions)
        > PayloadService.MAX_TOTAL_BYTES
        or any(not _valid_partition_shape(item) for item in manifest.partitions)
    ):
        return False
    if manifest.schema_version == 1:
        return bool(
            manifest.payload_modified_ns == 0
            and not manifest.tool_sha256
            and not manifest.record_digest
        )
    return bool(
        type(manifest.payload_modified_ns) is int
        and manifest.payload_modified_ns > 0
        and _sha256_value(manifest.tool_sha256)
        and _sha256_value(manifest.record_digest)
    )


def _valid_partition_shape(item: PayloadPartition) -> bool:
    if (
        type(item.name) is not str
        or not PayloadService.PARTITION_PATTERN.fullmatch(item.name)
        or type(item.estimated_bytes) is not int
        or not 0 <= item.estimated_bytes <= PayloadService.MAX_PARTITION_BYTES
        or type(item.category) is not str
        or not 0 < len(item.category) <= 80
        or type(item.recommended) is not bool
        or type(item.critical) is not bool
        or type(item.extracted_path) is not str
        or len(item.extracted_path) > 4_096
        or type(item.actual_bytes) is not int
        or not 0 <= item.actual_bytes <= PayloadService.MAX_PARTITION_BYTES
        or type(item.sha256) is not str
        or (item.sha256 and not _sha256_value(item.sha256))
        or type(item.image_format) is not str
        or item.image_format
        not in {
            "unknown",
            "Android boot image",
            "AVB metadata",
            "Android sparse image",
            "ext4 filesystem",
            "EROFS filesystem",
            "raw partition image",
        }
    ):
        return False
    return bool(
        (not item.extracted_path and item.actual_bytes == 0 and not item.sha256)
        or (item.extracted_path and item.actual_bytes > 0 and _sha256_value(item.sha256))
    )


def _seal_manifest(manifest: PayloadManifest) -> PayloadManifest:
    if manifest.schema_version != PayloadService.SCHEMA_VERSION:
        raise ProjectError("Legacy payload evidence must be rescanned before it can be sealed")
    unsealed = replace(manifest, record_digest="")
    return replace(unsealed, record_digest=_manifest_digest(unsealed))


def _manifest_digest(manifest: PayloadManifest) -> str:
    payload = asdict(manifest)
    payload.pop("record_digest", None)
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _sha256_value(value: object) -> bool:
    return type(value) is str and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _aware_timestamp(value: object) -> bool:
    if type(value) is not str or not 1 <= len(value) <= 80:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed <= datetime.now(UTC) + timedelta(minutes=5)


def _sha256(path: Path, progress: ProgressCallback | None = None) -> str:
    digest = hashlib.sha256()
    size = path.stat().st_size
    done = 0
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            digest.update(chunk)
            done += len(chunk)
            if progress is not None:
                progress(done, size)
    return digest.hexdigest()


def _image_format(path: Path) -> str:
    with path.open("rb") as stream:
        header = stream.read(4096)
    if header.startswith(b"ANDROID!"):
        return "Android boot image"
    if header.startswith(b"AVB0"):
        return "AVB metadata"
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
