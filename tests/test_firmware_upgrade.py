import hashlib
import zipfile

from romverse.device.models import AndroidDevice, DeviceState
from romverse.rom.ota_metadata import parse_android_ota_metadata
from romverse.rom.projects import RomProjectStore
from romverse.rom.upgrade import (
    FirmwareRelationship,
    assess_firmware_upgrade,
    assess_project_firmware_upgrade,
)


def _assess(current: str, candidate: str, *, target: str = "popsicle"):
    return assess_firmware_upgrade(
        current_build=current,
        candidate_build=candidate,
        device_codename="popsicle",
        candidate_codename=target,
    )


def test_recognizes_numeric_same_device_same_region_hyperos_upgrade() -> None:
    result = _assess("OS4.0.0.23.XPBCNXM", "OS4.0.0.25.XPBCNXM")

    assert result.relationship is FirmwareRelationship.UPGRADE
    assert result.current_region == "China"
    assert result.candidate_region == "China"
    assert result.summary == ("UPGRADE CANDIDATE • OS4.0.0.23.XPBCNXM → OS4.0.0.25.XPBCNXM")
    assert result.user_supplied_source
    assert not result.install_authority
    assert not result.phone_changed


def test_version_comparison_is_numeric_not_lexical() -> None:
    result = _assess("OS4.0.0.9.XPBCNXM", "OS4.0.0.23.XPBCNXM")

    assert result.relationship is FirmwareRelationship.UPGRADE


def test_recognizes_same_version_and_downgrade_without_authorizing_either() -> None:
    same = _assess("OS4.0.0.23.XPBCNXM", "OS4.0.0.23.XPBCNXM")
    downgrade = _assess("OS4.0.0.25.XPBCNXM", "OS4.0.0.23.XPBCNXM")

    assert same.relationship is FirmwareRelationship.SAME
    assert downgrade.relationship is FirmwareRelationship.DOWNGRADE
    assert not same.install_authority
    assert not downgrade.install_authority


def test_wrong_device_is_incompatible_but_cross_channel_version_is_visible() -> None:
    wrong_device = _assess(
        "OS4.0.0.23.XPBCNXM",
        "OS4.0.0.25.XPBCNXM",
        target="miami",
    )
    wrong_region = _assess("OS4.0.0.23.XPBCNXM", "OS4.0.0.25.XPBMIXM")

    assert wrong_device.relationship is FirmwareRelationship.INCOMPATIBLE
    assert wrong_region.relationship is FirmwareRelationship.UPGRADE
    assert wrong_region.summary.startswith("CROSS-CHANNEL UPGRADE CANDIDATE")
    assert any("physical country" in reason for reason in wrong_region.reasons)
    assert any("incremental OTA" in reason for reason in wrong_region.reasons)
    assert not wrong_region.install_authority
    assert not wrong_region.phone_changed


def test_unknown_or_changed_branch_stays_unconfirmed() -> None:
    unknown = _assess("CP2A.260605.016", "OS4.0.0.25.XPBCNXM")
    unknown_region = _assess("OS4.0.0.23.XPBZZXM", "OS4.0.0.25.XPBZZXM")
    branch_change = _assess("OS4.0.0.23.XPBCNXM", "OS5.0.0.1.YPBCNXM")

    assert unknown.relationship is FirmwareRelationship.UNCONFIRMED
    assert unknown_region.relationship is FirmwareRelationship.UNCONFIRMED
    assert branch_change.relationship is FirmwareRelationship.UNCONFIRMED


def _android_ota(*, target: str = "komodo", timestamp: int = 200, pre_incremental="100"):
    return parse_android_ota_metadata(
        (
            f"pre-device={target}\n"
            f"pre-build-incremental={pre_incremental}\n"
            "post-build-incremental=200\n"
            "post-sdk-level=36\n"
            f"post-timestamp={timestamp}\n"
        ).encode()
    )


def test_generic_android_ota_metadata_identifies_an_upgrade_without_flash_authority() -> None:
    result = assess_firmware_upgrade(
        current_build="BP2A.260801.001",
        candidate_build="",
        device_codename="komodo",
        candidate_codename="",
        current_incremental="100",
        current_sdk_level="36",
        current_build_timestamp=100,
        ota_metadata=_android_ota(),
    )

    assert result.relationship is FirmwareRelationship.UPGRADE
    assert result.summary == "UPGRADE CANDIDATE • BP2A.260801.001 → 200"
    assert not result.install_authority
    assert not result.phone_changed


def test_same_oem_marketing_version_surfaces_newer_internal_ota_build_when_unmatched() -> None:
    metadata = parse_android_ota_metadata(
        b"pre-device=popsicle\n"
        b"post-build=Xiaomi/popsicle/popsicle:17/CP2A.260605.016/"
        b"17OS4.0.260821.223347094.QCPECN.S:user/release-keys\n"
        b"post-build-incremental=17OS4.0.260821.223347094.QCPECN.S\n"
        b"post-sdk-level=37\n"
        b"post-timestamp=1787328761\n"
    )

    result = assess_firmware_upgrade(
        current_build="OS4.0.0.25.XPBCNXM",
        candidate_build="OS4.0.0.25.XPBCNXM",
        device_codename="popsicle",
        candidate_codename="popsicle",
        current_fingerprint=(
            "Xiaomi/popsicle/popsicle:17/CP2A.260605.016/OS4.0.0.25.XPBCNXM:user/release-keys"
        ),
        current_incremental="OS4.0.0.25.XPBCNXM",
        current_sdk_level="37",
        current_build_timestamp=1787323440,
        ota_metadata=metadata,
    )

    assert result.relationship is FirmwareRelationship.UPGRADE
    assert result.summary == (
        "NEWER OTA BUILD CANDIDATE • OS4.0.0.25.XPBCNXM → 17OS4.0.260821.223347094.QCPECN.S"
    )
    assert any("marketing version matches" in reason for reason in result.reasons)
    assert not result.install_authority
    assert not result.phone_changed


