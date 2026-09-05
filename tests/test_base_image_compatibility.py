from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
import struct
import zipfile
from dataclasses import asdict, replace
from importlib.resources import files
from types import SimpleNamespace

import pytest

from romverse.device_packs.registry import DevicePackRegistry
from romverse.rom.base_image_compatibility import (
    MAX_MANIFEST_BYTES,
    MAX_PARTITION_BYTES,
    MAX_PARTITIONS,
    MAX_SIGNATURE_BYTES,
    REQUIRED_PARTITIONS,
    BaseImageCompatibilityService,
    _digest,
    _parse_manifest,
    _wire_fields,
)
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.rom.source_installation import SourceInstallationService
from tests.test_source_installation import _files, _package


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _varint(value):
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def _integer(number, value):
    return _varint(number << 3) + _varint(value)


def _bytes(number, value):
    return _varint((number << 3) | 2) + _varint(len(value)) + value


def _partition(name, content=b"tiny image", *, info=None, extra=b"", operation=None):
    info = (
        _integer(1, len(content)) + _bytes(2, hashlib.sha256(content).digest())
        if info is None
        else info
    )
    operation = _integer(1, 0) if operation is None else operation
    return _bytes(
        13,
        _bytes(1, name.encode()) + _bytes(7, info) + _bytes(8, operation) + extra,
    )


