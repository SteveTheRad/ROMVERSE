from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import struct
import subprocess
import zipfile
from dataclasses import replace
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from romverse.infrastructure.process import CommandResult
from romverse.infrastructure.toolchain_evidence import ToolchainEvidenceService
from romverse.infrastructure.toolchain_versions import VersionedToolchainStore
from romverse.infrastructure.tools import ToolStatus
from romverse.rom import candidate_avb as module
from romverse.rom.candidate_avb import CandidateAvbService
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore


def _sha(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture(scope="module")
def key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _public(key):
    number = key.public_key().public_numbers().n
    return (
        struct.pack("!II", 2048, (-pow(number, -1, 1 << 32)) % (1 << 32))
        + number.to_bytes(256, "big")
        + pow(2, 4096, number).to_bytes(256, "big")
    )


def _meta(descriptors, key=None, *, flags=0, rollback=0, location=0):
    raw = b"".join(descriptors)
    public = _public(key) if key else b""
    aux = raw + public
    aux += b"\0" * (-len(aux) % 64)
    auth_size = 320 if key else 0
    header = module._HEADER.pack(
        b"AVB0",
        1,
        0,
        auth_size,
        len(aux),
        1 if key else 0,
        0,
        32 if key else 0,
        32 if key else 0,
        256 if key else 0,
        len(raw),
        len(public),
        len(raw) + len(public),
        0,
        0,
        len(raw),
        rollback,
        flags,
        location,
        b"test fixture\0",
        b"\0" * 80,
    )
    auth = b""
    if key:
        auth = hashlib.sha256(header + aux).digest()
        auth += key.sign(header + aux, padding.PKCS1v15(), hashes.SHA256())
        auth += b"\0" * (auth_size - len(auth))
    return header + auth + aux


def _chain(name, key, *, location=2, flags=0):
    name, public = name.encode(), _public(key)
    length = module._CHAIN.size + len(name) + len(public)
    total = (length + 7) // 8 * 8
    return (
        module._CHAIN.pack(4, total - 16, location, len(name), len(public), flags, b"\0" * 60)
        + name
        + public
        + b"\0" * (total - length)
    )


def _tree_desc(name, data, *, salt=b"salt", digest=None):
    block = 4096
    level = b"".join(
        hashlib.sha256(salt + data[n : n + block]).digest() for n in range(0, len(data), block)
    )
    level += b"\0" * (-len(level) % block)
    calculated = hashlib.sha256(salt + level).digest()
    name = name.encode()
    length = module._TREE.size + len(name) + len(salt) + 32
    total = (length + 7) // 8 * 8
    desc = (
        module._TREE.pack(
            1,
            total - 16,
            1,
            len(data),
            len(data),
            len(level),
            block,
            block,
            0,
            0,
            0,
            b"sha256",
            len(name),
            len(salt),
            32,
            0,
            b"\0" * 60,
        )
        + name
        + salt
        + (digest or calculated)
        + b"\0" * (total - length)
    )
    return desc, level


def _partition(name, byte=b"p", *, key=None, digest=None):
    data = byte * 8192
    desc, tree = _tree_desc(name, data, digest=digest)
    meta = _meta((desc,), key)
    offset = len(data) + len(tree)
    footer = struct.pack("!4sIIQQQ28s", b"AVBf", 1, 0, len(data), offset, len(meta), b"\0" * 28)
    return data + tree + meta + footer, desc


class Runner:
    def __init__(self):
        self.commands = []
        self.after = None
        self.output = "Algorithm: NONE\n"
        self.returncode = 0
        self.timed_out = False

    def run(self, args, **kwargs):
        self.commands.append(tuple(args))
        assert args[1:3] == ("info_image", "--image")
        if self.after:
            self.after()
        return CommandResult(tuple(args), self.returncode, self.output, "", self.timed_out)


@pytest.fixture
def fixture(tmp_path, monkeypatch, key):
    """Real binary/content verification; immutable source/build providers are isolated."""
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Candidate AVB", "test.pack")
    folder = store.working_root / project.project_id / "images"
    folder.mkdir(parents=True)
    raw = {}
    descriptors = []
    for name, byte in (("product", b"p"), ("system", b"s"), ("system_ext", b"e")):
        raw[name], desc = _partition(name, byte, key=key if name != "product" else None)
        descriptors.append(desc)
    raw["child"] = _meta(descriptors)
    raw["super"] = b"measured super with saved unpack comparison"
    paths = {}
    for name, data in raw.items():
        path = folder / f"{name}.img"
        path.write_bytes(data)
        paths[name] = (path, _sha(data), len(data))
    tool = tmp_path / "avbtool"
    tool.write_bytes(b"inert test tool")
    build = SimpleNamespace(receipt_digest="b" * 64, toolchain_manifest_digest="c" * 64)
    plan = SimpleNamespace(plan_digest="d" * 64)
    base = SimpleNamespace(
        source_sha256="a" * 64,
        receipt_digest="e" * 64,
        pack_sha256="f" * 64,
        contract_digest="1" * 64,
    )
    runner = Runner()
    service = CandidateAvbService(store, SimpleNamespace(packs=()), (), runner)
    context = SimpleNamespace(
        store=store,
        project=project,
        raw=raw,
        paths=paths,
        tool=tool,
        build=build,
        plan=plan,
        base=base,
        runner=runner,
        service=service,
        root=_meta((_chain("vbmeta_system", key),), key),
    )
    monkeypatch.setattr(
        service,
        "_collect",
        lambda *_args: (
            context.build,
            context.plan,
            context.paths,
            context.root,
            tool,
            _sha(b"inert test tool"),
            SimpleNamespace(hash_algorithm="sha256", salt=b"salt".hex(), generate_fec=False),
            (),
        ),
    )
    monkeypatch.setattr(
        module.LocalDeviceBuildExecutor, "load_receipt", lambda *_args: context.build
    )
    return context


def _change(fixture, name, data):
    path = fixture.paths[name][0]
    path.write_bytes(data)
    fixture.raw[name] = data
    fixture.paths[name] = (path, _sha(data), len(data))


def test_real_binary_content_verification_is_not_oem_or_phone_authority(fixture):
    receipt = fixture.service.prepare(fixture.project.project_id, fixture.base)
    assert receipt.root_algorithm == "SHA256_RSA2048"
    assert receipt.child_algorithm == "NONE"
    assert receipt.candidate_super_sha256 == fixture.paths["super"][1]
    assert receipt.product_sha256 == fixture.paths["product"][1]
    assert tuple(row.partition for row in receipt.descriptors) == (
        "product",
        "system",
        "system_ext",
    )
    assert receipt.root_chains[0].rollback_index_location == 2
    assert receipt.execution_authority == "none"
    assert not receipt.oem_trusted and not receipt.candidate_signed and not receipt.phone_changed
    assert "experimental" in receipt.policy_label and "NOT a valid OEM" in receipt.warnings[0]
    assert fixture.service.load(fixture.project.project_id) == receipt
    assert fixture.service.verify(receipt, fixture.base) == receipt
    assert len(fixture.runner.commands) == 2
    for name, data in fixture.raw.items():
        assert fixture.paths[name][0].read_bytes() == data


def test_counterfeit_child_digest_rejected_even_with_fresh_output_hash(fixture):
    descriptors = list(
        module._metadata(io.BytesIO(fixture.raw["child"]), len(fixture.raw["child"])).descriptors
    )
    corrupted = bytearray(descriptors[0].raw)
    corrupted[module._TREE.size + len("product") + len(b"salt")] ^= 1
    _change(fixture, "child", _meta((bytes(corrupted), *(d.raw for d in descriptors[1:]))))
    with pytest.raises(ProjectError, match="descriptor content differs"):
        fixture.service.prepare(fixture.project.project_id, fixture.base)


def test_counterfeit_footer_and_child_cannot_agree_themselves_into_success(fixture):
    data, corrupt = _partition("product", digest=b"x" * 32)
    descriptors = module._metadata(
        io.BytesIO(fixture.raw["child"]), len(fixture.raw["child"])
    ).descriptors
    _change(fixture, "product", data)
    _change(fixture, "child", _meta((corrupt, *(d.raw for d in descriptors[1:]))))
    with pytest.raises(ProjectError, match="Merkle root differs"):
        fixture.service.prepare(fixture.project.project_id, fixture.base)


@pytest.mark.parametrize("offset", [0, 8192])
def test_actual_data_or_stored_tree_corruption_rejected(fixture, offset):
    corrupted = bytearray(fixture.raw["product"])
    corrupted[offset] ^= 1
    _change(fixture, "product", bytes(corrupted))
    with pytest.raises(ProjectError, match="Merkle tree bytes"):
        fixture.service.prepare(fixture.project.project_id, fixture.base)


def test_changed_image_with_restored_mtime_is_rejected(fixture):
    path = fixture.paths["system"][0]
    before = path.stat()
    data = bytearray(path.read_bytes())
    data[0] ^= 1
    path.write_bytes(data)
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    with pytest.raises(ProjectError, match="image changed before"):
        fixture.service.prepare(fixture.project.project_id, fixture.base)


def test_source_signature_corruption_is_not_hidden_by_embedded_key(fixture):
    data = bytearray(fixture.root)
    data[256 + 32] ^= 1
    fixture.root = bytes(data)
    with pytest.raises(ProjectError, match="signature does not verify"):
        fixture.service.prepare(fixture.project.project_id, fixture.base)


@pytest.mark.parametrize("header_field,value", [(3, 2**63), (14, 2**63), (15, 2**63), (2, 99)])
def test_untrusted_avb_header_offsets_and_versions_are_bounded(fixture, header_field, value):
    blob = fixture.raw["child"]
    fields = list(module._HEADER.unpack(blob[:256]))
    fields[header_field] = value
    _change(fixture, "child", module._HEADER.pack(*fields) + blob[256:])
    with pytest.raises(ProjectError):
        fixture.service.prepare(fixture.project.project_id, fixture.base)


@pytest.mark.parametrize("kwargs", [{"flags": 1}, {"flags": 2}, {"rollback": 1}, {"location": 1}])
def test_unsigned_policy_never_silently_adds_disable_or_rollback_fields(fixture, kwargs):
    descriptors = module._metadata(
        io.BytesIO(fixture.raw["child"]), len(fixture.raw["child"])
    ).descriptors
    _change(fixture, "child", _meta(tuple(d.raw for d in descriptors), **kwargs))
    with pytest.raises(ProjectError, match="unsigned, flags-zero"):
        fixture.service.prepare(fixture.project.project_id, fixture.base)


def test_unrecognized_signed_child_requires_a_different_explicit_route(fixture, key):
    descriptors = module._metadata(
        io.BytesIO(fixture.raw["child"]), len(fixture.raw["child"])
    ).descriptors
    _change(fixture, "child", _meta(tuple(d.raw for d in descriptors), key))
    with pytest.raises(ProjectError, match="unsigned, flags-zero"):
        fixture.service.prepare(fixture.project.project_id, fixture.base)


@pytest.mark.parametrize("kind", ["missing", "duplicate", "unknown", "chain"])
def test_descriptor_inventory_cannot_skip_unknown_duplicate_or_missing_targets(fixture, key, kind):
    descriptors = [
        d.raw
        for d in module._metadata(
            io.BytesIO(fixture.raw["child"]), len(fixture.raw["child"])
        ).descriptors
    ]
    if kind == "missing":
        descriptors.pop()
    elif kind == "duplicate":
        descriptors.append(descriptors[0])
    elif kind == "chain":
        descriptors.append(_chain("vendor", key))
    else:
        descriptors.append(struct.pack("!QQ", 99, 0))
    _change(fixture, "child", _meta(descriptors))
    with pytest.raises(ProjectError):
        fixture.service.prepare(fixture.project.project_id, fixture.base)


@pytest.mark.parametrize("change", ["tool", "product", "super", "build"])
def test_input_drift_during_read_only_probe_stops_receipt(fixture, change):
    def mutate():
        if change == "tool":
            fixture.tool.write_bytes(b"substituted tool")
        elif change == "build":
            fixture.build = SimpleNamespace(receipt_digest="9" * 64)
        else:
            fixture.paths[change][0].write_bytes(b"changed after verification")

    fixture.runner.after = mutate
    with pytest.raises(ProjectError, match="changed"):
        fixture.service.prepare(fixture.project.project_id, fixture.base)


@pytest.mark.parametrize(
    "field,value",
    [("returncode", 1), ("timed_out", True), ("output", "Algorithm: SHA256_RSA2048\n")],
)
def test_pinned_tool_failure_or_header_disagreement_is_not_success(fixture, field, value):
    setattr(fixture.runner, field, value)
    with pytest.raises(ProjectError):
        fixture.service.prepare(fixture.project.project_id, fixture.base)


@pytest.mark.parametrize(
    "field,value",
    [("phone_changed", 0), ("oem_trusted", True), ("unexpected", "x"), ("child_flags", 2)],
)
def test_saved_receipt_is_typed_and_never_authorizes_oem_trust(fixture, field, value):
    receipt = fixture.service.prepare(fixture.project.project_id, fixture.base)
    path = fixture.store.projects_root / fixture.project.project_id / fixture.service.RECEIPT_NAME
    saved = json.loads(path.read_text())
    saved[field] = value
    path.write_text(json.dumps(saved))
    assert fixture.service.load(fixture.project.project_id) is None
    with pytest.raises(ProjectError):
        fixture.service.verify(receipt, fixture.base)


def test_caller_modified_even_resealed_receipt_is_not_saved_authority(fixture):
    receipt = fixture.service.prepare(fixture.project.project_id, fixture.base)
    forged = module._seal(replace(receipt, root_sha256="9" * 64))
    with pytest.raises(ProjectError, match="saved candidate AVB evidence"):
        fixture.service.verify(forged, fixture.base)


def test_missing_current_build_or_wrong_base_receipt_rejected_before_commands(tmp_path):
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Unbuilt", "test")
    runner = Runner()
    service = CandidateAvbService(store, SimpleNamespace(packs=()), (), runner)
    with pytest.raises(ProjectError, match="exact base-image receipt"):
        service.prepare(project.project_id, SimpleNamespace(build_project_id=project.project_id))
    assert not runner.commands


@pytest.mark.parametrize(
    "value", [b"../product", b"/product", b"product/a", b"..", b"product\x00x"]
)
def test_descriptor_partition_paths_are_not_filesystem_instructions(value):
    with pytest.raises(ProjectError):
        module._name(value)


def test_archive_root_is_bounded_hash_checked_and_normalizes_safe_dot_names(tmp_path, key):
    blob = _meta((_chain("vbmeta_system", key),), key)
    path = tmp_path / "source.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("./images/vbmeta.img", blob)
    row = SimpleNamespace(member="images/vbmeta.img", size_bytes=len(blob), sha256=_sha(blob))
    assert module._archive_root(path, row) == blob
    with pytest.raises(ProjectError, match="differs from"):
        module._archive_root(path, SimpleNamespace(**{**vars(row), "sha256": "a" * 64}))
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr("images/vbmeta.img", blob)
    with pytest.raises(ProjectError, match="ambiguous"):
        module._archive_root(path, row)


def test_merkle_size_and_fec_bounds_are_checked_before_large_reads(tmp_path):
    blob, raw = _partition("product")
    path = tmp_path / "product.img"
    path.write_bytes(blob)
    desc = module._descriptors(raw)[0]
    for changed in (
        replace(desc, tree_size=2**63),
        replace(desc, tree_offset=1),
        replace(desc, fec_num_roots=2, fec_offset=2**63, fec_size=4096),
        replace(desc, fec_num_roots=0, fec_offset=12288, fec_size=4096),
    ):
        with pytest.raises(ProjectError):
            module._verify_content(path, changed, 12288)


def test_hash_descriptor_verifies_actual_bytes_not_name(tmp_path):
    path = tmp_path / "partition.img"
    data = b"data" * 4096
    path.write_bytes(data)
    desc = module._Descriptor(
        2, b"", "product", len(data), "sha256", b"salt", hashlib.sha256(b"salt" + data).digest()
    )
    module._verify_content(path, desc, len(data))
    with pytest.raises(ProjectError, match="differs from"):
        module._verify_content(path, replace(desc, digest=b"x" * 32), len(data))


@pytest.mark.parametrize("algorithm", ["sha1", "sha256", "sha512"])
def test_multilevel_tree_matches_available_aosp_avbtool_without_device_access(tmp_path, algorithm):
    """Independent reference implementation checks real multi-level tree ordering."""
    tool = shutil.which("avbtool")
    if tool is None:
        pytest.skip("Optional AOSP avbtool cross-check is unavailable")
    path = tmp_path / "product.img"
    path.write_bytes(bytes(range(256)) * 8192)
    result = subprocess.run(
        (
            tool,
            "add_hashtree_footer",
            "--image",
            str(path),
            "--partition_name",
            "product",
            "--partition_size",
            str(4 * 1024 * 1024),
            "--hash_algorithm",
            algorithm,
            "--salt",
            "01020304",
            "--do_not_generate_fec",
        ),
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    meta = module._read_metadata(path)
    desc = module._partition_descriptors(meta)["product"]
    assert desc.tree_size > 4096 and desc.algorithm == algorithm
    module._verify_content(path, desc, meta.offset)
    data = bytearray(path.read_bytes())
    data[desc.tree_offset] ^= 1
    path.write_bytes(data)
    with pytest.raises(ProjectError, match="Merkle tree bytes"):
        module._verify_content(path, desc, meta.offset)


def test_product_contract_salt_must_match_even_when_all_candidate_descriptors_agree(fixture):
    collected = fixture.service._collect(fixture.project.project_id, fixture.base)
    fixture.service._collect = lambda *_args: (
        *collected[:-2],
        SimpleNamespace(hash_algorithm="sha256", salt="00", generate_fec=False),
        collected[-1],
    )
    with pytest.raises(ProjectError, match="fields differ from the exact build contract"):
        fixture.service.prepare(fixture.project.project_id, fixture.base)


def test_unsigned_root_is_not_silently_treated_as_exact_signed_source(fixture, key):
    fixture.root = _meta((_chain("vbmeta_system", key),))
    with pytest.raises(ProjectError, match="exact signed source root"):
        fixture.service.prepare(fixture.project.project_id, fixture.base)


@pytest.mark.parametrize("field,value", [("location", 0), ("flags", 1)])
def test_source_child_chain_must_have_explicit_ab_rollback_location(fixture, key, field, value):
    fixture.root = _meta((_chain("vbmeta_system", key, **{field: value}),), key)
    with pytest.raises(ProjectError):
        fixture.service.prepare(fixture.project.project_id, fixture.base)


def test_source_replacement_during_validation_invalidates_receipt(fixture, tmp_path):
    path = tmp_path / "source.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("data", b"original")
    project = fixture.store.import_original(fixture.project.project_id, path)
    source_path = fixture.store.original_path(project.project_id)
    collected = fixture.service._collect(fixture.project.project_id, fixture.base)
    fixture.service._collect = lambda *_args: (
        *collected[:-1],
        (
            (
                project.project_id,
                project.original,
                source_path,
                module._fingerprint(source_path.stat()),
            ),
        ),
    )

    def mutate_fixture_only():
        source_path.chmod(0o600)
        source_path.write_bytes(b"changed source")

    fixture.runner.after = mutate_fixture_only
    with pytest.raises(ProjectError, match="protected source changed"):
        fixture.service.prepare(fixture.project.project_id, fixture.base)


def test_resealed_nested_receipt_coercions_are_rejected_by_strict_loader(fixture):
    receipt = fixture.service.prepare(fixture.project.project_id, fixture.base)
    changed = replace(
        receipt, descriptors=(replace(receipt.descriptors[0], flags=True), *receipt.descriptors[1:])
    )
    payload = module._seal(changed)
    path = fixture.store.projects_root / fixture.project.project_id / fixture.service.RECEIPT_NAME
    path.write_text(json.dumps({"format": fixture.service.FORMAT, **module.asdict(payload)}))
    assert fixture.service.load(fixture.project.project_id) is None
    with pytest.raises(ProjectError, match="malformed"):
        fixture.service.verify(payload, fixture.base)


def _pinned_tool(tmp_path, *, isolate=True):
    workspace = tmp_path / "workspace"
    path = workspace / "tools" / "downloads" / "avbtool" / "avbtool"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"exact managed test AVB tool")
    if os.name != "nt":
        path.chmod(0o700)
    (path.parent / "managed-tool.romverse").write_text(
        json.dumps(
            {
                "format": "romverse.managed-tool",
                "schema_version": 1,
                "name": "AVBTool",
                "source": "https://android.googlesource.com/platform/external/avb/+/refs/heads/main/avbtool.py?format=TEXT",
                "sha256": _sha(path.read_bytes()),
                "executable": "avbtool",
            }
        )
    )
    statuses = (ToolStatus("AVBTool", True, str(path), "1.3.0", "Inert test tool"),)
    manifest = ToolchainEvidenceService(workspace, "Linux").capture(
        statuses, required_tools=("AVBTool",), scope="local-build:test-project"
    )
    versions = VersionedToolchainStore(workspace)
    pinned = versions.isolate({"AVBTool": path}, manifest)["AVBTool"] if isolate else None
    return SimpleNamespace(
        workspace=workspace, active=path, pinned=pinned, statuses=statuses, manifest=manifest
    )


@pytest.mark.parametrize("active_present", [True, False])
def test_exact_preserved_tool_survives_active_update_without_storage_mutation(
    tmp_path, monkeypatch, active_present
):
    fixture = _pinned_tool(tmp_path)
    fixture.active.write_bytes(b"different upgraded active AVB tool")
    paths = [fixture.pinned, fixture.pinned.parent / VersionedToolchainStore.RECEIPT_NAME]
    before = [
        (path.read_bytes(), path.stat().st_mode, module._fingerprint(path.stat())) for path in paths
    ]

    def unexpected_mutation(*args, **kwargs):
        pytest.fail("Read-only candidate inspection must not isolate, repair, or chmod tools")

    monkeypatch.setattr(VersionedToolchainStore, "_verify_slot", unexpected_mutation)
    monkeypatch.setattr(VersionedToolchainStore, "isolate", unexpected_mutation)
    monkeypatch.setattr(VersionedToolchainStore, "_snapshot", unexpected_mutation)
    path, evidence = module._resolve_avbtool(
        fixture.workspace, fixture.statuses if active_present else (), fixture.manifest
    )
    assert path == fixture.pinned
    assert module._hash(path) == (evidence.sha256, evidence.size_bytes)
    assert [
        (path.read_bytes(), path.stat().st_mode, module._fingerprint(path.stat())) for path in paths
    ] == before


def test_exact_active_tool_is_usable_without_creating_missing_preserved_slot(tmp_path):
    fixture = _pinned_tool(tmp_path, isolate=False)
    path, _ = module._resolve_avbtool(fixture.workspace, fixture.statuses, fixture.manifest)
    assert path == fixture.active
    assert not (fixture.workspace / "tools" / "versioned").exists()


@pytest.mark.parametrize("tamper", ["bytes", "receipt", "receipt_bool", "unexpected", "link"])
def test_corrupt_preserved_slot_never_falls_back_to_good_active_tool(tmp_path, tamper):
    fixture = _pinned_tool(tmp_path)
    if tamper == "bytes":
        fixture.pinned.chmod(0o700)
        fixture.pinned.write_bytes(b"changed preserved tool")
    elif tamper in {"receipt", "receipt_bool"}:
        path = fixture.pinned.parent / VersionedToolchainStore.RECEIPT_NAME
        data = json.loads(path.read_text())
        if tamper == "receipt_bool":
            data["schema_version"] = True
        else:
            data["source_sha256"] = "f" * 64
        path.write_text(json.dumps(data))
    elif tamper == "unexpected":
        (fixture.pinned.parent / "unexpected").write_bytes(b"extra")
    else:
        fixture.pinned.rename(fixture.pinned.with_suffix(".saved"))
        try:
            fixture.pinned.symlink_to(fixture.active)
        except OSError as exc:
            if os.name == "nt" and getattr(exc, "winerror", None) == 1314:
                pytest.skip("Windows runner lacks privilege for this real symlink fixture")
            raise
        fixture.pinned.with_suffix(".saved").rename(tmp_path / "saved-tool")
    with pytest.raises(ProjectError, match="AVBTool|symlink|regular"):
        module._resolve_avbtool(fixture.workspace, fixture.statuses, fixture.manifest)
    assert fixture.active.read_bytes() == b"exact managed test AVB tool"


def test_preserved_tool_parent_redirect_is_rejected_without_following_it(tmp_path):
    fixture = _pinned_tool(tmp_path)
    version_root = fixture.workspace / "tools" / "versioned"
    moved = tmp_path / "moved-versioned"
    version_root.rename(moved)
    try:
        version_root.symlink_to(moved, target_is_directory=True)
    except OSError as exc:
        if os.name == "nt" and getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows runner lacks privilege for this real symlink fixture")
        raise
    with pytest.raises(ProjectError, match="directory is unsafe"):
        module._resolve_avbtool(fixture.workspace, fixture.statuses, fixture.manifest)


def test_changed_active_tool_does_not_mint_or_repair_missing_pinned_version(tmp_path):
    fixture = _pinned_tool(tmp_path, isolate=False)
    fixture.active.write_bytes(b"different active version")
    with pytest.raises(ProjectError, match="changed from"):
        module._resolve_avbtool(fixture.workspace, fixture.statuses, fixture.manifest)
    assert not (fixture.workspace / "tools" / "versioned").exists()
