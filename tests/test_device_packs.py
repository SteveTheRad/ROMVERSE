import hashlib
import json
import shutil
from dataclasses import replace
from datetime import date
from importlib.resources import files

import pytest

from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.models import (
    AvbPolicyAuthority,
    AvbPolicyMode,
    CapabilityStatus,
    DeviceWriteTransport,
    FirmwareSourceContract,
)
from romverse.device_packs.registry import DevicePackRegistry


def builtin_registry():
    return DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))


def android_device(manufacturer: str, model: str = "Test Phone") -> AndroidDevice:
    return AndroidDevice(
        serial="private",
        state=DeviceState.DEVICE,
        manufacturer=manufacturer,
        model=model,
    )


def test_builtin_pack_index_and_hashes_are_valid():
    registry = builtin_registry()
    assert registry.issues == ()
    assert {pack.pack_id for pack in registry.packs} == {
        "android.generic",
        "asus.rog-android",
        "google.pixel",
        "google.pixel.tensor-gki",
        "honor.magicos",
        "hmd.nokia-android",
        "huawei.emui-harmonyos",
        "motorola.android",
        "nothing.os",
        "oneplus.oxygenos",
        "oppo.coloros",
        "realme.ui",
        "fairphone.android",
        "sony.xperia",
        "sony.xperia.open-devices.identity",
        "vivo.funtouch-iqoo",
        "transsion.android",
        "xiaomi.hyperos",
        "xiaomi.popsicle.hyperos4.os4.0.0.23",
        "samsung.oneui",
        "zte.nubia-android",
    }


def test_registry_resolves_xiaomi_samsung_and_generic_fallback():
    registry = builtin_registry()
    assert registry.resolve(android_device("Xiaomi")).pack.pack_id == "xiaomi.hyperos"
    assert registry.resolve(android_device("samsung")).pack.pack_id == "samsung.oneui"
    generic = registry.resolve(android_device("Example OEM"))
    assert generic.pack.pack_id == "android.generic"
    assert generic.reason == "Generic Android fallback"


def test_registry_uses_exact_android_retail_brand_when_manufacturer_differs():
    registry = builtin_registry()
    device = AndroidDevice(
        "private",
        DeviceState.DEVICE,
        brand="Xiaomi",
        manufacturer="Contract Manufacturer",
        model="Regional phone",
    )

    resolution = registry.resolve(device)

    assert resolution.pack is not None
    assert resolution.pack.pack_id == "xiaomi.hyperos"
    assert resolution.reason == "Retail brand matched Xiaomi"


def test_registry_uses_unambiguous_literal_product_for_fastboot_identity_only() -> None:
    registry = builtin_registry()
    device = AndroidDevice(
        "private",
        DeviceState.BOOTLOADER,
        transport="usb-fastboot",
        model="popsicle",
        product="popsicle",
        codename="popsicle",
    )

    resolution = registry.resolve(device)

    assert resolution.pack is not None
    assert resolution.pack.pack_id == "xiaomi.popsicle.hyperos4.os4.0.0.23"
    assert resolution.reason == (
        "Exact literal product identity matched popsicle; OEM was not reported in Fastboot"
    )


def test_registry_does_not_guess_a_fastboot_pack_from_a_wildcard_product() -> None:
    registry = builtin_registry()
    device = AndroidDevice(
        "private",
        DeviceState.FASTBOOT,
        transport="usb-fastboot",
        product="popsicle_unpublished_variant",
        codename="popsicle_unpublished_variant",
    )

    resolution = registry.resolve(device)

    assert resolution.pack is not None
    assert resolution.pack.pack_id == "android.generic"
    assert resolution.reason == "Generic Android fallback"