def _fixture(
    tmp_path,
    *,
    manifest=None,
    properties=None,
    header=None,
    payload_mutation=None,
    ota_extras=(),
    procedure_prefix="outputs/popsicle",
    image_contents=None,
):
    image_contents = _files() if image_contents is None else image_contents
    package = _package(tmp_path, files=image_contents, prefix=procedure_prefix)
    manifest = (
        _integer(12, 0)
        + _integer(16, 0)
        + b"".join(
            _partition(name, image_contents[f"images/{name}.img"]) for name in REQUIRED_PARTITIONS
        )
        if manifest is None
        else manifest
    )
    header = struct.pack(">4sQQI", b"CrAU", 2, len(manifest), 3) if header is None else header
    metadata = header + manifest
    payload = metadata + b"sig" + b"inert payload operation data"
    props = {
        "FILE_HASH": base64.b64encode(hashlib.sha256(payload).digest()).decode(),
        "FILE_SIZE": str(len(payload)),
        "METADATA_HASH": base64.b64encode(hashlib.sha256(metadata).digest()).decode(),
        "METADATA_SIZE": str(len(metadata)),
    }
    if properties is not None:
        props.update(properties)
    prop_bytes = "".join(f"{key}={value}\n" for key, value in props.items()).encode()
    original_payload = payload
    if payload_mutation is not None:
        payload = payload_mutation(payload)
    ota = tmp_path / "popsicle-ota_full-OS4.0.0.23.XPBCNXM.zip"
    with zipfile.ZipFile(ota, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("payload.bin", payload)
        archive.writestr("payload_properties.txt", prop_bytes)
        for name, data in ota_extras:
            archive.writestr(name, data)
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    pack = next(item for item in registry.packs if item.build_contract is not None)
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Tiny OTA build", pack.pack_id).project_id, ota)
    procedure = store.import_original(store.create("Tiny source procedure").project_id, package)
    recipe = SourceInstallationService(store).prepare(procedure.project_id)
    contract = replace(
        pack.build_contract,
        source=replace(
            pack.build_contract.source,
            archive_sha256=project.original.sha256,
            payload_sha256=_sha(original_payload),
        ),
        top_level_vbmeta_sha256=_sha(image_contents["images/vbmeta.img"]),
    )
    pack = replace(pack, build_contract=contract)
    registry = DevicePackRegistry((pack,))
    return SimpleNamespace(
        store=store,
        project=project,
        procedure=procedure,
        recipe=recipe,
        registry=registry,
        service=BaseImageCompatibilityService(store, registry),
        payload=original_payload,
        metadata=metadata,
        manifest=manifest,
        images=image_contents,
    )


def test_fresh_exact_base_comparison_persists_private_non_authorizing_evidence(tmp_path):
    context = _fixture(tmp_path)
    receipt = context.service.prepare(context.project.project_id, context.recipe)
    assert tuple(row.partition for row in receipt.comparisons) == REQUIRED_PARTITIONS
    assert len(receipt.comparisons) == 48
    for row in receipt.comparisons:
        content = context.images[f"images/{row.partition}.img"]
        assert row.member == f"outputs/popsicle/images/{row.partition}.img"
        assert row.sha256 == _sha(content)
        assert row.size_bytes == len(content)
    assert receipt.source_sha256 == context.project.original.sha256
    assert receipt.payload_sha256 == _sha(context.payload)
    assert receipt.metadata_sha256 == _sha(context.metadata)
    assert receipt.procedure_source_sha256 == context.procedure.original.sha256
    assert receipt.procedure_recipe_digest == context.recipe.recipe_digest
    assert receipt.procedure_wipe is False and receipt.procedure_reboot is True
    assert receipt.execution_authority == "none" and receipt.phone_changed is False
    assert context.service.load(context.project.project_id) == receipt
    path = context.store.projects_root / context.project.project_id / context.service.RECEIPT_NAME
    saved = path.read_bytes()
    before = path.stat()
    if os.name != "nt":
        assert stat.S_IMODE(before.st_mode) == 0o600
    assert context.service.verify(receipt, context.recipe) == receipt
    assert path.read_bytes() == saved and path.stat().st_mtime_ns == before.st_mtime_ns
    assert not context.store.working_root.exists()


@pytest.mark.parametrize("prefix", ["", "./outputs/popsicle"])
def test_exact_source_member_names_survive_safe_normalization(tmp_path, prefix):
    context = _fixture(tmp_path, procedure_prefix=prefix)
    receipt = context.service.prepare(context.project.project_id, context.recipe)
    assert receipt.comparisons[0].member == (
        f"{prefix}/images/abl.img" if prefix else "images/abl.img"
    )
    assert context.service.verify(receipt, context.recipe) == receipt


def test_optional_registry_loads_packaged_contracts_without_tools_or_transport(tmp_path):
    service = BaseImageCompatibilityService(RomProjectStore(tmp_path))
    assert any(pack.build_contract is not None for pack in service.registry.packs)


@pytest.mark.parametrize("name", ["abl", "boot", "modem", "vbmeta"])
def test_missing_named_ota_base_partition_is_not_a_partial_success(tmp_path, name):
    images = _files()
    manifest = b"".join(
        _partition(part, images[f"images/{part}.img"])
        for part in REQUIRED_PARTITIONS
        if part != name
    )
    context = _fixture(tmp_path, manifest=manifest)
    with pytest.raises(ProjectError, match=f"missing required base partition {name}"):
        context.service.prepare(context.project.project_id, context.recipe)
    assert context.service.load(context.project.project_id) is None


@pytest.mark.parametrize("change", ["hash", "size"])
def test_declared_ota_and_actual_package_image_mismatch_is_named(tmp_path, change):
    images = _files()
    original = images["images/boot.img"]
    info = _integer(1, len(original) + (change == "size")) + _bytes(
        2, b"x" * 32 if change == "hash" else hashlib.sha256(original).digest()
    )
    manifest = b"".join(
        _partition(name, images[f"images/{name}.img"], info=info if name == "boot" else None)
        for name in REQUIRED_PARTITIONS
    )
    context = _fixture(tmp_path, manifest=manifest)
    with pytest.raises(ProjectError, match="Base image boot"):
        context.service.prepare(context.project.project_id, context.recipe)


@pytest.mark.parametrize(
    "manifest",
    [
        b"",
        _integer(12, 1) + _partition("boot"),
        _integer(16, 1) + _partition("boot"),
        _integer(16, 2) + _partition("boot"),
        _integer(12, 0) * 2 + _partition("boot"),
        _bytes(12, b"\0") + _partition("boot"),
        _integer(16, 0) * 2 + _partition("boot"),
        _partition("boot") * 2,
        _partition("../boot"),
        _partition("Boot"),
        _partition("boot", extra=_bytes(1, b"boot")),
        _partition("boot", extra=_bytes(6, b"")),
        _partition("boot", info=_integer(1, 0) + _bytes(2, b"h" * 32)),
        _partition("boot", info=_integer(1, MAX_PARTITION_BYTES + 1) + _bytes(2, b"h" * 32)),
        _partition("boot", info=_integer(1, 4)),
        _partition("boot", info=_integer(1, 4) + _bytes(2, b"h" * 31)),
        _partition("boot", info=_integer(1, 4) * 2 + _bytes(2, b"h" * 32)),
        _partition("boot", info=_bytes(1, b"4") + _bytes(2, b"h" * 32)),
        _partition("boot", operation=_integer(1, 4)),
        _partition("boot", operation=_integer(1, 10)),
        _partition("boot", operation=_integer(1, 0) + _bytes(4, b"")),
        _partition("boot", operation=_integer(1, 0) + _integer(5, 0)),
        _partition("boot", operation=b""),
        _bytes(13, _bytes(1, b"boot") + _bytes(7, b"")),
        b"\x00",
        b"\x0b",
        b"\x0f",
        b"\x80",
        b"\x80\x00",
        b"\x80" * 9 + b"\x02",
        b"\x0a\xff\xff\xff\xff\x7f",
        b"\x09\x00",
        b"\x0d\x00",
    ],
)
def test_bounded_manifest_rejects_ambiguous_delta_or_malformed_evidence(manifest):
    with pytest.raises(ProjectError):
        _parse_manifest(manifest)


def test_manifest_bounded_counts_and_lengths_are_enforced(monkeypatch):
    with pytest.raises(ProjectError, match="partition inventory"):
        _parse_manifest(b"".join(_partition(f"p{index}") for index in range(MAX_PARTITIONS + 1)))
    with pytest.raises(ProjectError, match="bounded protobuf reader"):
        _parse_manifest(b"\0" * (MAX_MANIFEST_BYTES + 1))
    with pytest.raises(ProjectError, match="bounded protobuf reader"):
        tuple(_wire_fields(b"", 3))
    monkeypatch.setattr("romverse.rom.base_image_compatibility.MAX_FIELDS", 2)
    with pytest.raises(ProjectError, match="too many protobuf fields"):
        _parse_manifest(_integer(100, 0) * 3)


def test_unknown_non_executable_fields_are_skipped_with_wire_bounds():
    data = (
        _integer(100, 25)
        + _bytes(101, b"unknown bounded field")
        + _varint((102 << 3) | 1)
        + b"a" * 8
        + _varint((103 << 3) | 5)
        + b"b" * 4
        + _partition("boot")
    )
    rows = _parse_manifest(data)
    assert len(rows) == 1 and rows[0].partition == "boot"


@pytest.mark.parametrize(
    "properties",
    [
        {"FILE_HASH": "bad"},
        {"FILE_HASH": base64.b64encode(b"x" * 32).decode()},
        {"FILE_SIZE": "0"},
        {"FILE_SIZE": "-1"},
        {"FILE_SIZE": "99999999999999999999"},
        {"METADATA_HASH": "="},
        {"METADATA_HASH": base64.b64encode(b"x" * 32).decode()},
        {"METADATA_SIZE": "1"},
        {"METADATA_SIZE": "01"},
        {"EXTRA": "value\nFILE_SIZE=10"},
        {"EXTRA": "value\x00"},
        {"EXTRA": ""},
    ],
)
def test_payload_properties_do_not_replace_fresh_source_identity(tmp_path, properties):
    context = _fixture(tmp_path, properties=properties)
    with pytest.raises(ProjectError):
        context.service.prepare(context.project.project_id, context.recipe)


@pytest.mark.parametrize(
    "header",
    [
        struct.pack(">4sQQI", b"NOPE", 2, 10, 0),
        struct.pack(">4sQQI", b"CrAU", 1, 10, 0),
        struct.pack(">4sQQI", b"CrAU", 3, 10, 0),
        struct.pack(">4sQQI", b"CrAU", 2, 0, 0),
        struct.pack(">4sQQI", b"CrAU", 2, MAX_MANIFEST_BYTES + 1, 0),
        struct.pack(">4sQQI", b"CrAU", 2, 10, MAX_SIGNATURE_BYTES + 1),
        struct.pack(">4sQQI", b"CrAU", 2, 100000, 0),
    ],
)
def test_payload_header_bounds_and_version_are_enforced(tmp_path, header):
    context = _fixture(tmp_path, header=header)
    with pytest.raises(ProjectError):
        context.service.prepare(context.project.project_id, context.recipe)


def test_payload_bytes_after_metadata_are_freshly_hashed(tmp_path):
    context = _fixture(tmp_path, payload_mutation=lambda data: data[:-1] + bytes([data[-1] ^ 1]))
    with pytest.raises(ProjectError, match="fresh OTA payload SHA-256"):
        context.service.prepare(context.project.project_id, context.recipe)


@pytest.mark.parametrize(
    "extras",
    [
        (("./payload.bin", b"ambiguous"),),
        (("nested/PAYLOAD.BIN", b"ambiguous"),),
        (("nested/payload_properties.txt", b"ambiguous"),),
        (("../escape", b"unsafe"),),
        (("/absolute", b"unsafe"),),
        (("back\\slash", b"unsafe"),),
    ],
)
def test_ota_archive_ambiguity_and_unsafe_members_are_rejected(tmp_path, extras):
    context = _fixture(tmp_path, ota_extras=extras)
    with pytest.raises(ProjectError):
        context.service.prepare(context.project.project_id, context.recipe)


def _change_same_stat(path):
    before = path.stat()
    path.chmod(0o600)
    with path.open("r+b") as stream:
        stream.seek(50)
        byte = stream.read(1)
        stream.seek(50)
        stream.write(bytes([byte[0] ^ 1]))
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))


