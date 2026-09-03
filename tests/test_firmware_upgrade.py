from romverse.rom.upgrade import FirmwareRelationship, assess_firmware_upgrade


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


def test_wrong_device_or_region_never_becomes_an_upgrade() -> None:
    wrong_device = _assess(
        "OS4.0.0.23.XPBCNXM",
        "OS4.0.0.25.XPBCNXM",
        target="miami",
    )
    wrong_region = _assess("OS4.0.0.23.XPBCNXM", "OS4.0.0.25.XPBMIXM")

    assert wrong_device.relationship is FirmwareRelationship.INCOMPATIBLE
    assert wrong_region.relationship is FirmwareRelationship.INCOMPATIBLE


def test_unknown_or_changed_branch_stays_unconfirmed() -> None:
    unknown = _assess("CP2A.260605.016", "OS4.0.0.25.XPBCNXM")
    unknown_region = _assess("OS4.0.0.23.XPBZZXM", "OS4.0.0.25.XPBZZXM")
    branch_change = _assess("OS4.0.0.23.XPBCNXM", "OS5.0.0.1.YPBCNXM")

    assert unknown.relationship is FirmwareRelationship.UNCONFIRMED
    assert unknown_region.relationship is FirmwareRelationship.UNCONFIRMED
    assert branch_change.relationship is FirmwareRelationship.UNCONFIRMED