def test_registry_resolves_new_read_only_oem_knowledge_packs():
    registry = builtin_registry()

    expected = {
        "Google": "google.pixel",
        "OnePlus": "oneplus.oxygenos",
        "OPPO": "oppo.coloros",
        "realme": "realme.ui",
        "Nothing": "nothing.os",
        "motorola": "motorola.android",
        "Sony": "sony.xperia",
        "vivo": "vivo.funtouch-iqoo",
        "iQOO": "vivo.funtouch-iqoo",
        "ASUS": "asus.rog-android",
        "HUAWEI": "huawei.emui-harmonyos",
        "HONOR": "honor.magicos",
        "HMD Global": "hmd.nokia-android",
        "Nokia": "hmd.nokia-android",
        "TECNO": "transsion.android",
        "Infinix": "transsion.android",
        "itel": "transsion.android",
        "ZTE": "zte.nubia-android",
        "nubia": "zte.nubia-android",
        "REDMAGIC": "zte.nubia-android",
        "Fairphone": "fairphone.android",
    }
    for manufacturer, pack_id in expected.items():
        pack = registry.resolve(android_device(manufacturer)).pack
        assert pack is not None
        assert pack.pack_id == pack_id
        assert pack.build_contract is None
        assert pack.knowledge_sources
        assert all(source.url.startswith("https://") for source in pack.knowledge_sources)


def test_new_oem_knowledge_packs_never_grant_device_changing_authority():
    registry = builtin_registry()
    pack_ids = {
        "oppo.coloros",
        "realme.ui",
        "nothing.os",
        "vivo.funtouch-iqoo",
        "asus.rog-android",
        "huawei.emui-harmonyos",
        "honor.magicos",
        "hmd.nokia-android",
        "transsion.android",
        "zte.nubia-android",
        "fairphone.android",
    }

    for pack in (pack for pack in registry.packs if pack.pack_id in pack_ids):
        assert pack.build_contract is None
        assert not pack.build_compatible_pack_sha256
        firmware_capabilities = tuple(
            capability
            for capability in pack.capabilities
            if capability.capability_id.endswith("firmware.operations")
        )
        assert len(firmware_capabilities) == 1
        capability = firmware_capabilities[0]
        assert capability.status is CapabilityStatus.PLANNED
        assert capability.scope == "locked"
        assert capability.detail.startswith("No ")


def test_registry_prefers_exact_published_pixel_tensor_identity_over_oem_pack():
    registry = builtin_registry()
    device = AndroidDevice(
        "private",
        DeviceState.DEVICE,
        manufacturer="Google",
        model="Pixel 9 Pro",
        product="caiman",
        codename="caiman",
    )

    pack = registry.resolve(device).pack

    assert pack is not None
    assert pack.pack_id == "google.pixel.tensor-gki"
    assert pack.build_contract is None
    assert any(source.source_id == "aosp.pixel.kernel-matrix" for source in pack.knowledge_sources)
    source = pack.knowledge_sources[0]
    assert not source.is_stale(date(2026, 12, 1))
    assert source.is_stale(date(2027, 3, 1))


@pytest.mark.parametrize(
    ("product", "expected_pack"),
    [
        ("pdx245", "sony.xperia.open-devices.identity"),
        ("pdx234", "sony.xperia.open-devices.identity"),
        ("pdx215", "sony.xperia.open-devices.identity"),
        ("akari", "sony.xperia.open-devices.identity"),
    ],
)
def test_registry_prefers_published_sony_open_devices_identity(product, expected_pack):
    registry = builtin_registry()
    device = AndroidDevice(
        "private",
        DeviceState.DEVICE,
        manufacturer="Sony",
        model="XQ-TEST",
        product="carrier_variant_product",
        codename=product,
    )

    pack = registry.resolve(device).pack

    assert pack is not None
    assert pack.pack_id == expected_pack
    assert pack.build_contract is None
    assert any("supported-device matrix" in source.label for source in pack.knowledge_sources)


def test_unknown_sony_product_remains_on_broad_read_only_pack():
    pack = (
        builtin_registry()
        .resolve(
            AndroidDevice(
                "private",
                DeviceState.DEVICE,
                manufacturer="Sony",
                model="Unknown Xperia",
                product="unknown_sony_product",
            )
        )
        .pack
    )

    assert pack is not None
    assert pack.pack_id == "sony.xperia"


def test_equal_priority_live_match_is_ambiguous_and_fails_closed():
    base = next(pack for pack in builtin_registry().packs if pack.pack_id == "sony.xperia")
    first = replace(base, pack_id="sony.conflict.one", priority=500)
    second = replace(base, pack_id="sony.conflict.two", priority=500)
    registry = DevicePackRegistry((first, second))

    resolution = registry.resolve(android_device("Sony"))

    assert resolution.pack is None
    assert not resolution.matched
    assert "Ambiguous Device Pack match" in resolution.reason
    assert "sony.conflict.one" in resolution.reason
    assert "sony.conflict.two" in resolution.reason