@pytest.mark.parametrize("target", ["ota", "procedure"])
def test_fresh_verify_rejects_source_mutation_with_restored_size_and_mtime(tmp_path, target):
    context = _fixture(tmp_path)
    receipt = context.service.prepare(context.project.project_id, context.recipe)
    project = context.project if target == "ota" else context.procedure
    _change_same_stat(context.store.original_path(project.project_id))
    with pytest.raises(ProjectError, match="SHA-256 changed"):
        context.service.verify(receipt, context.recipe)


@pytest.mark.parametrize("change", ["partition", "hash", "slot", "source", "script"])
def test_caller_recipe_dataclasses_cannot_supply_invented_evidence(tmp_path, change):
    context = _fixture(tmp_path)
    recipe = context.recipe
    if change == "partition":
        recipe = replace(recipe, steps=(replace(recipe.steps[0], slot="b"), *recipe.steps[1:]))
    elif change == "hash":
        recipe = replace(
            recipe, images=(replace(recipe.images[0], sha256="f" * 64), *recipe.images[1:])
        )
    elif change == "slot":
        recipe = replace(recipe, target_slot="b")
    elif change == "source":
        recipe = replace(recipe, source_sha256="f" * 64)
    else:
        recipe = replace(recipe, script_sha256="f" * 64)
    with pytest.raises(ProjectError, match="changed"):
        context.service.prepare(context.project.project_id, recipe)


