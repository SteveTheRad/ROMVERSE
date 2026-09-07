"""Read-only, source-declared installation recipes; never execute archive scripts.

The first adapter recognizes an entire reviewed local HyperOS shell script by its
SHA-256. Its fixed operations are translated below, not parsed from shell text.
That recognition proves which instructions we understand, not image compatibility,
publisher authenticity, production certification, or a successful physical boot.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import struct
import zipfile
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path, PurePosixPath

from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore

POPSICLE_SCRIPT_SHA256 = "589afffba7bc1e3528f936caeb9fe3bfd43da8d4017d0b5d4562c6f9e2be41ac"
# Source: the complete flash_all.sh with the digest above. Preserve its order.
POPSICLE_PHYSICAL_PARTITIONS = (
    "abl",
    "aop",
    "aop_config",
    "bluetooth",
    "boot",
    "cpucp",
    "cpucp_dtb",
    "dcp",
    "devcfg",
    "dsp",
    "dtbo",
    "featenabler",
    "hyp",
    "hyp_ac_config",
    "idmanager",
    "imagefv",
    "init_boot",
    "keymaster",
    "modem",
    "modemfirmware",
    "multiimgqti",
    "pdp",
    "pdp_cdb",
    "pvmfw",
    "qtvm_dtbo",
    "qupfw",
    "recovery",
    "secretkeeper",
    "shrm",
    "soccp",
    "soccp_dcd",
    "soccp_debug",
    "spuservice",
    "tme_config",
    "tme_fw",
    "tme_seq_patch",
    "tz",
    "tz_ac_config",
    "tz_qti_config",
    "uefi",
    "uefisecapp",
    "vendor_boot",
    "vm-bootsys",
    "xbl",
    "xbl_ac_config",
    "xbl_config",
    "xbl_ramdump",
)


@dataclass(frozen=True, slots=True)
class SourceInstallImage:
    member: str
    sha256: str
    size_bytes: int
    expanded_size_bytes: int

    @property
    def name(self) -> str:
        return PurePosixPath(self.member).name


@dataclass(frozen=True, slots=True)
class SourceInstallStep:
    action: str
    partition: str = ""
    image_member: str = ""
    slot: str = ""
    chunk_size: str = ""


@dataclass(frozen=True, slots=True)
class SourceInstallationRecipe:
    project_id: str
    source_sha256: str
    recipe_digest: str
    label: str
    expected_product: str
    expected_manufacturer: str
    target_slot: str
    requires_critical_unlock: bool
    images: tuple[SourceInstallImage, ...]
    steps: tuple[SourceInstallStep, ...]
    warnings: tuple[str, ...]
    script_sha256: str
    archive_path: Path = field(repr=False)
    script_member: str
    checksums_member: str
    checksums_sha256: str
    wipe: bool
    reboot: bool


class SourceInstallationService:
    """Verify a protected ZIP and derive a complete supported local recipe.

    All work here is read-only. Runtime must privately stage and hash the archive
    members again before performing the reviewed steps. No working-tree images,
    generated shell, archive executables, or synthetic Device Pack are used.
    """

    MAX_ARCHIVE_MEMBERS = 100_000
    MAX_PACKAGE_MEMBERS = 2048
    MAX_SCRIPT_BYTES = 128 * 1024
    MAX_CHECKSUM_BYTES = 1024 * 1024
    MAX_MEMBER_BYTES = 128 * 1024**3
    MAX_PACKAGE_BYTES = 256 * 1024**3
    MAX_EXPANDED_BYTES = 1024**4
    CHUNK_SIZE = 4 * 1024 * 1024

    def __init__(self, store: RomProjectStore):
        self.store = store

    def prepare(
        self, project_id: str, *, wipe: bool = False, reboot: bool = True
    ) -> SourceInstallationRecipe:
        if type(wipe) is not bool or type(reboot) is not bool:
            raise ProjectError("Choose wipe and reboot explicitly as yes or no.")
        project = self.store.get(project_id)
        if project.original is None:
            raise ProjectError(
                "Import the intended firmware package as this project's protected source first."
            )
        path = self.store.original_path(project_id)
        self._source_path(path)
        try:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, "rb") as stream:
                before = os.fstat(stream.fileno())
                if (
                    not stat.S_ISREG(before.st_mode)
                    or before.st_size != project.original.size_bytes
                ):
                    raise ProjectError(
                        "The protected source size changed or it is not a regular file."
                    )
                source_digest = hashlib.sha256()
                for chunk in iter(lambda: stream.read(self.CHUNK_SIZE), b""):
                    source_digest.update(chunk)
                if source_digest.hexdigest() != project.original.sha256:
                    raise ProjectError(
                        "The protected source SHA-256 changed. Re-import the intended package."
                    )
                stream.seek(0)
                with zipfile.ZipFile(stream) as archive:
                    recipe = self._prepare_zip(
                        project_id, path, project.original.sha256, archive, wipe, reboot
                    )
                if self._fingerprint(before) != self._fingerprint(os.fstat(stream.fileno())):
                    raise ProjectError("The protected source changed during recipe verification.")
                self._source_path(path)
                if self._fingerprint(before) != self._fingerprint(path.stat()):
                    raise ProjectError(
                        "The protected source was replaced during recipe verification."
                    )
            if self.store.get(project_id).original != project.original:
                raise ProjectError(
                    "The project's protected source changed during recipe verification."
                )
            return recipe
        except ProjectError:
            raise
        except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, NotImplementedError) as exc:
            raise ProjectError(
                "The source package could not be read and verified as a supported ZIP."
            ) from exc

    def verify(self, recipe: SourceInstallationRecipe) -> SourceInstallationRecipe:
        if not isinstance(recipe, SourceInstallationRecipe):
            raise ProjectError("The reviewed source installation recipe is invalid.")
        current = self.prepare(recipe.project_id, wipe=recipe.wipe, reboot=recipe.reboot)
        if current != recipe:
            raise ProjectError(
                "The source, images, or reviewed installation choices changed. Prepare a fresh review."
            )
        return current

    def _prepare_zip(self, project_id, path, source_sha, archive, wipe, reboot):
        entries = archive.infolist()
        if not entries or len(entries) > self.MAX_ARCHIVE_MEMBERS:
            raise ProjectError("The source ZIP has an empty or excessively large member inventory.")
        members: dict[str, zipfile.ZipInfo] = {}
        for item in entries:
            normalized = _safe_member(item.filename.rstrip("/"))
            if normalized in members:
                raise ProjectError("The source ZIP contains duplicate or ambiguous member paths.")
            mode = item.external_attr >> 16
            if (stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}) or item.flag_bits & 1:
                raise ProjectError(
                    "The source ZIP contains a linked, special, or encrypted member."
                )
            if not item.is_dir() and stat.S_ISDIR(mode):
                raise ProjectError("The source ZIP has contradictory member types.")
            members[normalized] = item
        scripts = [
            item
            for name, item in members.items()
            if PurePosixPath(name).name == "flash_all.sh" and not item.is_dir()
        ]
        if len(scripts) != 1:
            raise ProjectError(
                "Automatic installation needs one supported source flash_all.sh. This package has none or is ambiguous; no filename-based partition guessing is used."
            )
        script = scripts[0]
        script_bytes = self._bounded_read(archive, script, self.MAX_SCRIPT_BYTES)
        script_sha = hashlib.sha256(script_bytes).hexdigest()
        if script_sha != POPSICLE_SCRIPT_SHA256:
            raise ProjectError(
                "This source installer is not yet supported. Its complete script needs a reviewed adapter; ROMVERSE will not execute shell scripts or silently skip instructions."
            )
        root = PurePosixPath(_safe_member(script.filename)).parent
        manifest_name = (root / "SHA256SUMS").as_posix()
        manifest = members.get(manifest_name)
        if manifest is None or manifest.is_dir():
            raise ProjectError("The source installer is missing its SHA256SUMS integrity manifest.")
        manifest_bytes = self._bounded_read(archive, manifest, self.MAX_CHECKSUM_BYTES)
        checksums = self._checksums(manifest_bytes, root)
        script_normal = _safe_member(script.filename)
        if checksums.get(script_normal) != script_sha:
            raise ProjectError("SHA256SUMS does not bind the exact reviewed source installer.")
        package_files = {
            name
            for name, item in members.items()
            if not item.is_dir()
            and PurePosixPath(name).is_relative_to(root)
            and name != manifest_name
        }
        if set(checksums) != package_files:
            raise ProjectError(
                "SHA256SUMS must cover every package file exactly; an entry is missing, extra, or ambiguous."
            )
        if sum(members[name].file_size for name in checksums) > self.MAX_PACKAGE_BYTES:
            raise ProjectError("The source package exceeds the supported verification size bound.")
        required = tuple(
            (root / "images" / f"{part}.img").as_posix()
            for part in (*POPSICLE_PHYSICAL_PARTITIONS, "super", "vbmeta_system", "vbmeta")
        )
        if not set(required).issubset(checksums):
            raise ProjectError(
                "The supported installer is missing a required image or its exact checksum. Re-download the complete package."
            )
        verified: dict[str, SourceInstallImage] = {}
        for member, expected in checksums.items():
            item = members[member]
            if item.file_size < 0 or item.file_size > self.MAX_MEMBER_BYTES:
                raise ProjectError(
                    "A package member exceeds the supported verification size bound."
                )
            is_image = member in required
            with archive.open(item) as image_stream:
                digest, expanded = _hash_stream(
                    image_stream,
                    item.file_size,
                    image=is_image,
                    maximum_expanded=self.MAX_EXPANDED_BYTES,
                )
            if digest != expected:
                raise ProjectError(
                    f"Package checksum mismatch: {PurePosixPath(member).name}. No installation can start."
                )
            if is_image:
                # Preserve the actual ZIP name for an exact, unambiguous runtime open.
                verified[member] = SourceInstallImage(
                    item.filename, digest, item.file_size, expanded
                )
        images = tuple(verified[member] for member in required)
        steps = [SourceInstallStep("set_active", slot="a")]
        steps.extend(
            SourceInstallStep("flash", f"{part}_a", images[index].member)
            for index, part in enumerate(POPSICLE_PHYSICAL_PARTITIONS)
        )
        steps.extend(
            (
                SourceInstallStep("flash", "super", images[-3].member, chunk_size="700M"),
                SourceInstallStep("flash", "vbmeta_system_a", images[-2].member),
                SourceInstallStep("flash", "vbmeta_a", images[-1].member),
            )
        )
        if wipe:
            steps.extend(
                (SourceInstallStep("erase", "metadata"), SourceInstallStep("erase", "userdata"))
            )
        steps.append(SourceInstallStep("set_active", slot="a"))
        if reboot:
            steps.append(SourceInstallStep("reboot"))
        warnings = (
            "SOURCE-DECLARED LOCAL INSTALLATION: this adapter understands the exact source script, not arbitrary firmware packages. User-imported checksums are integrity evidence, not an official publisher signature or compatibility certification.",
            "All 50 source-declared images will be written, including critical bootloader/radio firmware. The exact live product must be popsicle, with bootloader and critical partitions confirmed unlocked; matching storage capacity is not device identity.",
            "Slot A is selected before and after flashing. The entire super container is replaced and may affect logical partitions for other slots; slot B is not a guaranteed untouched recovery route.",
            "Source-declared AVB metadata is included without verification-disable flags. Anti-rollback, downgrade/data compatibility, physical recovery and subsystem health are not proven by these checks. An unlocked bootloader is not an anti-rollback bypass.",
            "The source's optional Android/Fastbootd-to-bootloader transport steps require separate exact-phone confirmation before this recipe starts. No archive shell script, unlock, relock or custom command will run.",
            "WIPE SELECTED: metadata and userdata will be erased, including apps, accounts, photos and local data. Keep an independent backup."
            if wipe
            else "KEEP DATA SELECTED: metadata and userdata are not erased by this recipe. Data compatibility and preservation are not guaranteed; keep an independent backup.",
            "Android reboot is selected after completed writes. Boot health requires the separate measured boot check; the first boot may take 10–15 minutes."
            if reboot
            else "No final reboot is selected; the phone remains in bootloader Fastboot after completed writes.",
        )
        recipe = SourceInstallationRecipe(
            project_id,
            source_sha,
            "",
            "Source-declared Xiaomi popsicle installation",
            "popsicle",
            "Xiaomi",
            "a",
            True,
            images,
            tuple(steps),
            warnings,
            script_sha,
            path,
            script.filename,
            manifest.filename,
            hashlib.sha256(manifest_bytes).hexdigest(),
            wipe,
            reboot,
        )
        payload = asdict(recipe)
        payload.pop("recipe_digest")
        return replace(
            recipe,
            recipe_digest=hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
            ).hexdigest(),
        )

    def _checksums(self, data: bytes, root: PurePosixPath) -> dict[str, str]:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProjectError("SHA256SUMS is not a supported UTF-8 checksum manifest.") from exc
        result = {}
        for line in text.splitlines():
            if not line:
                continue
            match = re.fullmatch(r"([0-9a-fA-F]{64}) [ *](.+)", line)
            if match is None:
                raise ProjectError("SHA256SUMS contains an unsupported or malformed line.")
            name = (root / _safe_member(match[2])).as_posix()
            if name in result or len(result) >= self.MAX_PACKAGE_MEMBERS:
                raise ProjectError("SHA256SUMS contains duplicate paths or too many entries.")
            result[name] = match[1].lower()
        if not result:
            raise ProjectError("SHA256SUMS is empty.")
        return result

    @staticmethod
    def _bounded_read(archive, item, maximum):
        if item.file_size <= 0 or item.file_size > maximum:
            raise ProjectError(
                "The installer script or checksum manifest is empty or exceeds its safe size bound."
            )
        with archive.open(item) as stream:
            data = stream.read(maximum + 1)
        if len(data) != item.file_size:
            raise ProjectError("The installer script or checksum manifest is truncated.")
        return data

    def _source_path(self, path: Path) -> None:
        root = self.store.originals_root
        if not path.is_relative_to(root) or path == root:
            raise ProjectError("The source is outside the protected originals directory.")
        try:
            for current in (path, *path.parents):
                if current.is_symlink():
                    raise ProjectError("The protected source path contains a symbolic link.")
                if current == self.store.workspace:
                    break
            if not stat.S_ISREG(path.stat().st_mode):
                raise ProjectError("The protected source is not a regular file.")
        except OSError as exc:
            raise ProjectError("The protected source is unavailable.") from exc

    @staticmethod
    def _fingerprint(info):
        # CPython's Windows handle-stat and path-stat implementations can expose the
        # same NTFS creation time with different sub-millisecond rounding. Device and
        # file indexes still provide same-file identity; size and mtime retain the
        # content-race guard. Keep the stricter ctime comparison on POSIX hosts.
        ctime_ns = None if os.name == "nt" else info.st_ctime_ns
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, ctime_ns


def _safe_member(name: str) -> str:
    if not name or "\\" in name or any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise ProjectError("A package member path is unsafe.")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or path.as_posix() in {"", "."}:
        raise ProjectError("A package member path escapes its source root.")
    return path.as_posix()


def _hash_stream(stream, size: int, *, image: bool, maximum_expanded: int) -> tuple[str, int]:
    """Hash once while validating sparse geometry, without expansion or seeks."""
    digest = hashlib.sha256()
    consumed = 0

    def read_exact(amount):
        nonlocal consumed
        if amount < 0 or consumed + amount > size:
            raise ProjectError("An image or sparse chunk extends outside its package member.")
        data = stream.read(amount)
        if len(data) != amount:
            raise ProjectError("A package member is truncated.")
        consumed += amount
        digest.update(data)
        return data

    def discard(amount):
        while amount:
            step = min(amount, SourceInstallationService.CHUNK_SIZE)
            read_exact(step)
            amount -= step

    if image and size <= 0:
        raise ProjectError("A required firmware image is empty.")
    header = read_exact(min(28, size))
    expanded = size
    if image and header[:4] == b"\x3a\xff\x26\xed":
        if len(header) != 28:
            raise ProjectError("An Android sparse image header is truncated.")
        _magic, major, _minor, file_header, chunk_header, block_size, blocks, chunks, _crc = (
            struct.unpack("<I4H4I", header)
        )
        expanded = blocks * block_size
        if (
            major != 1
            or file_header < 28
            or chunk_header < 12
            or block_size <= 0
            or block_size % 4
            or blocks <= 0
            or chunks <= 0
            or chunks > size // 12
            or expanded > maximum_expanded
        ):
            raise ProjectError("An Android sparse image has invalid or excessive header geometry.")
        discard(file_header - 28)
        observed_blocks = 0
        for _ in range(chunks):
            kind, _reserved, chunk_blocks, total = struct.unpack("<2H2I", read_exact(12))
            payload = total - chunk_header
            expected = {0xCAC1: chunk_blocks * block_size, 0xCAC2: 4, 0xCAC3: 0, 0xCAC4: 4}.get(
                kind
            )
            if expected is None or payload != expected or (kind == 0xCAC4 and chunk_blocks != 0):
                raise ProjectError("An Android sparse image has invalid chunk geometry.")
            observed_blocks += chunk_blocks
            discard(chunk_header - 12)
            discard(payload)
        if observed_blocks != blocks or consumed != size:
            raise ProjectError(
                "An Android sparse image has an inconsistent block count or trailing data."
            )
    else:
        discard(size - consumed)
    if stream.read(1):
        raise ProjectError("A package member has unexpected trailing bytes.")
    return digest.hexdigest(), expanded