def test_higher_priority_oem_pack_wins_over_generic():
    registry = builtin_registry()
    resolution = registry.resolve(android_device("POCO"))
    assert resolution.pack.display_name == "Xiaomi / HyperOS"
    assert resolution.pack.priority > 0


def test_exact_popsicle_pack_wins_and_exposes_a_bounded_build_contract():
    registry = builtin_registry()
    device = AndroidDevice(
        "private",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        model="2509FPN0BC",
        product="popsicle_global",
        codename="popsicle",
    )

    pack = registry.resolve(device).pack

    assert pack is not None
    assert pack.pack_id == "xiaomi.popsicle.hyperos4.os4.0.0.23"
    assert pack.build_contract is not None
    assert pack.build_contract.editable_partitions == ("product",)
    assert pack.build_contract.super_size_bytes == 13_421_772_800
    assert set(pack.build_contract.required_tools) == {
        "Python",
        "ADB",
        "Fastboot",
        "7-Zip",
        "Unzip",
        "simg2img",
        "Payload Dumper",
        "EROFS Builder",
        "EROFS Verifier",
        "LP Make",
        "LP Unpack",
        "LP Dump",
        "Fakeroot",
        "AVBTool",
    }
    assert "Git" not in pack.build_contract.required_tools
    assert "Java" not in pack.build_contract.required_tools
    policy = pack.build_contract.avb_execution_policy
    assert policy is not None
    assert policy.mode is AvbPolicyMode.UNLOCKED_UNSIGNED_CHILD
    assert policy.authority is AvbPolicyAuthority.REFERENCE_ONLY
    assert policy.evidence_build_id == "OS4.0.0.20.XPBCNXM"
    assert policy.require_unlocked_bootloader
    assert policy.require_critical_unlocked
    assert policy.target_slot == "a"
    assert pack.build_compatible_pack_sha256 == (
        "f6506fb44281dc62c79008fd7e80cf79c8286bccd57aba3df740fc8eff5981a3",
    )


def test_unmatched_source_can_fall_back_to_non_executing_oem_knowledge():
    registry = builtin_registry()
    device = AndroidDevice(
        "private",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        model="2509FPN0BC",
        product="popsicle_global",
        codename="popsicle",
    )

    exact = registry.resolve(device)
    knowledge = registry.resolve_knowledge(device)

    assert exact.pack is not None and exact.pack.build_contract is not None
    assert knowledge.matched
    assert knowledge.pack is not None
    assert knowledge.pack.pack_id == "xiaomi.hyperos"
    assert knowledge.pack.build_contract is None


def test_registry_resolves_a_unique_exact_firmware_source():
    registry = builtin_registry()
    exact = next(
        pack for pack in registry.packs if pack.pack_id == "xiaomi.popsicle.hyperos4.os4.0.0.23"
    )
    contract = exact.build_contract
    assert contract is not None

    by_archive = registry.resolve_source(contract.source.archive_sha256)
    by_both = registry.resolve_source(
        contract.source.archive_sha256,
        contract.source.payload_sha256,
    )

    assert by_archive.pack == exact
    assert by_archive.matched
    assert by_both.pack == exact
    assert not registry.resolve_source("0" * 64).matched
    assert not registry.resolve_source("not-a-digest").matched
    assert not registry.resolve_source(contract.source.archive_sha256, "1" * 64).matched


def test_modified_pack_fails_integrity_and_cannot_activate(tmp_path):
    source = files("romverse.assets").joinpath("device_packs")
    for name in (
        "index.json",
        "android-generic.json",
        "xiaomi-hyperos.json",
        "xiaomi-popsicle-hyperos4.json",
        "samsung-oneui.json",
    ):
        shutil.copyfile(source.joinpath(name), tmp_path / name)
    path = tmp_path / "xiaomi-hyperos.json"
    path.write_text(path.read_text() + "\n")

    registry = DevicePackRegistry.load(tmp_path)
    assert any(issue.filename == "xiaomi-hyperos.json" for issue in registry.issues)
    assert registry.resolve(android_device("Xiaomi")).pack.pack_id == "android.generic"