@pytest.mark.parametrize(
    "change", ["source", "payload", "root", "product", "manufacturer", "missing", "duplicate"]
)
def test_current_build_contract_and_target_are_not_assumed_from_version_text(tmp_path, change):
    context = _fixture(tmp_path)
    pack = context.registry.packs[0]
    contract = pack.build_contract
    if change in {"source", "payload"}:
        source = replace(
            contract.source,
            **{"archive_sha256" if change == "source" else "payload_sha256": "f" * 64},
        )
        pack = replace(pack, build_contract=replace(contract, source=source))
    elif change == "root":
        pack = replace(pack, build_contract=replace(contract, top_level_vbmeta_sha256="f" * 64))
    elif change == "product":
        pack = replace(pack, product_patterns=("other",))
    elif change == "manufacturer":
        pack = replace(pack, manufacturers=("other",))
    packs = () if change == "missing" else (pack, pack) if change == "duplicate" else (pack,)
    service = BaseImageCompatibilityService(context.store, DevicePackRegistry(packs))
    with pytest.raises(ProjectError):
        service.prepare(context.project.project_id, context.recipe)


@pytest.mark.parametrize(
    "mutation", ["hash", "authority", "size_type", "extra", "timestamp", "comparison", "wipe_type"]
)
def test_saved_receipt_strictly_rejects_corruption_even_with_recomputed_digest(tmp_path, mutation):
    context = _fixture(tmp_path)
    receipt = context.service.prepare(context.project.project_id, context.recipe)
    path = context.store.projects_root / context.project.project_id / context.service.RECEIPT_NAME
    data = json.loads(path.read_text())
    if mutation == "hash":
        data["payload_sha256"] = "not a digest"
    elif mutation == "authority":
        data["execution_authority"] = "flash"
    elif mutation == "size_type":
        data["comparisons"][0]["size_bytes"] = True
    elif mutation == "extra":
        data["signing_ready"] = True
    elif mutation == "timestamp":
        data["created_at"] = "not a time"
    elif mutation == "comparison":
        data["comparisons"][0]["partition"] = "other"
    else:
        data["procedure_wipe"] = 0
    values = {key: value for key, value in data.items() if key not in {"format", "receipt_digest"}}
    data["receipt_digest"] = _digest(values)
    path.write_text(json.dumps(data))
    assert context.service.load(context.project.project_id) is None
    with pytest.raises(ProjectError):
        context.service.verify(receipt, context.recipe)


