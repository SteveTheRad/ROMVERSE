import hashlib
import json

import pytest

from romverse.rom.source_identity import (
    CanonicalFirmwareIdentityError,
    canonical_firmware_identity_mapping,
    create_canonical_firmware_identity,
    identify_firmware_source,
    parse_canonical_firmware_identity,
)


def test_identifies_xiaomi_fastboot_base_used_by_the_active_project() -> None:
    identity = identify_firmware_source(
        "popsicle_images_OS3.0.318.0.WPBCNXM_20260804.0000.00_16.0_cn_f1a4098622.tgz"
    )

    assert identity.manufacturer == "Xiaomi"
    assert identity.codename == "popsicle"
    assert identity.build_id == "OS3.0.318.0.WPBCNXM"
    assert identity.android_version == "16.0"
    assert identity.region == "China"
    assert identity.package_type == "Xiaomi fastboot image archive"
    assert identity.confidence == "high"


def test_identifies_xiaomi_full_ota_without_granting_compatibility() -> None:
    identity = identify_firmware_source(
        "popsicle-ota_full-OS4.0.0.23.XPBCNXM-user-17.0-44eb547903.zip"
    )

    assert identity.codename == "popsicle"
    assert identity.build_id == "OS4.0.0.23.XPBCNXM"
    assert identity.android_version == "17.0"
    assert identity.region == "China"
    assert "distribution region" in " ".join(identity.evidence)
    assert "SHA-256" in " ".join(identity.evidence)


def test_unknown_source_remains_explicitly_unclassified() -> None:
    identity = identify_firmware_source("mystery-build.zip")

    assert identity.confidence == "unknown"
    assert not identity.build_id
    assert identity.package_type == "Unclassified ZIP firmware container"


def test_canonical_firmware_identity_is_artifact_bound_and_round_trips() -> None:
    device_id = hashlib.sha256(b"device").hexdigest()
    artifact = hashlib.sha256(b"firmware").hexdigest()
    layout = hashlib.sha256(b"partition-layout").hexdigest()
    identity = create_canonical_firmware_identity(
        canonical_device_id=device_id,
        model_variant="2509FPN0BC",
        region="China",
        build_id="OS4.0.0.35.XPBCNXM",
        firmware_version="4.0.0.35",
        android_version="17.0",
        security_patch="2026-08-01",
        artifact_sha256=artifact,
        partition_layout_digest=layout,
        evidence_claim_ids=("a" * 64, "b" * 64),
    )
    loaded = parse_canonical_firmware_identity(canonical_firmware_identity_mapping(identity))

    assert loaded == identity
    assert identity.compatibility_status == "UNCONFIRMED"
    assert identity.execution_authority == "none"
    assert not identity.phone_action_allowed
    assert not identity.guardian_approval
    assert not identity.bootloader_relock_allowed


def test_canonical_firmware_versions_models_regions_and_artifacts_do_not_inherit() -> None:
    common = {
        "canonical_device_id": "c" * 64,
        "model_variant": "2509FPN0BC",
        "region": "China",
        "build_id": "OS4.0.0.35.XPBCNXM",
        "artifact_sha256": "d" * 64,
        "evidence_claim_ids": ("e" * 64,),
    }
    first = create_canonical_firmware_identity(**common)
    changed_build = create_canonical_firmware_identity(
        **{**common, "build_id": "OS4.0.0.36.XPBCNXM"}
    )
    changed_model = create_canonical_firmware_identity(**{**common, "model_variant": "2509FPN0BG"})
    changed_region = create_canonical_firmware_identity(**{**common, "region": "Global"})
    changed_artifact = create_canonical_firmware_identity(**{**common, "artifact_sha256": "f" * 64})

    assert (
        len(
            {
                first.firmware_id,
                changed_build.firmware_id,
                changed_model.firmware_id,
                changed_region.firmware_id,
                changed_artifact.firmware_id,
            }
        )
        == 5
    )


def test_canonical_firmware_rejects_missing_digest_private_and_promoted_records() -> None:
    with pytest.raises(CanonicalFirmwareIdentityError, match="artifact"):
        create_canonical_firmware_identity(
            canonical_device_id="a" * 64,
            model_variant="SM-S928B",
            build_id="BUILD1",
            artifact_sha256="unknown",
            evidence_claim_ids=("b" * 64,),
        )
    with pytest.raises(CanonicalFirmwareIdentityError, match="private"):
        create_canonical_firmware_identity(
            canonical_device_id="a" * 64,
            model_variant="SM-S928B",
            build_id="username=steve",
            artifact_sha256="b" * 64,
            evidence_claim_ids=("c" * 64,),
        )
    with pytest.raises(CanonicalFirmwareIdentityError, match="private"):
        create_canonical_firmware_identity(
            canonical_device_id="a" * 64,
            model_variant="SM-S928B",
            build_id="123456789012345",
            artifact_sha256="b" * 64,
            evidence_claim_ids=("c" * 64,),
        )

    identity = create_canonical_firmware_identity(
        canonical_device_id="a" * 64,
        model_variant="SM-S928B",
        build_id="BUILD1",
        artifact_sha256="b" * 64,
        evidence_claim_ids=("c" * 64,),
    )
    raw = json.loads(json.dumps(canonical_firmware_identity_mapping(identity)))
    raw["compatibility_status"] = "SUPPORTED"
    with pytest.raises(CanonicalFirmwareIdentityError, match="promote"):
        parse_canonical_firmware_identity(raw)