def test_unsafe_index_filename_is_rejected(tmp_path):
    (tmp_path / "index.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "packs": [{"file": "../outside.json", "sha256": "irrelevant"}],
            }
        )
    )
    registry = DevicePackRegistry.load(tmp_path)
    assert registry.packs == ()
    assert registry.issues[0].reason == "unsafe pack filename"


def test_duplicate_pack_ids_are_all_rejected(tmp_path):
    source = files("romverse.assets").joinpath("device_packs", "sony-xperia.json")
    raw = source.read_text(encoding="utf-8")
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    (tmp_path / "first.json").write_text(raw, encoding="utf-8")
    (tmp_path / "second.json").write_text(raw, encoding="utf-8")
    (tmp_path / "index.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "packs": [
                    {"file": "first.json", "sha256": digest},
                    {"file": "second.json", "sha256": digest},
                ],
            }
        ),
        encoding="utf-8",
    )

    registry = DevicePackRegistry.load(tmp_path)

    assert registry.packs == ()
    assert len(registry.issues) == 1
    assert registry.issues[0].filename == "sony.xperia"
    assert "all conflicting copies rejected" in registry.issues[0].reason


def test_custom_rechain_policy_requires_exact_signing_public_key():
    source = FirmwareSourceContract("BUILD", "a" * 64, "b" * 64)
    policy = {
        "schema_version": 1,
        "mode": "signed_custom_rechain",
        "authority": "flash_validated",
        "evidence_build_id": "BUILD",
        "top_level_strategy": "preserve_exact_source",
        "chain_partition": "vbmeta_system",
        "candidate_algorithm": "SHA256_RSA4096",
        "candidate_rollback_index": 1,
        "candidate_rollback_index_location": 2,
        "candidate_flags": 0,
        "require_unlocked_bootloader": False,
        "require_critical_unlocked": False,
        "require_verity_mode": True,
        "target_slot": "a",
        "recovery_bootloader_slot": "b",
        "attestation_sha256": "c" * 64,
    }

    with pytest.raises(ValueError, match="signing public key"):
        DevicePackRegistry._parse_avb_policy(policy, source)

    policy["signing_public_key_sha1"] = "d" * 40
    parsed = DevicePackRegistry._parse_avb_policy(policy, source)
    assert parsed is not None
    assert parsed.signing_public_key_sha1 == "d" * 40


def _schema_two_build_contract() -> dict:
    document = json.loads(
        files("romverse.assets")
        .joinpath("device_packs", "xiaomi-popsicle-hyperos4.json")
        .read_text(encoding="utf-8")
    )
    contract = document["build_contract"]
    contract["schema_version"] = 2
    policy = contract["avb_execution_policy"]
    policy["authority"] = "flash_validated"
    policy["evidence_build_id"] = contract["source"]["build_id"]
    policy["attestation_sha256"] = "c" * 64
    contract["partition_write_contract"] = {
        "schema_version": 1,
        "contract_id": "popsicle-exact-writes",
        "source_build_id": contract["source"]["build_id"],
        "attestation_sha256": "c" * 64,
        "require_unlocked_bootloader": True,
        "require_critical_unlocked": True,
        "preserve_user_data_supported": True,
        "wipe_user_data_supported": True,
        "bootloader_relock_allowed": False,
        "writes": [
            {
                "partition": "super",
                "artifact": "super.img",
                "transport": "fastbootd",
                "target_slot": "none",
                "verify_after_write": True,
            }
        ],
    }
    return contract


