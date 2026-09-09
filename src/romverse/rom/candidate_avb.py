"""Content-bound AVB evidence for a local, unlocked experimental candidate.

AVB binary layouts and Merkle ordering follow AOSP external/avb (avbtool.py,
AvbVBMetaHeader, AvbHashtreeDescriptor and generate_hash_tree). Cryptographic
self-consistency is not publisher trust, rollback permission or device authority.
No image is modified and no AVB-disable, unlock, relock or device command exists.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import platform
import re
import stat
import struct
import zipfile
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
from typing import get_args, get_origin, get_type_hints

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from romverse.infrastructure.file_identity import stable_file_identity
from romverse.infrastructure.local_store import atomic_write_json, read_json_object
from romverse.infrastructure.process import CommandResult
from romverse.infrastructure.toolchain_evidence import ToolchainEvidenceService
from romverse.infrastructure.toolchain_versions import VersionedToolchainStore
from romverse.infrastructure.tools import ToolStatus
from romverse.rom.base_image_compatibility import (
    BaseImageCompatibilityReceipt,
    BaseImageCompatibilityService,
)
from romverse.rom.build_execution import LocalDeviceBuildExecutor
from romverse.rom.models import ProjectError
from romverse.rom.project_flash import ProjectFlashPreparationService
from romverse.rom.source_installation import SourceInstallationService, _safe_member

_HEADER = struct.Struct("!4s2I2QI11Q2I48s80s")
_TREE = struct.Struct("!QQIQQQIIIQQ32sIIII60s")
_HASH = struct.Struct("!QQQ32sIIII60s")
_CHAIN = struct.Struct("!QQIIII60s")
_MAX_META = 8 * 1024 * 1024
_MAX_IMAGE = 128 * 1024**3
_MAX_TREE = 128 * 1024 * 1024
_CHUNK = 4 * 1024 * 1024
_PARTITIONS = ("product", "system", "system_ext")
_POLICY = "Local unlocked experimental · unsigned child · not OEM-trusted"
_WARNINGS = (
    "The candidate child is unsigned. The unchanged signed source root delegates a signing key "
    "that this child does not possess; this is NOT a valid OEM-trusted AVB chain.",
    "This local experimental route requires an already unlocked bootloader. Device acceptance, "
    "rollback protection, data compatibility and boot health remain unverified.",
    "No verification-disable flags, unlock, relock or phone-changing commands are added. "
    "The older reference-only AVB policy is not promoted to flash-validated authority.",
    "Descriptor content and stored Merkle trees are checked. FEC parity is not regenerated; "
    "passthrough FEC bytes remain bound to the exact source image hash.",
)


@dataclass(frozen=True, slots=True)
class CandidateAvbDescriptor:
    partition: str
    kind: str
    descriptor_sha256: str
    image_sha256: str
    image_size: int
    hash_algorithm: str
    salt: str
    digest: str
    flags: int
    tree_offset: int = 0
    tree_size: int = 0
    data_block_size: int = 0
    hash_block_size: int = 0
    fec_num_roots: int = 0
    fec_offset: int = 0
    fec_size: int = 0


@dataclass(frozen=True, slots=True)
class CandidateAvbChain:
    partition: str
    rollback_index_location: int
    public_key_sha256: str
    flags: int


@dataclass(frozen=True, slots=True)
class CandidateAvbReceipt:
    schema_version: int
    receipt_digest: str
    project_id: str
    source_sha256: str
    build_receipt_digest: str
    root_sha256: str
    candidate_super_sha256: str
    candidate_vbmeta_system_sha256: str
    product_sha256: str
    policy_label: str
    warnings: tuple[str, ...]
    base_receipt_digest: str
    pack_sha256: str
    contract_digest: str
    build_plan_digest: str
    toolchain_manifest_digest: str
    avbtool_sha256: str
    root_algorithm: str
    root_public_key_sha256: str
    root_rollback_index: int
    root_rollback_index_location: int
    root_flags: int
    root_chains: tuple[CandidateAvbChain, ...]
    child_algorithm: str
    child_rollback_index: int
    child_rollback_index_location: int
    child_flags: int
    descriptors: tuple[CandidateAvbDescriptor, ...]
    phone_changed: bool = False
    execution_authority: str = "none"
    oem_trusted: bool = False
    candidate_signed: bool = False


@dataclass(frozen=True, slots=True)
class _Descriptor:
    tag: int
    raw: bytes
    partition: str = ""
    image_size: int = 0
    algorithm: str = ""
    salt: bytes = b""
    digest: bytes = b""
    flags: int = 0
    tree_offset: int = 0
    tree_size: int = 0
    data_block_size: int = 0
    hash_block_size: int = 0
    fec_num_roots: int = 0
    fec_offset: int = 0
    fec_size: int = 0
    rollback_location: int = 0
    public_key: bytes = b""


@dataclass(frozen=True, slots=True)
class _Metadata:
    algorithm: str
    public_key: bytes
    rollback: int
    location: int
    flags: int
    descriptors: tuple[_Descriptor, ...]
    offset: int = 0


class CandidateAvbService:
    """Verify current build/source evidence and actual descriptors, with no phone access."""

    FORMAT = "romverse.candidate-avb-content"
    RECEIPT_NAME = "candidate-avb-content.romverse"
    MAX_RECEIPT_BYTES = 128 * 1024

    def __init__(self, store, registry, tools, runner):
        self.store = store
        self.registry = registry
        self.tools = tuple(tools)
        self.runner = runner

    def prepare(self, project_id: str, base_receipt: BaseImageCompatibilityReceipt):
        receipt = self._derive(project_id, base_receipt)
        atomic_write_json(
            self.store.projects_root / project_id / self.RECEIPT_NAME,
            {"format": self.FORMAT, **asdict(receipt)},
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_RECEIPT_BYTES,
        )
        return receipt

    def verify(self, receipt: CandidateAvbReceipt, base_receipt: BaseImageCompatibilityReceipt):
        if type(receipt) is not CandidateAvbReceipt or not _valid_receipt(receipt):
            raise ProjectError("Candidate AVB evidence is malformed or changed.")
        saved = read_json_object(
            self.store.projects_root / receipt.project_id / self.RECEIPT_NAME,
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_RECEIPT_BYTES,
        )
        if _json(saved) != _json({"format": self.FORMAT, **asdict(receipt)}):
            raise ProjectError("The saved candidate AVB evidence is missing or changed.")
        current = self._derive(receipt.project_id, base_receipt)
        if current != receipt:
            raise ProjectError("Candidate AVB inputs changed; prepare the exact candidate again.")
        return current

    def load(self, project_id: str) -> CandidateAvbReceipt | None:
        """Strict historical retrieval; verify() still freshly checks all dependencies."""
        self.store.get(project_id)
        try:
            data = read_json_object(
                self.store.projects_root / project_id / self.RECEIPT_NAME,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
            if data.pop("format", None) != self.FORMAT:
                return None
            receipt = _decode(CandidateAvbReceipt, data)
            if receipt.project_id != project_id or not _valid_receipt(receipt):
                return None
            return receipt
        except (OSError, ValueError, TypeError, KeyError, ProjectError):
            return None

    def _collect(self, project_id, base):
        if type(base) is not BaseImageCompatibilityReceipt or base.build_project_id != project_id:
            raise ProjectError("AVB verification needs this project's exact base-image receipt.")
        source_states = tuple(
            (
                identifier,
                self.store.get(identifier).original,
                self.store.original_path(identifier),
                _fingerprint(self.store.original_path(identifier).stat()),
            )
            for identifier in (project_id, base.procedure_project_id)
        )
        procedure = SourceInstallationService(self.store).prepare(
            base.procedure_project_id, wipe=base.procedure_wipe, reboot=base.procedure_reboot
        )
        BaseImageCompatibilityService(self.store, self.registry).verify(base, procedure)
        # This existing preparation checks the latest tree, recipe, build and every
        # saved output hash; it cannot fall back from a build to protected images.
        prepared = ProjectFlashPreparationService(self.store, self.registry).prepare(
            project_id, candidate_choice="built"
        )
        executor = LocalDeviceBuildExecutor(self.store, self.registry, self.tools, self.runner)
        build = executor.load_receipt(project_id)
        if build is None or build.schema_version != 2:
            raise ProjectError("Build a current candidate with pinned toolchain evidence first.")
        manifest = ToolchainEvidenceService(
            self.store.workspace, platform.system() or os.name
        ).load_private(build.toolchain_manifest_digest)
        tool, tool_evidence = _resolve_avbtool(self.store.workspace, self.tools, manifest)
        executor.contracts.tool_statuses = tuple(
            item for item in self.tools if item.name != "AVBTool"
        ) + (ToolStatus("AVBTool", True, str(tool), tool_evidence.version, "Exact build tool"),)
        plan = executor.contracts.verify_for_execution(project_id)
        packs = [p for p in self.registry.packs if p.pack_id == base.pack_id]
        if len(packs) != 1 or packs[0].build_contract is None:
            raise ProjectError("The exact AVB build contract is unavailable.")
        pack, contract = packs[0], packs[0].build_contract
        if (
            pack.sha256 != base.pack_sha256
            or _digest(asdict(contract)) != base.contract_digest
            or plan.plan_digest != build.plan_digest
            or plan.source_archive_sha256 != base.source_sha256
            or plan.source_payload_sha256 != base.payload_sha256
            or prepared.source_sha256 != base.source_sha256
            or tuple(contract.vbmeta_descriptor_partitions) != _PARTITIONS
            or tuple(r.name for r in contract.partitions if r.mode == "rebuild") != ("product",)
        ):
            raise ProjectError("The AVB candidate does not match the current exact build contract.")
        steps = {step.step_id: step for step in plan.steps}
        if len(steps) != len(plan.steps):
            raise ProjectError("The build contains ambiguous step roles.")
        required = ("add-avb-footer", "make-vbmeta-system", "assemble-super", "unpack-and-compare")
        if any(name not in steps for name in required):
            raise ProjectError(
                "The candidate has no complete product/child/super verification roles."
            )
        role_paths = {}
        outputs = {item.path: item for item in build.outputs}
        for role, step_id in (
            ("product", required[0]),
            ("child", required[1]),
            ("super", required[2]),
        ):
            step = steps[step_id]
            if len(step.outputs) != 1 or step.outputs[0] not in outputs:
                raise ProjectError("A candidate output is not bound to its exact build-step role.")
            output = outputs[step.outputs[0]]
            role_paths[role] = (
                _contained(self.store, output.path),
                output.sha256,
                output.size_bytes,
            )
        verify_steps = [step for step in build.steps if step.step_id == "unpack-and-compare"]
        if len(verify_steps) != 1 or verify_steps[0].returncode != 0:
            raise ProjectError(
                "The candidate super has no successful logical-partition comparison."
            )
        records = steps["make-vbmeta-system"].inputs
        if len(records) != 3 or records[0] != steps["add-avb-footer"].outputs[0]:
            raise ProjectError("Child descriptor inputs differ from the expected build roles.")
        rules = {rule.name: rule for rule in contract.partitions}
        product_rule = rules["product"]
        if (
            product_rule.avb_hashtree is None
            or product_rule.avb_hashtree.generate_fec
            or role_paths["product"][2] != product_rule.size_bytes
        ):
            raise ProjectError("The rebuilt product needs its exact no-FEC partition contract.")
        for name, relative in zip(_PARTITIONS[1:], records[1:], strict=True):
            rule = rules.get(name)
            if rule is None or rule.mode != "passthrough":
                raise ProjectError(
                    "The child needs exact source system and system_ext passthrough."
                )
            role_paths[name] = (
                _contained(self.store, relative),
                rule.source_sha256,
                rule.source_size_bytes,
            )
        root_rows = [item for item in base.comparisons if item.partition == "vbmeta"]
        if len(root_rows) != 1 or root_rows[0].sha256 != contract.top_level_vbmeta_sha256:
            raise ProjectError("The source root is not the exact OTA/base root image.")
        root = _archive_root(procedure.archive_path, root_rows[0])
        return (
            build,
            plan,
            role_paths,
            root,
            tool,
            tool_evidence.sha256,
            product_rule.avb_hashtree,
            source_states,
        )

    def _derive(self, project_id, base):
        build, plan, paths, root_blob, tool, tool_hash, product_policy, source_states = (
            self._collect(project_id, base)
        )
        for path, expected, size in paths.values():
            if _hash(path) != (expected, size):
                raise ProjectError(
                    "A candidate or source passthrough image changed before AVB verification."
                )
        root = _metadata(io.BytesIO(root_blob), len(root_blob))
        child = _read_metadata(paths["child"][0])
        if root.algorithm == "NONE" or root.flags != 0:
            raise ProjectError(
                "This route requires the exact signed source root with verification enabled."
            )
        if child.algorithm != "NONE" or child.flags or child.rollback or child.location:
            raise ProjectError(
                "This adapter supports only the explicitly unsigned, flags-zero local child."
            )
        chains = [item for item in root.descriptors if item.tag == 4]
        targets = [item for item in chains if item.partition == "vbmeta_system"]
        if len(targets) != 1 or targets[0].flags or targets[0].rollback_location <= 0:
            raise ProjectError("The source root has no unambiguous enabled vbmeta_system chain.")
        # Parse and validate the actual delegated key, not a printed fingerprint.
        for chain in chains:
            _public_key(chain.public_key)
        actual = _partition_descriptors(child)
        if set(actual) != set(_PARTITIONS):
            raise ProjectError(
                "Candidate child descriptors do not cover exactly product/system/system_ext."
            )
        expected_extras = []
        content = []
        for name in _PARTITIONS:
            path, image_hash, _size = paths[name]
            embedded = _read_metadata(path)
            source_descriptors = _partition_descriptors(embedded)
            if (
                set(source_descriptors) != {name}
                or source_descriptors[name].raw != actual[name].raw
            ):
                raise ProjectError(
                    f"Candidate {name} descriptor content differs from its exact image footer."
                )
            if embedded.flags or (name == "product" and embedded.algorithm != "NONE"):
                raise ProjectError(f"Unsupported verification flags or signing mode in {name}.")
            expected_extras.extend(item.raw for item in embedded.descriptors if item.tag == 0)
            desc = actual[name]
            if name == "product" and (
                desc.tag != 1
                or desc.flags
                or desc.algorithm != product_policy.hash_algorithm
                or desc.salt.hex() != product_policy.salt.casefold()
                or desc.fec_num_roots
                or embedded.rollback
                or embedded.location
            ):
                raise ProjectError(
                    "Rebuilt product AVB fields differ from the exact build contract."
                )
            _verify_content(path, desc, embedded.offset)
            content.append(_evidence(desc, image_hash))
        if tuple(item.raw for item in child.descriptors if item.tag == 0) != tuple(expected_extras):
            raise ProjectError("The candidate child contains changed or unexpected AVB properties.")
        # AOSP informational inspection is read-only. Content verification above is
        # independent of printed names or a runner's claimed success.
        if _hash(tool, maximum=1024**3)[0] != tool_hash:
            raise ProjectError("AVBTool changed before the read-only inspection.")
        command = (str(tool), "info_image", "--image", str(paths["child"][0]))
        result = self.runner.run(command, timeout=30, cwd=self.store.workspace)
        if not isinstance(result, CommandResult) or result.args != command or not result.ok:
            raise ProjectError("The pinned AVBTool could not inspect this exact candidate child.")
        if re.findall(r"(?m)^Algorithm:\s*(\S+)\s*$", result.stdout) != [child.algorithm]:
            raise ProjectError(
                "AVBTool's candidate header disagrees with bounded binary verification."
            )
        for path, expected, size in paths.values():
            if _hash(path) != (expected, size):
                raise ProjectError("An AVB input changed during content verification.")
        if _hash(tool, maximum=1024**3)[0] != tool_hash:
            raise ProjectError("AVBTool changed during candidate verification.")
        for identifier, original, path, fingerprint in source_states:
            if (
                self.store.get(identifier).original != original
                or self.store.original_path(identifier) != path
                or path.is_symlink()
                or _fingerprint(path.stat()) != fingerprint
            ):
                raise ProjectError("A protected source changed during AVB verification.")
        # A newer build must not inherit the old build's verification result.
        latest = LocalDeviceBuildExecutor(
            self.store, self.registry, self.tools, self.runner
        ).load_receipt(project_id)
        if latest is None or latest.receipt_digest != build.receipt_digest:
            raise ProjectError("The selected build changed during AVB verification.")
        return _seal(
            CandidateAvbReceipt(
                1,
                "",
                project_id,
                base.source_sha256,
                build.receipt_digest,
                hashlib.sha256(root_blob).hexdigest(),
                paths["super"][1],
                paths["child"][1],
                paths["product"][1],
                _POLICY,
                _WARNINGS,
                base.receipt_digest,
                base.pack_sha256,
                base.contract_digest,
                plan.plan_digest,
                build.toolchain_manifest_digest,
                tool_hash,
                root.algorithm,
                hashlib.sha256(root.public_key).hexdigest(),
                root.rollback,
                root.location,
                root.flags,
                tuple(
                    CandidateAvbChain(
                        d.partition,
                        d.rollback_location,
                        hashlib.sha256(d.public_key).hexdigest(),
                        d.flags,
                    )
                    for d in chains
                ),
                child.algorithm,
                child.rollback,
                child.location,
                child.flags,
                tuple(content),
            )
        )


def _resolve_avbtool(workspace, statuses, manifest):
    """Read an existing exact managed slot; never snapshot or repair tool storage."""
    evidence = [item for item in manifest.tools if item.name == "AVBTool"]
    if len(evidence) != 1 or evidence[0].state != "verified" or not evidence[0].sha256:
        raise ProjectError("The build's exact verified AVBTool is unavailable.")
    item = evidence[0]
    try:
        if item.origin == "romverse-managed":
            if item.integrity_scope != "managed-source-and-executable":
                raise ProjectError("The build's managed AVBTool has no verified source binding.")
            versions = VersionedToolchainStore(workspace)
            slot = versions._slot(item)
            # The existing store's isolate/_verify_slot methods can create or
            # chmod directories. Reuse its identity/receipt contract read-only.
            current = versions.workspace
            present = True
            for component in slot.relative_to(current).parts:
                current = current / component
                try:
                    details = current.lstat()
                except FileNotFoundError:
                    present = False
                    break
                if current.is_symlink() or not stat.S_ISDIR(details.st_mode):
                    raise ProjectError("The preserved AVBTool directory is unsafe.")
            if present:
                with os.scandir(slot) as entries:
                    names = []
                    for entry in entries:
                        names.append(entry.name)
                        if len(names) > 2:
                            break
                if sorted(names) != sorted((item.executable_name, versions.RECEIPT_NAME)):
                    raise ProjectError("The preserved AVBTool slot contains unexpected files.")
                saved = read_json_object(
                    slot / versions.RECEIPT_NAME,
                    boundary=versions.workspace,
                    maximum_bytes=versions.MAX_RECEIPT_BYTES,
                )
                expected = {"format": "romverse.versioned-tool", **asdict(versions._receipt(item))}
                if _json(saved) != _json(expected):
                    raise ProjectError("The preserved AVBTool receipt changed from its build.")
                path = slot / item.executable_name
                details = path.lstat()
                if (
                    path.is_symlink()
                    or getattr(details, "st_file_attributes", 0)
                    & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
                    or not stat.S_ISREG(details.st_mode)
                ):
                    raise ProjectError("The preserved AVBTool is not a regular unlinked file.")
                if _hash(path, maximum=1024**3) != (item.sha256, item.size_bytes):
                    raise ProjectError("The preserved AVBTool bytes changed from their build.")
                return path, item
        active = [tool for tool in statuses if tool.name == "AVBTool" and tool.available]
        if len(active) != 1 or not active[0].path:
            raise ProjectError("The exact build AVBTool is not preserved or currently available.")
        path = Path(active[0].path).resolve(strict=True)
        if path.name != item.executable_name or _hash(path, maximum=1024**3) != (
            item.sha256,
            item.size_bytes,
        ):
            raise ProjectError("AVBTool changed from the tool bound into this build.")
        return path, item
    except (OSError, ValueError) as exc:
        if isinstance(exc, ProjectError):
            raise
        raise ProjectError(f"The exact build AVBTool could not be read: {exc}") from exc


def _contained(store, relative):
    if (
        not isinstance(relative, str)
        or Path(relative).is_absolute()
        or ".." in Path(relative).parts
    ):
        raise ProjectError("An AVB input is outside the project workspace.")
    path = store.workspace / relative
    if not path.is_relative_to(store.working_root):
        raise ProjectError("An AVB image is outside the working-image boundary.")
    for current in (path, *path.parents):
        if current.is_symlink():
            raise ProjectError("An AVB input path contains a symbolic link.")
        if current == store.workspace:
            break
    if path.resolve(strict=True) != path or not path.is_file():
        raise ProjectError("An AVB input is not a regular contained image.")
    return path


def _fingerprint(info):
    return stable_file_identity(info)


def _hash(path, maximum=_MAX_IMAGE):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= maximum:
            raise ProjectError("An AVB input exceeds its regular-file size bound.")
        digest = hashlib.sha256()
        while block := stream.read(_CHUNK):
            digest.update(block)
        if _fingerprint(before) != _fingerprint(os.fstat(stream.fileno())) or _fingerprint(
            before
        ) != _fingerprint(path.stat()):
            raise ProjectError("An AVB input changed while being hashed.")
        return digest.hexdigest(), before.st_size


def _archive_root(path, row):
    if not 0 < row.size_bytes <= _MAX_META:
        raise ProjectError("The source root AVB image exceeds its bounded size.")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as stream:
        before = _fingerprint(os.fstat(stream.fileno()))
        with zipfile.ZipFile(stream) as archive:
            infos = archive.infolist()
            if len(infos) > SourceInstallationService.MAX_ARCHIVE_MEMBERS:
                raise ProjectError("The source root archive inventory is oversized.")
            matches = [
                i
                for i in infos
                if not i.is_dir() and _safe_member(i.filename) == _safe_member(row.member)
            ]
            if len(matches) != 1 or matches[0].file_size != row.size_bytes:
                raise ProjectError("The exact source root member is missing or ambiguous.")
            with archive.open(matches[0]) as member:
                blob = member.read(_MAX_META + 1)
        if before != _fingerprint(os.fstat(stream.fileno())) or before != _fingerprint(path.stat()):
            raise ProjectError("The source archive changed while reading its AVB root.")
    if len(blob) != row.size_bytes or hashlib.sha256(blob).hexdigest() != row.sha256:
        raise ProjectError("The AVB root differs from the measured OTA/base image.")
    return blob


def _read_metadata(path):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ProjectError("AVB metadata is not in a regular image.")
        value = _metadata(stream, before.st_size)
        if _fingerprint(before) != _fingerprint(os.fstat(stream.fileno())):
            raise ProjectError("The image changed while reading AVB metadata.")
        return value


def _slice(blob, offset, size):
    if offset < 0 or size < 0 or offset + size > len(blob):
        raise ProjectError("AVB metadata contains an out-of-bounds offset.")
    return blob[offset : offset + size]


def _metadata(stream, size):
    if not _HEADER.size <= size <= _MAX_IMAGE:
        raise ProjectError("AVB image size is unsupported.")
    stream.seek(0)
    start = stream.read(4)
    offset = 0
    footer_limit = size
    if start != b"AVB0":
        stream.seek(size - 64)
        footer = stream.read(64)
        if len(footer) != 64:
            raise ProjectError("AVB image footer is truncated.")
        magic, major, minor, original, offset, length, reserved = struct.unpack(
            "!4sIIQQQ28s", footer
        )
        if (
            magic != b"AVBf"
            or major != 1
            or minor != 0
            or any(reserved)
            or not 0 < original <= offset
            or not _HEADER.size <= length <= _MAX_META
            or offset + length > size - 64
        ):
            raise ProjectError("AVB footer has unsupported or out-of-bounds fields.")
        footer_limit = offset + length
    stream.seek(offset)
    header = stream.read(_HEADER.size)
    if len(header) != _HEADER.size:
        raise ProjectError("AVB metadata header is truncated.")
    h = _HEADER.unpack(header)
    if h[0] != b"AVB0" or h[1] != 1 or h[2] > 3 or any(h[20]) or h[19][-1] != 0:
        raise ProjectError("AVB metadata header/version is unsupported.")
    auth_size, aux_size = h[3:5]
    total = _HEADER.size + auth_size + aux_size
    if auth_size % 64 or aux_size % 64 or total > _MAX_META or offset + total > footer_limit:
        raise ProjectError("AVB blocks exceed their image or metadata bound.")
    auth, aux = stream.read(auth_size), stream.read(aux_size)
    if len(auth) != auth_size or len(aux) != aux_size:
        raise ProjectError("AVB blocks are truncated.")
    digest, signature = _slice(auth, h[6], h[7]), _slice(auth, h[8], h[9])
    key = _slice(aux, h[10], h[11])
    _slice(aux, h[12], h[13])
    raw_descriptors = _slice(aux, h[14], h[15])
    algorithm = _signature(h[5], header, aux, digest, signature, key)
    descriptors = _descriptors(raw_descriptors)
    return _Metadata(algorithm, key, h[16], h[18], h[17], descriptors, offset)


def _public_key(blob):
    if len(blob) < 8:
        raise ProjectError("An AVB signing key is truncated.")
    bits, n0inv = struct.unpack("!II", blob[:8])
    if bits not in {2048, 4096, 8192} or len(blob) != 8 + bits // 4:
        raise ProjectError("An AVB signing key has unsupported geometry.")
    length = bits // 8
    modulus = int.from_bytes(blob[8 : 8 + length], "big")
    rr = int.from_bytes(blob[8 + length :], "big")
    if (
        modulus.bit_length() != bits
        or modulus % 2 != 1
        or n0inv != (-pow(modulus, -1, 1 << 32)) % (1 << 32)
        or rr != pow(2, bits * 2, modulus)
    ):
        raise ProjectError("An AVB signing key has invalid RSA/Montgomery parameters.")
    return rsa.RSAPublicNumbers(65537, modulus).public_key()


def _signature(algorithm, header, aux, digest, signature, key):
    if algorithm == 0:
        if digest or signature or key:
            raise ProjectError("Unsigned AVB metadata contains unexpected authentication fields.")
        return "NONE"
    if algorithm not in range(1, 7):
        raise ProjectError("Unsupported AVB signature algorithm.")
    bits = (2048, 4096, 8192)[(algorithm - 1) % 3]
    name = "sha256" if algorithm <= 3 else "sha512"
    if len(signature) != bits // 8 or len(digest) != hashlib.new(name).digest_size:
        raise ProjectError("AVB signature/hash size does not match its algorithm.")
    actual = hashlib.new(name, header + aux).digest()
    if not hmac.compare_digest(digest, actual):
        raise ProjectError("AVB metadata authentication hash is invalid.")
    public = _public_key(key)
    if public.key_size != bits:
        raise ProjectError("AVB signing key and algorithm sizes disagree.")
    try:
        public.verify(
            signature,
            header + aux,
            padding.PKCS1v15(),
            hashes.SHA256() if name == "sha256" else hashes.SHA512(),
        )
    except InvalidSignature as exc:
        raise ProjectError("AVB metadata signature does not verify with its embedded key.") from exc
    return f"{name.upper()}_RSA{bits}"


def _descriptors(blob):
    result = []
    offset = 0
    while offset < len(blob):
        if len(result) >= 256 or len(blob) - offset < 16:
            raise ProjectError("AVB descriptor inventory is truncated or oversized.")
        tag, following = struct.unpack("!QQ", blob[offset : offset + 16])
        if following % 8 or following > _MAX_META or offset + 16 + following > len(blob):
            raise ProjectError("AVB descriptor size is out of bounds.")
        raw = blob[offset : offset + 16 + following]
        offset += len(raw)
        if tag in {1, 2}:
            layout = _TREE if tag == 1 else _HASH
            if len(raw) < layout.size:
                raise ProjectError("AVB partition descriptor is truncated.")
            values = layout.unpack(raw[: layout.size])
            if tag == 1:
                (
                    _,
                    _,
                    version,
                    image_size,
                    tree_offset,
                    tree_size,
                    db,
                    hb,
                    fec,
                    fo,
                    fs,
                    alg,
                    nl,
                    sl,
                    dl,
                    flags,
                    reserved,
                ) = values
                if version != 1 or db != hb or db not in {4096, 8192, 16384}:
                    raise ProjectError("Unsupported AVB hashtree block geometry.")
            else:
                _, _, image_size, alg, nl, sl, dl, flags, reserved = values
                tree_offset = tree_size = db = hb = fec = fo = fs = 0
            if (
                any(reserved)
                or not 0 < image_size <= _MAX_IMAGE
                or flags & ~3
                or (tag == 2 and flags & ~1)
                or not 1 <= nl <= 64
                or not 0 <= sl <= 128
            ):
                raise ProjectError("AVB descriptor fields are unsupported.")
            name = _name(_slice(raw, layout.size, nl))
            try:
                algorithm = alg.rstrip(b"\0").decode("ascii", errors="strict")
            except UnicodeDecodeError as exc:
                raise ProjectError("AVB descriptor hash algorithm is not ASCII.") from exc
            if (
                algorithm not in {"sha1", "sha256", "sha512"}
                or dl != hashlib.new(algorithm).digest_size
            ):
                raise ProjectError(
                    "AVB persistent/unknown digests are not supported by this route."
                )
            length = layout.size + nl + sl + dl
            _padding(raw, length)
            result.append(
                _Descriptor(
                    tag,
                    raw,
                    name,
                    image_size,
                    algorithm,
                    _slice(raw, layout.size + nl, sl),
                    _slice(raw, layout.size + nl + sl, dl),
                    flags,
                    tree_offset,
                    tree_size,
                    db,
                    hb,
                    fec,
                    fo,
                    fs,
                )
            )
        elif tag == 4:
            if len(raw) < _CHAIN.size:
                raise ProjectError("AVB chain descriptor is truncated.")
            _, _, location, nl, kl, flags, reserved = _CHAIN.unpack(raw[: _CHAIN.size])
            if (
                any(reserved)
                or not 1 <= nl <= 64
                or not 1 <= location <= 31
                or flags & ~1
                or kl > 4096
            ):
                raise ProjectError("AVB chain fields are unsupported.")
            _padding(raw, _CHAIN.size + nl + kl)
            result.append(
                _Descriptor(
                    tag,
                    raw,
                    _name(_slice(raw, _CHAIN.size, nl)),
                    flags=flags,
                    rollback_location=location,
                    public_key=_slice(raw, _CHAIN.size + nl, kl),
                )
            )
        elif tag == 0:
            if len(raw) < 32:
                raise ProjectError("AVB property descriptor is truncated.")
            kl, vl = struct.unpack("!QQ", raw[16:32])
            if not 0 < kl <= 1024 or vl > 64 * 1024:
                raise ProjectError("AVB property size is unsupported.")
            _padding(raw, 32 + kl + 1 + vl + 1)
            if _slice(raw, 32 + kl, 1) != b"\0" or _slice(raw, 33 + kl + vl, 1) != b"\0":
                raise ProjectError("AVB property terminators are invalid.")
            result.append(_Descriptor(tag, raw))
        elif tag == 3:
            # Retained root metadata can contain a signed kernel command line.
            # Candidate child/partition metadata rejects it below.
            if len(raw) < 24:
                raise ProjectError("AVB kernel descriptor is truncated.")
            flags, length = struct.unpack("!II", raw[16:24])
            if flags & ~3 or length > 64 * 1024:
                raise ProjectError("Unsupported AVB kernel descriptor.")
            _padding(raw, 24 + length)
            result.append(_Descriptor(tag, raw, flags=flags))
        else:
            raise ProjectError("An unsupported AVB descriptor cannot be silently skipped.")
    names = [d.partition for d in result if d.partition]
    if len(names) != len(set(names)):
        raise ProjectError("AVB partition descriptors contain duplicate targets.")
    return tuple(result)


def _name(blob):
    try:
        value = blob.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ProjectError("AVB partition name is invalid.") from exc
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", value) or value in {".", ".."}:
        raise ProjectError("AVB partition name is unsafe.")
    return value


def _padding(raw, used):
    if used > len(raw) or len(raw) != (used + 7) // 8 * 8 or any(raw[used:]):
        raise ProjectError("AVB descriptor length or reserved padding is invalid.")


def _partition_descriptors(metadata):
    if any(d.tag not in {0, 1, 2} for d in metadata.descriptors):
        raise ProjectError("Unexpected chain or kernel instruction in candidate child/partition.")
    return {d.partition: d for d in metadata.descriptors if d.tag in {1, 2}}


def _verify_content(path, desc, vbmeta_offset):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if desc.image_size > before.st_size or (vbmeta_offset and desc.image_size > vbmeta_offset):
            raise ProjectError("AVB descriptor covers bytes outside its partition data.")
        if desc.tag == 2:
            digest = hashlib.new(desc.algorithm, desc.salt)
            remaining = desc.image_size
            while remaining:
                chunk = stream.read(min(_CHUNK, remaining))
                if not chunk:
                    raise ProjectError("AVB partition data is truncated.")
                digest.update(chunk)
                remaining -= len(chunk)
            calculated = digest.digest()
        else:
            block = desc.data_block_size
            if (
                desc.image_size % block
                or desc.tree_offset < desc.image_size
                or desc.tree_offset + desc.tree_size > vbmeta_offset
                or desc.tree_size > _MAX_TREE
            ):
                raise ProjectError("AVB Merkle tree geometry exceeds its partition bounds.")
            if desc.fec_num_roots:
                if (
                    not 1 <= desc.fec_num_roots <= 255
                    or desc.fec_offset < desc.tree_offset + desc.tree_size
                    or desc.fec_size <= 0
                    or desc.fec_offset + desc.fec_size > vbmeta_offset
                ):
                    raise ProjectError("AVB FEC geometry exceeds its partition bounds.")
            elif desc.fec_offset or desc.fec_size:
                raise ProjectError("AVB FEC bytes are present without FEC roots.")
            stride = 1 << (hashlib.new(desc.algorithm).digest_size - 1).bit_length()
            size = desc.image_size
            sizes = []
            while size > block:
                size = ((size // block * stride + block - 1) // block) * block
                sizes.append(size)
                if sum(sizes) > _MAX_TREE:
                    raise ProjectError("AVB tree calculation exceeds its memory bound.")
            if sum(sizes) != desc.tree_size:
                raise ProjectError("AVB descriptor has a false Merkle tree size.")
            source = stream
            source_size = desc.image_size
            level = b""
            if not sizes:
                calculated = hashlib.new(desc.algorithm, desc.salt + stream.read(block)).digest()
            for index, expected_size in enumerate(sizes):
                output = bytearray()
                for _ in range(source_size // block):
                    data = source.read(block)
                    if len(data) != block:
                        raise ProjectError("AVB partition data is truncated.")
                    value = hashlib.new(desc.algorithm, desc.salt + data).digest()
                    output.extend(value)
                    output.extend(b"\0" * (stride - len(value)))
                output.extend(b"\0" * (expected_size - len(output)))
                level = bytes(output)
                stream.seek(desc.tree_offset + sum(sizes[index + 1 :]))
                if stream.read(expected_size) != level:
                    raise ProjectError(
                        "Stored AVB Merkle tree bytes do not match the partition contents."
                    )
                source, source_size = io.BytesIO(level), len(level)
                calculated = hashlib.new(desc.algorithm, desc.salt + level).digest()
        if not hmac.compare_digest(calculated, desc.digest):
            raise ProjectError(
                "The actual partition hash/Merkle root differs from its AVB descriptor."
            )
        if _fingerprint(before) != _fingerprint(os.fstat(stream.fileno())):
            raise ProjectError("An image changed during AVB content verification.")


def _evidence(desc, image_hash):
    return CandidateAvbDescriptor(
        desc.partition,
        "hashtree" if desc.tag == 1 else "hash",
        hashlib.sha256(desc.raw).hexdigest(),
        image_hash,
        desc.image_size,
        desc.algorithm,
        desc.salt.hex(),
        desc.digest.hex(),
        desc.flags,
        desc.tree_offset,
        desc.tree_size,
        desc.data_block_size,
        desc.hash_block_size,
        desc.fec_num_roots,
        desc.fec_offset,
        desc.fec_size,
    )


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _seal(receipt):
    return replace(receipt, receipt_digest=_digest(asdict(replace(receipt, receipt_digest=""))))


def _decode(kind, value):
    if kind in {str, int, bool}:
        if type(value) is not kind:
            raise ProjectError("AVB receipt contains a coerced field.")
        if kind is str and len(value) > 8192 or kind is int and not 0 <= value < 2**64:
            raise ProjectError("AVB receipt field exceeds its bound.")
        return value
    if get_origin(kind) is tuple:
        if not isinstance(value, (list, tuple)) or len(value) > 256:
            raise ProjectError("AVB receipt inventory exceeds its bound.")
        return tuple(_decode(get_args(kind)[0], item) for item in value)
    if kind not in {CandidateAvbReceipt, CandidateAvbChain, CandidateAvbDescriptor}:
        raise ProjectError("Unknown AVB receipt structure.")
    if not isinstance(value, dict) or set(value) != {f.name for f in fields(kind)}:
        raise ProjectError("AVB receipt fields differ from its schema.")
    types = get_type_hints(kind)
    return kind(**{name: _decode(types[name], item) for name, item in value.items()})


def _valid_receipt(receipt):
    try:
        if _decode(CandidateAvbReceipt, asdict(receipt)) != receipt:
            return False
        digests = [
            getattr(receipt, f.name)
            for f in fields(receipt)
            if f.name.endswith(("sha256", "digest"))
        ]
        return (
            receipt.schema_version == 1
            and all(re.fullmatch(r"[a-f0-9]{64}", value) for value in digests)
            and receipt.policy_label == _POLICY
            and receipt.warnings == _WARNINGS
            and receipt.execution_authority == "none"
            and receipt.phone_changed is False
            and receipt.oem_trusted is False
            and receipt.candidate_signed is False
            and receipt.root_algorithm
            in {
                f"{algorithm}_RSA{bits}"
                for algorithm in ("SHA256", "SHA512")
                for bits in (2048, 4096, 8192)
            }
            and receipt.root_flags == 0
            and 1 <= len(receipt.root_chains) <= 32
            and len({chain.partition for chain in receipt.root_chains}) == len(receipt.root_chains)
            and all(
                re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", chain.partition)
                and 1 <= chain.rollback_index_location <= 31
                and chain.flags in {0, 1}
                and re.fullmatch(r"[a-f0-9]{64}", chain.public_key_sha256)
                for chain in receipt.root_chains
            )
            and any(
                chain.partition == "vbmeta_system" and chain.flags == 0
                for chain in receipt.root_chains
            )
            and receipt.child_algorithm == "NONE"
            and not (
                receipt.child_flags
                or receipt.child_rollback_index
                or receipt.child_rollback_index_location
            )
            and tuple(item.partition for item in receipt.descriptors) == _PARTITIONS
            and all(_valid_descriptor(item) for item in receipt.descriptors)
            and _seal(receipt) == receipt
        )
    except (ProjectError, ValueError, TypeError, AttributeError):
        return False


def _valid_descriptor(item):
    return (
        item.kind in {"hash", "hashtree"}
        and item.hash_algorithm in {"sha1", "sha256", "sha512"}
        and re.fullmatch(r"[a-f0-9]{64}", item.descriptor_sha256)
        and re.fullmatch(r"[a-f0-9]{64}", item.image_sha256)
        and 0 < item.image_size <= _MAX_IMAGE
        and len(item.salt) <= 256
        and len(item.salt) % 2 == 0
        and re.fullmatch(r"[a-f0-9]*", item.salt)
        and len(item.digest) == hashlib.new(item.hash_algorithm).digest_size * 2
        and re.fullmatch(r"[a-f0-9]+", item.digest)
        and item.flags in ({0, 1} if item.kind == "hash" else {0, 1, 2, 3})
        and item.tree_size <= _MAX_TREE
        and item.tree_offset + item.tree_size <= _MAX_IMAGE
        and item.fec_num_roots <= 255
        and item.fec_offset + item.fec_size <= _MAX_IMAGE
        and (
            item.kind == "hashtree"
            and item.data_block_size in {4096, 8192, 16384}
            and item.hash_block_size == item.data_block_size
            or item.kind == "hash"
            and not any(
                (
                    item.tree_size,
                    item.tree_offset,
                    item.data_block_size,
                    item.hash_block_size,
                    item.fec_num_roots,
                    item.fec_offset,
                    item.fec_size,
                )
            )
        )
    )