def test_resealed_but_false_saved_comparison_is_remeasured_before_use(tmp_path):
    context = _fixture(tmp_path)
    receipt = context.service.prepare(context.project.project_id, context.recipe)
    path = context.store.projects_root / context.project.project_id / context.service.RECEIPT_NAME
    changed = replace(
        receipt,
        comparisons=(replace(receipt.comparisons[0], sha256="f" * 64), *receipt.comparisons[1:]),
    )
    payload = asdict(changed)
    payload.pop("receipt_digest")
    changed = replace(changed, receipt_digest=_digest(payload))
    path.write_text(json.dumps({"format": context.service.FORMAT, **asdict(changed)}))
    assert context.service.load(context.project.project_id) == changed
    with pytest.raises(ProjectError, match="changed"):
        context.service.verify(changed, context.recipe)


@pytest.mark.parametrize(
    "fields",
    [
        {"build_project_id": None},
        {"build_project_id": "../other"},
        {"created_at": None},
        {"comparisons": None},
        {"comparisons": (object(),)},
        {"phone_changed": 0},
        {"execution_authority": "flash"},
    ],
)
def test_malformed_caller_receipt_is_rejected_before_source_work(tmp_path, fields, monkeypatch):
    context = _fixture(tmp_path)
    receipt = context.service.prepare(context.project.project_id, context.recipe)
    changed = replace(receipt, **fields)

    def must_not_measure(*_args, **_kwargs):
        pytest.fail("Malformed caller evidence must not trigger a source measurement")

    monkeypatch.setattr(context.service, "_derive", must_not_measure)
    with pytest.raises(ProjectError, match="receipt"):
        context.service.verify(changed, context.recipe)


@pytest.mark.parametrize("target", ["receipt", "source"])
def test_symlinked_evidence_or_source_cannot_be_used(tmp_path, target):
    context = _fixture(tmp_path)
    receipt = context.service.prepare(context.project.project_id, context.recipe)
    path = (
        context.store.projects_root / context.project.project_id / context.service.RECEIPT_NAME
        if target == "receipt"
        else context.store.original_path(context.project.project_id)
    )
    outside = tmp_path / f"outside-{target}"
    path.rename(outside)
    try:
        path.symlink_to(outside)
    except OSError as exc:
        if os.name == "nt" and getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows runner lacks privilege for this real symlink fixture")
        raise
    with pytest.raises(ProjectError):
        context.service.verify(receipt, context.recipe)


def test_approval_options_bind_receipt_without_granting_wipe_authority(tmp_path):
    context = _fixture(tmp_path)
    first = context.service.prepare(context.project.project_id, context.recipe)
    recipe = SourceInstallationService(context.store).prepare(
        context.procedure.project_id, wipe=True, reboot=False
    )
    with pytest.raises(ProjectError, match="changed"):
        context.service.verify(first, recipe)
    second = context.service.prepare(context.project.project_id, recipe)
    assert second.procedure_wipe is True and second.procedure_reboot is False
    assert second.receipt_digest != first.receipt_digest
    assert second.execution_authority == "none" and not second.phone_changed
    with pytest.raises(ProjectError, match="service-owned"):
        context.service.verify(first, context.recipe)
