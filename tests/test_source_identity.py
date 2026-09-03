from romverse.rom.source_identity import identify_firmware_source


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