def _schema_two_build_contract_with_post_write_verification() -> dict:
    contract = _schema_two_build_contract()
    write_contract = contract["partition_write_contract"]
    write_contract["schema_version"] = 2
    write_contract["post_write_verification_contract"] = {
        "schema_version": 1,
        "contract_id": "popsicle-exact-post-write",
        "source_build_id": contract["source"]["build_id"],
        "attestation_sha256": "c" * 64,
        "readbacks": [
            {
                "partition": "super",
                "transport": "fastbootd",
                "target_slot": "none",
                "method": "fastboot_fetch_sha256",
                "expected_size_bytes": 13_421_772_800,
                "expected_sha256": "d" * 64,
            }
        ],
        "post_boot_properties": [
            {"property_name": "sys.boot_completed", "expected_value": "1"},
            {"property_name": "ro.product.device", "expected_value": "popsicle"},
            {
                "property_name": "ro.build.fingerprint",
                "expected_value": "Xiaomi/popsicle/popsicle:17/TEST/1:user/release-keys",
            },
            {"property_name": "ro.build.version.incremental", "expected_value": "TEST.1"},
            {"property_name": "ro.build.version.sdk", "expected_value": "37"},
            {
                "property_name": "ro.build.version.security_patch",
                "expected_value": "2026-08-01",
            },
            {"property_name": "ro.boot.verifiedbootstate", "expected_value": "orange"},
        ],
        "require_adb_authorized": True,
        "boot_timeout_seconds": 300,
    }
    return contract


def test_schema_two_build_contract_parses_bounded_signed_write_intent():
    parsed = DevicePackRegistry._parse_build_contract(_schema_two_build_contract())

    assert parsed.version == 2
    assert parsed.partition_write_contract is not None
    write_contract = parsed.partition_write_contract
    assert write_contract.source_build_id == parsed.source.build_id
    assert write_contract.attestation_sha256 == "c" * 64
    assert write_contract.preserve_user_data_supported
    assert write_contract.wipe_user_data_supported
    assert not write_contract.bootloader_relock_allowed
    assert write_contract.writes[0].transport is DeviceWriteTransport.FASTBOOTD


def test_write_contract_schema_two_parses_exact_readback_and_post_boot_contract():
    parsed = DevicePackRegistry._parse_build_contract(
        _schema_two_build_contract_with_post_write_verification()
    )

    write_contract = parsed.partition_write_contract
    assert write_contract is not None and write_contract.version == 2
    verification = write_contract.post_write_verification_contract
    assert verification is not None
    assert verification.source_build_id == parsed.source.build_id
    assert verification.attestation_sha256 == write_contract.attestation_sha256
    assert verification.readbacks[0].partition == write_contract.writes[0].partition
    assert verification.readbacks[0].method.value == "fastboot_fetch_sha256"
    assert verification.post_boot_properties[0].property_name == "sys.boot_completed"
    assert verification.boot_timeout_seconds == 300


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (lambda value: value["readbacks"].clear(), "matching readback"),
        (
            lambda value: value["readbacks"][0].update(partition="boot"),
            "matching readback",
        ),
        (
            lambda value: value["readbacks"][0].update(method="fastboot_upload"),
            "transport or method",
        ),
        (
            lambda value: value.update(attestation_sha256="e" * 64),
            "partition-write attestation",
        ),
        (
            lambda value: value.update(require_adb_authorized=False),
            "require authorized ADB",
        ),
        (
            lambda value: value.update(boot_timeout_seconds=True),
            "30 to 900",
        ),
        (
            lambda value: value["post_boot_properties"].pop(),
            "missing required Device DNA",
        ),
    ),
)
def test_post_write_verification_contract_rejects_incomplete_or_unbound_rules(mutation, message):
    contract = _schema_two_build_contract_with_post_write_verification()
    mutation(contract["partition_write_contract"]["post_write_verification_contract"])

    with pytest.raises(ValueError, match=message):
        DevicePackRegistry._parse_build_contract(contract)


def test_post_write_verification_rejects_unsafe_property_and_non_exact_boot_values():
    unsafe = _schema_two_build_contract_with_post_write_verification()
    properties = unsafe["partition_write_contract"]["post_write_verification_contract"][
        "post_boot_properties"
    ]
    properties[0]["property_name"] = "persist.vendor.secret"
    with pytest.raises(ValueError, match="read-only allowlist"):
        DevicePackRegistry._parse_build_contract(unsafe)

    incomplete = _schema_two_build_contract_with_post_write_verification()
    values = incomplete["partition_write_contract"]["post_write_verification_contract"]
    values["post_boot_properties"][0]["expected_value"] = "0"
    with pytest.raises(ValueError, match="boot_completed=1"):
        DevicePackRegistry._parse_build_contract(incomplete)