def test_live_system_partition_identity_proves_the_ota_is_already_installed() -> None:
    internal = "17OS4.0.260821.223347094.QCPECN.S"
    system_fingerprint = (
        f"Android/generic_system/generic:17/CP2A.260605.016/{internal}:user/release-keys"
    )
    ota_fingerprint = f"Xiaomi/popsicle/popsicle:17/CP2A.260605.016/{internal}:user/release-keys"
    metadata = parse_android_ota_metadata(
        (
            "pre-device=popsicle\n"
            f"post-build={ota_fingerprint}\n"
            f"post-build-incremental={internal}\n"
            "post-sdk-level=37\n"
            "post-timestamp=1787328761\n"
        ).encode()
    )

    result = assess_firmware_upgrade(
        current_build="OS4.0.0.25.XPBCNXM",
        candidate_build="OS4.0.0.25.XPBCNXM",
        device_codename="popsicle",
        candidate_codename="popsicle",
        current_fingerprint=(
            "Xiaomi/popsicle/popsicle:17/CP2A.260605.016/OS4.0.0.25.XPBCNXM:user/release-keys"
        ),
        current_incremental="OS4.0.0.25.XPBCNXM",
        current_sdk_level="37",
        current_build_timestamp=1787323440,
        current_build_fingerprints=(system_fingerprint,),
        current_build_incrementals=(internal,),
        ota_metadata=metadata,
    )

    assert result.relationship is FirmwareRelationship.SAME
    assert result.summary == f"SAME INSTALLED OTA BUILD • {internal}"
    assert any("already reported" in reason for reason in result.reasons)
    assert not result.install_authority
    assert not result.phone_changed


def test_generic_android_ota_rejects_wrong_device_or_update_path() -> None:
    wrong_device = assess_firmware_upgrade(
        current_build="100",
        candidate_build="200",
        device_codename="husky",
        candidate_codename="",
        current_incremental="100",
        current_build_timestamp=100,
        ota_metadata=_android_ota(),
    )
    wrong_path = assess_firmware_upgrade(
        current_build="100",
        candidate_build="200",
        device_codename="komodo",
        candidate_codename="",
        current_incremental="99",
        current_build_timestamp=100,
        ota_metadata=_android_ota(),
    )

    assert wrong_device.relationship is FirmwareRelationship.INCOMPATIBLE
    assert wrong_path.relationship is FirmwareRelationship.INCOMPATIBLE


def test_generic_android_ota_stays_unconfirmed_without_comparable_timestamp() -> None:
    result = assess_firmware_upgrade(
        current_build="100",
        candidate_build="200",
        device_codename="komodo",
        candidate_codename="",
        current_incremental="100",
        ota_metadata=_android_ota(),
    )

    assert result.relationship is FirmwareRelationship.UNCONFIRMED


def test_project_review_binds_upgrade_classification_to_the_protected_source(tmp_path) -> None:
    source = tmp_path / "popsicle-ota_full-OS4.0.0.25.XPBCNXM-user-17.0-test.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("payload.bin", b"CrAU test")
        archive.writestr("META-INF/com/android/metadata", "ota-type=AB\n")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Upgrade review").project_id, source)
    device = AndroidDevice(
        "private-serial",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        model="2509FPN0BC",
        codename="popsicle",
        product="popsicle",
        rom_display="OS4.0.0.23.XPBCNXM",
    )

    review = assess_project_firmware_upgrade(store, project.project_id, device)

    assert review.assessment.relationship is FirmwareRelationship.UPGRADE
    assert review.assessment.summary.startswith("UPGRADE CANDIDATE")
    assert (
        review.source_sha256
        == hashlib.sha256(store.original_path(project.project_id).read_bytes()).hexdigest()
    )
    assert review.evidence_kind == "bounded vendor build identity"
    assert review.authority == "firmware-relationship-classification-only"
    assert not review.install_authority
    assert not review.phone_changed


def test_project_review_rejects_bad_ota_metadata_instead_of_falling_back_to_filename(
    tmp_path,
) -> None:
    source = tmp_path / "popsicle-ota_full-OS4.0.0.25.XPBCNXM-user-17.0-test.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("payload.bin", b"CrAU test")
        archive.writestr("META-INF/com/android/metadata", "not-a-valid-line\n")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Rejected metadata").project_id, source)
    device = AndroidDevice(
        "private-serial",
        DeviceState.DEVICE,
        codename="popsicle",
        rom_display="OS4.0.0.23.XPBCNXM",
    )

    review = assess_project_firmware_upgrade(store, project.project_id, device)

    assert review.metadata_error
    assert review.assessment.relationship is FirmwareRelationship.UNCONFIRMED
    assert any("will not replace rejected" in item for item in review.assessment.reasons)
    assert not review.install_authority
    assert not review.phone_changed
