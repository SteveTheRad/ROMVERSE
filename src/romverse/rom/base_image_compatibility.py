"""Exact OTA-to-package base identity; no image extraction or phone authority.

Payload field numbers follow AOSP system/update_engine/update_metadata.proto:
DeltaArchiveManifest partitions=13, minor_version=12, partial_update=16;
PartitionUpdate partition_name=1, old_partition_info=6, new_partition_info=7;
PartitionInfo size=1, hash=2. The bounded reader inventories identity only. It
does not implement update_engine operations or infer an installation procedure.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import stat
import struct
import zipfile
from dataclasses import asdict, dataclass, fields, replace
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import PurePosixPath

from romverse.device_packs.registry import DevicePackRegistry
from romverse.infrastructure.local_store import atomic_write_json, read_json_object
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.rom.source_installation import (
    POPSICLE_PHYSICAL_PARTITIONS,
    SourceInstallationRecipe,
    SourceInstallationService,
    _safe_member,
)

MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_SIGNATURE_BYTES = 64 * 1024
MAX_PARTITIONS = 256
MAX_FIELDS = 100_000
MAX_PARTITION_BYTES = 128 * 1024**3
MAX_PAYLOAD_BYTES = 128 * 1024**3
MAX_ARCHIVE_BYTES = 256 * 1024**3
CHUNK_SIZE = 4 * 1024 * 1024
REQUIRED_PARTITIONS = (*POPSICLE_PHYSICAL_PARTITIONS, "vbmeta")


@dataclass(frozen=True, slots=True)
class OtaPartitionIdentity:
    partition: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class BaseImageComparison:
    partition: str
    member: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class BaseImageCompatibilityReceipt:
    schema_version: int
    receipt_digest: str
    created_at: str
    build_project_id: str
    source_sha256: str
    payload_sha256: str
    payload_size_bytes: int
    metadata_sha256: str
    pack_id: str
    pack_sha256: str
    contract_id: str
    contract_digest: str
    procedure_project_id: str
    procedure_source_sha256: str
    procedure_recipe_digest: str
    procedure_wipe: bool
    procedure_reboot: bool
    script_sha256: str
    comparisons: tuple[BaseImageComparison, ...]
    phone_changed: bool = False
    execution_authority: str = "none"


class BaseImageCompatibilityService:
    """Freshly measure sources and persist a sealed, non-authorizing receipt."""

    FORMAT = "romverse.base-image-compatibility"
    SCHEMA_VERSION = 1
    RECEIPT_NAME = "base-image-compatibility.romverse"
    MAX_RECEIPT_BYTES = 128 * 1024
    MAX_ZIP_MEMBERS = 10_000
    MAX_PROPERTIES_BYTES = 16 * 1024

    def __init__(self, store: RomProjectStore, registry: DevicePackRegistry | None = None) -> None:
        self.store = store
        self.registry = (
            registry
            if registry is not None
            else DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
        )

    def prepare(
        self, build_project_id: str, procedure_recipe: SourceInstallationRecipe
    ) -> BaseImageCompatibilityReceipt:
        receipt = self._derive(build_project_id, procedure_recipe, datetime.now(UTC).isoformat())
        try:
            atomic_write_json(
                self.store.projects_root / build_project_id / self.RECEIPT_NAME,
                {"format": self.FORMAT, **asdict(receipt)},
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
        except (OSError, ValueError, TypeError) as exc:
            raise ProjectError(
                "The private base-image evidence could not be saved safely."
            ) from exc
        return receipt

    def verify(
        self,
        receipt: BaseImageCompatibilityReceipt,
        procedure_recipe: SourceInstallationRecipe,
    ) -> BaseImageCompatibilityReceipt:
        if type(receipt) is not BaseImageCompatibilityReceipt:
            raise ProjectError("The base-image compatibility receipt is invalid.")
        try:
            valid = _valid_receipt(receipt, receipt.build_project_id) and _seal(receipt) == receipt
        except (TypeError, ValueError, AttributeError, ProjectError) as exc:
            raise ProjectError("The base-image compatibility receipt is malformed.") from exc
        if not valid:
            raise ProjectError("The base-image compatibility receipt is invalid.")
        saved = self.load(receipt.build_project_id)
        try:
            matches = saved is not None and _encoded(asdict(saved)) == _encoded(asdict(receipt))
        except (TypeError, ValueError) as exc:
            raise ProjectError("The base-image compatibility receipt is malformed.") from exc
        if not matches:
            raise ProjectError("The service-owned base-image evidence is missing or changed.")
        current = self._derive(receipt.build_project_id, procedure_recipe, receipt.created_at)
        if current != receipt:
            raise ProjectError(
                "The OTA, build contract, procedure, or base images changed. Prepare fresh evidence."
            )
        return current

    def load(self, build_project_id: str) -> BaseImageCompatibilityReceipt | None:
        """Load strict saved metadata; call verify before using its comparisons."""
        self.store.get(build_project_id)
        try:
            data = read_json_object(
                self.store.projects_root / build_project_id / self.RECEIPT_NAME,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
            if (
                set(data)
                != {"format", *(item.name for item in fields(BaseImageCompatibilityReceipt))}
                or data.pop("format") != self.FORMAT
            ):
                return None
            rows = data.pop("comparisons")
            if (
                not isinstance(rows, list)
                or len(rows) != len(REQUIRED_PARTITIONS)
                or any(
                    not isinstance(row, dict)
                    or set(row) != {item.name for item in fields(BaseImageComparison)}
                    for row in rows
                )
            ):
                return None
            receipt = BaseImageCompatibilityReceipt(
                **data, comparisons=tuple(BaseImageComparison(**row) for row in rows)
            )
            if not _valid_receipt(receipt, build_project_id) or _seal(receipt) != receipt:
                return None
            return receipt
        except (OSError, ValueError, TypeError, KeyError, ProjectError):
            return None

    def _derive(self, build_project_id, procedure_recipe, created_at):
        project = self.store.get(build_project_id)
        matches = tuple(
            item for item in self.registry.packs if item.pack_id == project.device_pack_id
        )
        if len(matches) != 1 or matches[0].build_contract is None or project.original is None:
            raise ProjectError("Base-image comparison needs one exact source-bound build contract.")
        pack = matches[0]
        contract = pack.build_contract
        if (
            project.original.sha256 != contract.source.archive_sha256
            or not _sha256_value(contract.source.payload_sha256)
            or not _sha256_value(pack.sha256)
        ):
            raise ProjectError("The protected OTA does not match the exact build contract.")

        # A caller's dataclass is not source evidence: re-read the complete package
        # through the supported adapter, including every declared image checksum.
        source_service = SourceInstallationService(self.store)
        recipe = source_service.verify(procedure_recipe)
        procedure_before = source_service._fingerprint(recipe.archive_path.stat())
        identities = {value.casefold() for value in pack.product_patterns}
        manufacturers = {value.casefold() for value in pack.manufacturers}
        if (
            recipe.expected_product.casefold() not in identities
            or recipe.expected_manufacturer.casefold() not in manufacturers
        ):
            raise ProjectError("The build contract and source procedure target different devices.")

        original_path = self.store.original_path(build_project_id)
        source_service._source_path(original_path)
        try:
            descriptor = os.open(original_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, "rb") as stream:
                before = os.fstat(stream.fileno())
                if (
                    not stat.S_ISREG(before.st_mode)
                    or before.st_size != project.original.size_bytes
                    or not 0 < before.st_size <= MAX_ARCHIVE_BYTES
                ):
                    raise ProjectError("The protected OTA size changed or exceeds its safe bound.")
                if _hash_stream(stream, before.st_size) != project.original.sha256:
                    raise ProjectError("The protected OTA SHA-256 changed after import.")
                stream.seek(0)
                with zipfile.ZipFile(stream) as archive:
                    partitions, payload_sha, payload_size, metadata_sha = self._read_ota(
                        archive, contract.source.payload_sha256
                    )
                if source_service._fingerprint(before) != source_service._fingerprint(
                    os.fstat(stream.fileno())
                ) or source_service._fingerprint(before) != source_service._fingerprint(
                    original_path.stat()
                ):
                    raise ProjectError("The protected OTA changed while it was being measured.")
            if procedure_before != source_service._fingerprint(recipe.archive_path.stat()):
                raise ProjectError("The source procedure changed during base-image measurement.")
        except ProjectError:
            raise
        except (OSError, zipfile.BadZipFile, RuntimeError, EOFError, struct.error) as exc:
            raise ProjectError(
                "The protected OTA could not be read safely as a full payload ZIP."
            ) from exc

        records = {item.partition: item for item in partitions}
        images = {item.member: item for item in recipe.images}
        writes = {step.partition: step for step in recipe.steps if step.action == "flash"}
        comparisons = []
        for name in REQUIRED_PARTITIONS:
            record = records.get(name)
            if record is None:
                raise ProjectError(f"The exact OTA is missing required base partition {name}.")
            image = images[writes[f"{name}_a"].image_member]
            if (
                image.size_bytes != record.size_bytes
                or image.sha256 != record.sha256
                or image.expanded_size_bytes != image.size_bytes
            ):
                raise ProjectError(
                    f"Base image {name} does not match the exact OTA's complete-image size and SHA-256."
                )
            comparisons.append(
                BaseImageComparison(name, image.member, record.sha256, record.size_bytes)
            )
        if records["vbmeta"].sha256 != contract.top_level_vbmeta_sha256:
            raise ProjectError("The OTA root vbmeta does not match the exact build contract.")
        latest = self.store.get(build_project_id)
        procedure_project = self.store.get(recipe.project_id)
        if (
            latest.original != project.original
            or latest.device_pack_id != project.device_pack_id
            or procedure_project.original is None
            or procedure_project.original.sha256 != recipe.source_sha256
        ):
            raise ProjectError("The project source or build contract changed during measurement.")
        return _seal(
            BaseImageCompatibilityReceipt(
                self.SCHEMA_VERSION,
                "",
                created_at,
                build_project_id,
                project.original.sha256,
                payload_sha,
                payload_size,
                metadata_sha,
                pack.pack_id,
                pack.sha256,
                contract.contract_id,
                _digest(asdict(contract)),
                recipe.project_id,
                recipe.source_sha256,
                recipe.recipe_digest,
                recipe.wipe,
                recipe.reboot,
                recipe.script_sha256,
                tuple(comparisons),
            )
        )

    def _read_ota(self, archive, expected_payload_sha256):
        members = {}
        inventory = archive.infolist()
        if not 0 < len(inventory) <= self.MAX_ZIP_MEMBERS:
            raise ProjectError("The OTA has an empty or oversized member inventory.")
        for item in inventory:
            name = _safe_member(item.filename.rstrip("/"))
            mode = item.external_attr >> 16
            if (
                name in members
                or item.flag_bits & 1
                or stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}
                or (stat.S_ISDIR(mode) and not item.is_dir())
            ):
                raise ProjectError(
                    "The OTA contains ambiguous, linked, special, or encrypted members."
                )
            members[name] = item
        payloads = [
            name for name in members if PurePosixPath(name).name.casefold() == "payload.bin"
        ]
        properties = [
            name
            for name in members
            if PurePosixPath(name).name.casefold() == "payload_properties.txt"
        ]
        if (
            len(payloads) != 1
            or len(properties) != 1
            or PurePosixPath(payloads[0]).parent != PurePosixPath(properties[0]).parent
        ):
            raise ProjectError("Choose one unambiguous OTA payload and its paired properties.")
        payload, prop_member = members[payloads[0]], members[properties[0]]
        if payload.is_dir() or not 24 <= payload.file_size <= MAX_PAYLOAD_BYTES:
            raise ProjectError("The OTA payload size is outside the supported bound.")
        prop_bytes = SourceInstallationService._bounded_read(
            archive, prop_member, self.MAX_PROPERTIES_BYTES
        )
        props = _properties(prop_bytes)
        payload_size = _positive_size(props["FILE_SIZE"], MAX_PAYLOAD_BYTES)
        if (
            payload_size != payload.file_size
            or _property_hash(props["FILE_HASH"]) != expected_payload_sha256
        ):
            raise ProjectError(
                "The declared OTA payload identity differs from the exact build contract."
            )
        with archive.open(payload) as stream:
            header = stream.read(24)
            if len(header) != 24:
                raise ProjectError("The OTA payload header is truncated.")
            magic, major, manifest_size, signature_size = struct.unpack(">4sQQI", header)
            if magic != b"CrAU" or major != 2:
                raise ProjectError(
                    "Only supported major-version-2 full OTA payloads can supply base evidence."
                )
            if (
                not 0 < manifest_size <= MAX_MANIFEST_BYTES
                or signature_size > MAX_SIGNATURE_BYTES
                or 24 + manifest_size + signature_size > payload_size
            ):
                raise ProjectError(
                    "The OTA metadata framing is truncated or exceeds its safe bounds."
                )
            manifest = stream.read(manifest_size)
            if len(manifest) != manifest_size:
                raise ProjectError("The OTA partition manifest is truncated.")
            metadata = header + manifest
            metadata_sha = hashlib.sha256(metadata).hexdigest()
            if (
                _positive_size(props["METADATA_SIZE"], MAX_MANIFEST_BYTES + 24) != len(metadata)
                or _property_hash(props["METADATA_HASH"]) != metadata_sha
            ):
                raise ProjectError("The OTA metadata hash or size does not match its properties.")
            partitions = _parse_manifest(manifest)
            digest = hashlib.sha256(metadata)
            remaining = payload_size - len(metadata)
            while remaining:
                chunk = stream.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    raise ProjectError("The OTA payload is truncated.")
                digest.update(chunk)
                remaining -= len(chunk)
            if stream.read(1) or digest.hexdigest() != expected_payload_sha256:
                raise ProjectError(
                    "The fresh OTA payload SHA-256 differs from the exact build contract."
                )
        return partitions, digest.hexdigest(), payload_size, metadata_sha


def _varint(data, position):
    value = 0
    for index in range(10):
        if position >= len(data):
            raise ProjectError("The OTA manifest contains a truncated protobuf integer.")
        byte = data[position]
        position += 1
        if index == 9 and byte > 1:
            raise ProjectError("The OTA manifest contains an overflowing protobuf integer.")
        value |= (byte & 127) << (7 * index)
        if not byte & 128:
            if index and byte == 0:
                raise ProjectError("The OTA manifest contains a non-canonical protobuf integer.")
            return value, position
    raise ProjectError("The OTA manifest contains an overlong protobuf integer.")


def _wire_fields(data, depth):
    if not isinstance(data, bytes) or not 0 <= depth <= 2 or len(data) > MAX_MANIFEST_BYTES:
        raise ProjectError("The OTA manifest exceeds the bounded protobuf reader.")
    position = 0
    count = 0
    while position < len(data):
        count += 1
        if count > MAX_FIELDS:
            raise ProjectError("The OTA manifest contains too many protobuf fields.")
        key, position = _varint(data, position)
        number, wire = key >> 3, key & 7
        if not 1 <= number <= 536870911:
            raise ProjectError("The OTA manifest contains an invalid protobuf field number.")
        if wire == 0:
            value, position = _varint(data, position)
        elif wire in {1, 2, 5}:
            if wire == 2:
                size, position = _varint(data, position)
            else:
                size = 8 if wire == 1 else 4
            end = position + size
            if size > MAX_MANIFEST_BYTES or end > len(data):
                raise ProjectError(
                    "The OTA manifest contains a truncated or oversized protobuf field."
                )
            value, position = data[position:end], end
        else:
            raise ProjectError("The OTA manifest uses an unsupported protobuf wire type.")
        yield number, wire, value


def _selected_fields(data, selected, depth):
    result = {}
    for number, wire, value in _wire_fields(data, depth):
        if number in selected:
            if number in result or wire != selected[number]:
                raise ProjectError(
                    "The OTA manifest contains duplicate fields or incorrect wire types."
                )
            result[number] = value
    return result


def _parse_manifest(data: bytes) -> tuple[OtaPartitionIdentity, ...]:
    """Parse identities only, without interpreting or executing OTA operations."""
    partitions = {}
    scalar = {}
    for number, wire, value in _wire_fields(data, 0):
        if number in {12, 16}:
            if number in scalar or wire != 0:
                raise ProjectError("The OTA manifest has ambiguous full/delta declarations.")
            scalar[number] = value
            if value != 0:
                raise ProjectError("Delta and partial OTA payloads cannot supply a complete base.")
        elif number == 13:
            if wire != 2 or len(partitions) >= MAX_PARTITIONS:
                raise ProjectError("The OTA partition inventory is malformed or exceeds its bound.")
            record = _partition_fields(value)
            if set(record) != {1, 7}:
                raise ProjectError(
                    "The OTA partition lacks new identity or requires an old delta source."
                )
            try:
                name = record[1].decode("ascii")
            except UnicodeDecodeError as exc:
                raise ProjectError("The OTA partition name is malformed.") from exc
            if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,63}", name) or name in partitions:
                raise ProjectError("The OTA partition names are invalid or duplicated.")
            info = _selected_fields(record[7], {1: 0, 2: 2}, 2)
            if set(info) != {1, 2} or not 0 < info[1] <= MAX_PARTITION_BYTES or len(info[2]) != 32:
                raise ProjectError(f"The OTA partition {name} lacks a bounded size and SHA-256.")
            partitions[name] = OtaPartitionIdentity(name, info[1], info[2].hex())
    if not partitions:
        raise ProjectError("The OTA partition inventory is empty.")
    return tuple(partitions.values())


def _partition_fields(data):
    record = {}
    operations = 0
    for number, wire, value in _wire_fields(data, 1):
        if number in {1, 6, 7}:
            if number in record or wire != 2:
                raise ProjectError(
                    "The OTA partition has duplicate fields or incorrect wire types."
                )
            record[number] = value
        elif number == 8:
            if wire != 2:
                raise ProjectError("The OTA operation list is malformed.")
            # InstallOperation.type=1, src_extents=4, src_length=5. Inventory
            # source-free full operations only; never implement their execution.
            operation = _selected_fields(value, {1: 0, 4: 2, 5: 0}, 2)
            if set(operation) != {1} or operation[1] not in {0, 1, 6, 7, 8}:
                raise ProjectError("The OTA contains delta-dependent or unsupported operations.")
            operations += 1
    if not operations:
        raise ProjectError("The full OTA partition has no source-independent image operations.")
    return record


def _properties(data):
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ProjectError("OTA payload properties must be bounded ASCII text.") from exc
    result = {}
    for line in text.splitlines():
        key, separator, value = line.partition("=")
        if (
            not separator
            or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", key)
            or key in result
            or not value
            or any(ord(char) < 32 or ord(char) > 126 for char in value)
            or len(result) >= 64
        ):
            raise ProjectError("OTA payload properties are malformed or duplicated.")
        result[key] = value
    if not {"FILE_HASH", "FILE_SIZE", "METADATA_HASH", "METADATA_SIZE"}.issubset(result):
        raise ProjectError("OTA payload properties are missing required identity fields.")
    return result


def _property_hash(value):
    try:
        decoded = base64.b64decode(value, validate=True)
        if len(decoded) != 32 or base64.b64encode(decoded).decode("ascii") != value:
            raise ValueError("not a canonical SHA-256")
        return decoded.hex()
    except (ValueError, binascii.Error) as exc:
        raise ProjectError("OTA payload properties contain an invalid SHA-256.") from exc


def _positive_size(value, maximum):
    if not re.fullmatch(r"[1-9][0-9]{0,19}", value):
        raise ProjectError("OTA payload properties contain an invalid size.")
    size = int(value)
    if size > maximum:
        raise ProjectError("OTA payload properties exceed their size boundary.")
    return size


def _hash_stream(stream, expected_size):
    digest = hashlib.sha256()
    remaining = expected_size
    while remaining:
        chunk = stream.read(min(CHUNK_SIZE, remaining))
        if not chunk:
            raise ProjectError("The protected OTA is truncated.")
        remaining -= len(chunk)
        digest.update(chunk)
    if stream.read(1):
        raise ProjectError("The protected OTA size changed while hashing.")
    return digest.hexdigest()


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _digest(value):
    return hashlib.sha256(_encoded(value)).hexdigest()


def _seal(receipt):
    payload = asdict(receipt)
    payload.pop("receipt_digest")
    return replace(receipt, receipt_digest=_digest(payload))


def _sha256_value(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _valid_receipt(receipt, project_id):
    timestamp = datetime.fromisoformat(receipt.created_at)
    return (
        type(receipt.schema_version) is int
        and receipt.schema_version == BaseImageCompatibilityService.SCHEMA_VERSION
        and isinstance(receipt.build_project_id, str)
        and re.fullmatch(r"[a-z0-9-]{1,64}", receipt.build_project_id) is not None
        and receipt.build_project_id == project_id
        and isinstance(receipt.procedure_project_id, str)
        and re.fullmatch(r"[a-z0-9-]{1,64}", receipt.procedure_project_id) is not None
        and timestamp.tzinfo is not None
        and timestamp.utcoffset() is not None
        and type(receipt.payload_size_bytes) is int
        and 24 <= receipt.payload_size_bytes <= MAX_PAYLOAD_BYTES
        and receipt.phone_changed is False
        and receipt.execution_authority == "none"
        and type(receipt.procedure_wipe) is bool
        and type(receipt.procedure_reboot) is bool
        and all(
            isinstance(value, str) and re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,127}", value)
            for value in (receipt.pack_id, receipt.contract_id)
        )
        and all(
            _sha256_value(getattr(receipt, name))
            for name in (
                "receipt_digest",
                "source_sha256",
                "payload_sha256",
                "metadata_sha256",
                "pack_sha256",
                "contract_digest",
                "procedure_source_sha256",
                "procedure_recipe_digest",
                "script_sha256",
            )
        )
        and type(receipt.comparisons) is tuple
        and all(type(item) is BaseImageComparison for item in receipt.comparisons)
        and tuple(item.partition for item in receipt.comparisons) == REQUIRED_PARTITIONS
        and all(
            isinstance(item.member, str)
            and bool(_safe_member(item.member))
            and _sha256_value(item.sha256)
            and type(item.size_bytes) is int
            and 0 < item.size_bytes <= MAX_PARTITION_BYTES
            for item in receipt.comparisons
        )
    )