def test_partition_write_schema_one_cannot_smuggle_post_write_authority():
    contract = _schema_two_build_contract_with_post_write_verification()
    contract["partition_write_contract"]["schema_version"] = 1

    with pytest.raises(ValueError, match="incomplete or unsupported"):
        DevicePackRegistry._parse_build_contract(contract)


def test_write_and_verification_schema_versions_reject_boolean_confusion():
    build_boolean = _schema_two_build_contract()
    build_boolean["schema_version"] = True
    with pytest.raises(ValueError, match="unsupported build contract schema"):
        DevicePackRegistry._parse_build_contract(build_boolean)

    write_boolean = _schema_two_build_contract()
    write_boolean["partition_write_contract"]["schema_version"] = True
    with pytest.raises(ValueError, match="unsupported partition-write contract schema"):
        DevicePackRegistry._parse_build_contract(write_boolean)

    verification_boolean = _schema_two_build_contract_with_post_write_verification()
    verification_boolean["partition_write_contract"]["post_write_verification_contract"][
        "schema_version"
    ] = True
    with pytest.raises(ValueError, match="unsupported post-write verification contract schema"):
        DevicePackRegistry._parse_build_contract(verification_boolean)


@pytest.mark.parametrize(
    "partition",
    (
        "userdata",
        "metadata",
        "bootloader_a",
        "unlock_control",
        "flashing_control",
        "erase_control",
    ),
)
def test_partition_write_contract_rejects_unsafe_targets(partition):
    contract = _schema_two_build_contract()
    contract["partition_write_contract"]["writes"][0]["partition"] = partition

    with pytest.raises(ValueError, match="unsafe partition-write target"):
        DevicePackRegistry._parse_build_contract(contract)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("source_build_id", "different-build", "exact source build"),
        ("attestation_sha256", "d" * 64, "exact flash-validated AVB attestation"),
        ("require_unlocked_bootloader", False, "unlocked bootloader"),
        ("bootloader_relock_allowed", True, "relocking is permanently prohibited"),
    ),
)
def test_partition_write_contract_rejects_mismatched_or_unsafe_authority(field, value, message):
    contract = _schema_two_build_contract()
    contract["partition_write_contract"][field] = value

    with pytest.raises(ValueError, match=message):
        DevicePackRegistry._parse_build_contract(contract)


def test_partition_write_contract_rejects_unknown_artifact_slot_and_duplicate_rules():
    unknown_artifact = _schema_two_build_contract()
    unknown_artifact["partition_write_contract"]["writes"][0]["artifact"] = "boot.img"
    with pytest.raises(ValueError, match="allowed image output"):
        DevicePackRegistry._parse_build_contract(unknown_artifact)

    implicit_slot = _schema_two_build_contract()
    implicit_slot["partition_write_contract"]["writes"][0]["target_slot"] = "active"
    with pytest.raises(ValueError, match="must be a, b, or none"):
        DevicePackRegistry._parse_build_contract(implicit_slot)

    suffixed_slot = _schema_two_build_contract()
    suffixed_slot["partition_write_contract"]["writes"][0]["partition"] = "super_a"
    with pytest.raises(ValueError, match="omit the slot suffix"):
        DevicePackRegistry._parse_build_contract(suffixed_slot)

    no_verification = _schema_two_build_contract()
    no_verification["partition_write_contract"]["writes"][0]["verify_after_write"] = False
    with pytest.raises(ValueError, match="verify every written image"):
        DevicePackRegistry._parse_build_contract(no_verification)

    duplicate = _schema_two_build_contract()
    duplicate["partition_write_contract"]["writes"].append(
        dict(duplicate["partition_write_contract"]["writes"][0])
    )
    with pytest.raises(ValueError, match="targets must be unique"):
        DevicePackRegistry._parse_build_contract(duplicate)


def test_build_contract_schema_versions_fail_closed_around_write_authority():
    schema_one_with_writes = _schema_two_build_contract()
    schema_one_with_writes["schema_version"] = 1
    with pytest.raises(ValueError, match="require build contract schema 2"):
        DevicePackRegistry._parse_build_contract(schema_one_with_writes)

    schema_two_without_writes = _schema_two_build_contract()
    schema_two_without_writes.pop("partition_write_contract")
    with pytest.raises(ValueError, match="requires a partition-write contract"):
        DevicePackRegistry._parse_build_contract(schema_two_without_writes)
