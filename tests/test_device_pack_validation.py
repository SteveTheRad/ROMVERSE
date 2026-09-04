import json
from dataclasses import replace
from importlib.resources import files

from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.attestations import PhysicalRecoveryAttestationReport
from romverse.device_packs.models import (
    AvbPolicyAuthority,
    CapabilityStatus,
    DeviceMode,
    DeviceModeTransitionRule,
    DevicePack,
    DevicePostWriteVerificationContract,
    DeviceRecoveryActionRule,
    DeviceRecoveryContract,
    DeviceRecoveryOperation,
    DeviceRecoveryStrategy,
    DeviceTransitionOperation,
    DeviceTransitionRecoveryContract,
    DeviceWriteContract,
    DeviceWriteTransport,
    PackCapability,
    PartitionReadbackRule,
    PartitionVerificationMethod,
    PartitionWriteRule,
    PostBootPropertyRule,
)
from romverse.device_packs.registry import DevicePackRegistry
from romverse.device_packs.validation import DevicePackValidationService, ValidationState


def _xiaomi() -> AndroidDevice:
    return AndroidDevice(
        serial="private-serial-never-exported",
        state=DeviceState.DEVICE,
        manufacturer="Xiaomi",
        model="2509FPN0BC",
        product="popsicle_global",
        codename="popsicle",
    )


def test_builtin_xiaomi_pack_fails_closed_without_exact_contract() -> None:
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    pack = next(item for item in registry.packs if item.pack_id == "xiaomi.hyperos")

    report = DevicePackValidationService().assess(pack, _xiaomi())

    checks = {check.check_id: check for check in report.checks}
    assert checks["integrity"].state is ValidationState.PASS
    assert checks["exact-model"].state is ValidationState.BLOCKED
    assert checks["partition-layout"].state is ValidationState.BLOCKED
    assert checks["declarative-build-contract"].state is ValidationState.BLOCKED
    assert not report.build_contract_ready
    assert not report.flash_contract_ready


def test_observed_s24_ultra_pack_passes_identity_but_grants_no_build_or_flash() -> None:
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    device = AndroidDevice(
        serial="private-serial-never-exported",
        state=DeviceState.DEVICE,
        manufacturer="samsung",
        model="SM-S928B",
        product="e3q",
        codename="e3q",
    )
    pack = registry.resolve(device).pack

    assert pack is not None
    assert pack.pack_id == "samsung.galaxy-s24-ultra.sm-s928b"
    report = DevicePackValidationService().assess(pack, device)
    checks = {check.check_id: check for check in report.checks}
    assert checks["integrity"].state is ValidationState.PASS
    assert checks["exact-model"].state is ValidationState.PASS
    assert checks["declarative-build-contract"].state is ValidationState.BLOCKED
    assert not report.build_contract_ready
    assert not report.flash_contract_ready


def test_capability_labels_without_declarative_contract_cannot_reach_build_readiness() -> None:
    pack = DevicePack(
        "xiaomi.popsicle",
        "1.0.0",
        "Xiaomi popsicle",
        200,
        ("xiaomi",),
        ("2509fpn0bc",),
        ("popsicle*",),
        (
            PackCapability(
                "firmware.operations",
                "Firmware operations",
                CapabilityStatus.SUPPORTED,
                "model_specific",
                "Reviewed build contract",
            ),
            PackCapability(
                "firmware.partition-layout",
                "Partition layout",
                CapabilityStatus.SUPPORTED,
                "model_specific",
                "Versioned A/B descriptors",
            ),
            PackCapability(
                "stock.recovery",
                "Stock recovery",
                CapabilityStatus.SUPPORTED,
                "model_specific",
                "Verified stock restore inputs",
            ),
        ),
        (),
        "a" * 64,
    )

    report = DevicePackValidationService().assess(pack, _xiaomi())

    assert not report.build_contract_ready
    assert not report.flash_contract_ready
    contract = next(
        check for check in report.checks if check.check_id == "declarative-build-contract"
    )
    assert contract.state is ValidationState.BLOCKED


def test_builtin_exact_contract_reaches_local_build_but_not_flash_readiness() -> None:
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    pack = registry.resolve(_xiaomi()).pack
    assert pack is not None

    report = DevicePackValidationService().assess(pack, _xiaomi())

    assert report.build_contract_ready
    assert not report.flash_contract_ready
    avb = next(check for check in report.checks if check.check_id == "avb-execution-policy")
    assert avb.state is ValidationState.BLOCKED
    assert "reference-only" in avb.evidence
    physical = next(check for check in report.checks if check.check_id == "physical-recovery-test")
    assert physical.state is ValidationState.BLOCKED


def test_next_safe_action_routes_exact_build_ready_pack_to_stock_recovery() -> None:
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    pack = registry.resolve(_xiaomi()).pack
    assert pack is not None
    service = DevicePackValidationService()

    action = service.next_safe_action(service.assess(pack, _xiaomi()))

    assert action.action_id == "prepare-stock-recovery"
    assert action.check_id == "stock-recovery-route"
    assert action.scope == "flash"
    assert action.route == "time_machine"
    assert action.article_key == ""
    assert "cannot certify" in action.detail


def test_next_safe_action_routes_unknown_model_to_exact_identity_guide() -> None:
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    pack = next(item for item in registry.packs if item.pack_id == "android.generic")
    service = DevicePackValidationService()
    device = AndroidDevice(
        "private-unknown",
        DeviceState.DEVICE,
        manufacturer="Example",
        model="EX-100",
        product="nebula",
        codename="nebula",
    )

    action = service.next_safe_action(service.assess(pack, device))

    assert action.action_id == "confirm-exact-identity"
    assert action.check_id == "exact-model"
    assert action.scope == "build"
    assert action.route == "archives"
    assert action.article_key == "android-device-identity-catalog"


def _verified_attestation(pack: DevicePack) -> PhysicalRecoveryAttestationReport:
    assert pack.build_contract is not None
    return PhysicalRecoveryAttestationReport(
        verified=True,
        signer_id="radforge-release-2026",
        pack_id=pack.pack_id,
        pack_sha256=pack.sha256,
        source_build_id=pack.build_contract.source.build_id,
        model="2509FPN0BC",
        product="popsicle_global",
        scenarios=(
            "stock_restore",
            "failed_flash_recovery",
            "slot_recovery",
            "first_boot_validation",
        ),
        report_sha256="b" * 64,
        issued_at="2026-08-29T00:00:00+00:00",
        expires_at="2027-08-29T00:00:00+00:00",
        envelope_sha256="c" * 64,
        reason="Test fixture already verified by the cryptographic verifier",
    )


def test_exact_physical_attestation_clears_only_its_evidence_checks() -> None:
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    pack = registry.resolve(_xiaomi()).pack
    assert pack is not None

    report = DevicePackValidationService().assess(
        pack,
        _xiaomi(),
        _verified_attestation(pack),
    )

    checks = {check.check_id: check for check in report.checks}
    assert checks["publisher-signature"].state is ValidationState.PASS
    assert checks["physical-recovery-test"].state is ValidationState.PASS
    assert checks["avb-execution-policy"].state is ValidationState.BLOCKED
    assert checks["stock-recovery-route"].state is ValidationState.BLOCKED
    assert not report.flash_contract_ready


def test_exact_write_contract_passes_only_with_matching_physical_attestation() -> None:
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    base = registry.resolve(_xiaomi()).pack
    assert base is not None and base.build_contract is not None
    assert base.build_contract.avb_execution_policy is not None
    envelope_sha256 = "c" * 64
    avb = replace(
        base.build_contract.avb_execution_policy,
        authority=AvbPolicyAuthority.FLASH_VALIDATED,
        evidence_build_id=base.build_contract.source.build_id,
        attestation_sha256=envelope_sha256,
    )
    writes = DeviceWriteContract(
        "validated-writes",
        1,
        base.build_contract.source.build_id,
        envelope_sha256,
        True,
        avb.require_critical_unlocked,
        True,
        True,
        (
            PartitionWriteRule(
                "super",
                "super.img",
                DeviceWriteTransport.FASTBOOTD,
                "none",
                True,
            ),
        ),
    )
    pack = replace(
        base,
        build_contract=replace(
            base.build_contract,
            version=2,
            avb_execution_policy=avb,
            partition_write_contract=writes,
        ),
    )

    without_attestation = DevicePackValidationService().assess(pack, _xiaomi())
    with_attestation = DevicePackValidationService().assess(
        pack, _xiaomi(), _verified_attestation(pack)
    )
    with_wrong_attestation = DevicePackValidationService().assess(
        pack,
        _xiaomi(),
        replace(_verified_attestation(pack), envelope_sha256="d" * 64),
    )

    missing_check = next(
        check
        for check in without_attestation.checks
        if check.check_id == "partition-write-contract"
    )
    verified_check = next(
        check for check in with_attestation.checks if check.check_id == "partition-write-contract"
    )
    wrong_check = next(
        check
        for check in with_wrong_attestation.checks
        if check.check_id == "partition-write-contract"
    )
    assert missing_check.state is ValidationState.BLOCKED
    assert wrong_check.state is ValidationState.BLOCKED
    assert verified_check.state is ValidationState.PASS
    assert "relocking is prohibited" in verified_check.evidence
    post_write_check = next(
        check
        for check in with_attestation.checks
        if check.check_id == "post-write-verification-contract"
    )
    assert post_write_check.state is ValidationState.BLOCKED
    assert not with_attestation.flash_contract_ready


def test_exact_post_write_contract_is_required_for_flash_contract_readiness() -> None:
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    base = registry.resolve(_xiaomi()).pack
    assert base is not None and base.build_contract is not None
    assert base.build_contract.avb_execution_policy is not None
    envelope_sha256 = "c" * 64
    avb = replace(
        base.build_contract.avb_execution_policy,
        authority=AvbPolicyAuthority.FLASH_VALIDATED,
        evidence_build_id=base.build_contract.source.build_id,
        attestation_sha256=envelope_sha256,
    )
    verification = DevicePostWriteVerificationContract(
        "validated-post-write",
        1,
        base.build_contract.source.build_id,
        envelope_sha256,
        (
            PartitionReadbackRule(
                "super",
                DeviceWriteTransport.FASTBOOTD,
                "none",
                PartitionVerificationMethod.FASTBOOT_FETCH_SHA256,
                base.build_contract.super_size_bytes,
                "d" * 64,
            ),
        ),
        (
            PostBootPropertyRule("sys.boot_completed", "1"),
            PostBootPropertyRule("ro.product.device", "popsicle"),
            PostBootPropertyRule("ro.build.fingerprint", "xiaomi/popsicle/test"),
            PostBootPropertyRule("ro.build.version.incremental", "TEST.1"),
            PostBootPropertyRule("ro.build.version.sdk", "37"),
            PostBootPropertyRule("ro.build.version.security_patch", "2026-08-01"),
            PostBootPropertyRule("ro.boot.verifiedbootstate", "orange"),
        ),
        True,
        300,
    )
    transition = DeviceTransitionRecoveryContract(
        "validated-transition-recovery",
        1,
        base.build_contract.source.build_id,
        envelope_sha256,
        DeviceMode.BOOTLOADER,
        (
            DeviceModeTransitionRule(
                1,
                0,
                DeviceTransitionOperation.REBOOT_FASTBOOTD,
                DeviceMode.BOOTLOADER,
                DeviceMode.FASTBOOTD,
                "none",
                60,
            ),
            DeviceModeTransitionRule(
                2,
                1,
                DeviceTransitionOperation.REBOOT_SYSTEM,
                DeviceMode.FASTBOOTD,
                DeviceMode.ANDROID,
                "none",
                300,
            ),
        ),
        DeviceMode.ANDROID,
        DeviceRecoveryContract(
            DeviceRecoveryStrategy.STOCK_PACKAGE_RESTORE,
            "xiaomi.fastboot.stock",
            base.build_contract.source.archive_sha256,
            DeviceMode.BOOTLOADER,
            (
                DeviceRecoveryActionRule(
                    1,
                    DeviceRecoveryOperation.RESTORE_STOCK_PACKAGE,
                    "xiaomi.fastboot.stock.restore",
                    DeviceMode.BOOTLOADER,
                    DeviceMode.BOOTLOADER,
                    "none",
                    1800,
                    True,
                ),
                DeviceRecoveryActionRule(
                    2,
                    DeviceRecoveryOperation.REBOOT_SYSTEM,
                    "xiaomi.fastboot.stock.reboot",
                    DeviceMode.BOOTLOADER,
                    DeviceMode.ANDROID,
                    "none",
                    300,
                    False,
                ),
                DeviceRecoveryActionRule(
                    3,
                    DeviceRecoveryOperation.VERIFY_POST_BOOT,
                    "xiaomi.fastboot.stock.verify",
                    DeviceMode.ANDROID,
                    DeviceMode.ANDROID,
                    "none",
                    300,
                    False,
                ),
            ),
            True,
            True,
            False,
            True,
            False,
            False,
        ),
        True,
        "none",
        False,
    )
    writes = DeviceWriteContract(
        "validated-writes",
        3,
        base.build_contract.source.build_id,
        envelope_sha256,
        True,
        avb.require_critical_unlocked,
        True,
        True,
        (
            PartitionWriteRule(
                "super",
                "super.img",
                DeviceWriteTransport.FASTBOOTD,
                "none",
                True,
            ),
        ),
        post_write_verification_contract=verification,
        transition_recovery_contract=transition,
    )
    pack = replace(
        base,
        capabilities=tuple(
            replace(item, status=CapabilityStatus.SUPPORTED)
            if "recovery" in item.capability_id
            else item
            for item in base.capabilities
        ),
        build_contract=replace(
            base.build_contract,
            version=2,
            avb_execution_policy=avb,
            partition_write_contract=writes,
        ),
    )

    report = DevicePackValidationService().assess(pack, _xiaomi(), _verified_attestation(pack))

    checks = {check.check_id: check for check in report.checks}
    assert checks["partition-write-contract"].state is ValidationState.PASS
    assert checks["post-write-verification-contract"].state is ValidationState.PASS
    assert checks["transition-recovery-contract"].state is ValidationState.PASS
    assert report.flash_contract_ready

    unsafe_transition = replace(
        transition,
        transitions=(
            replace(transition.transitions[0], after_write_order=1),
            *transition.transitions[1:],
        ),
    )
    unsafe_pack = replace(
        pack,
        build_contract=replace(
            pack.build_contract,
            partition_write_contract=replace(
                writes,
                transition_recovery_contract=unsafe_transition,
            ),
        ),
    )
    unsafe_report = DevicePackValidationService().assess(
        unsafe_pack,
        _xiaomi(),
        _verified_attestation(unsafe_pack),
    )
    unsafe_checks = {check.check_id: check for check in unsafe_report.checks}
    assert unsafe_checks["transition-recovery-contract"].state is ValidationState.BLOCKED
    assert not unsafe_report.flash_contract_ready


def test_attestation_for_different_hardware_cannot_clear_recovery_gate() -> None:
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    pack = registry.resolve(_xiaomi()).pack
    assert pack is not None
    attestation = _verified_attestation(pack)
    wrong_hardware = replace(
        attestation,
        model="Different model",
        product="different_product",
    )

    report = DevicePackValidationService().assess(pack, _xiaomi(), wrong_hardware)

    checks = {check.check_id: check for check in report.checks}
    assert checks["publisher-signature"].state is ValidationState.ATTENTION
    assert checks["physical-recovery-test"].state is ValidationState.BLOCKED
    assert not report.flash_contract_ready


def test_attestation_for_different_source_build_cannot_clear_recovery_gate() -> None:
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    pack = registry.resolve(_xiaomi()).pack
    assert pack is not None
    wrong_source = replace(
        _verified_attestation(pack),
        source_build_id="different-build",
    )

    report = DevicePackValidationService().assess(pack, _xiaomi(), wrong_source)

    checks = {check.check_id: check for check in report.checks}
    assert checks["publisher-signature"].state is ValidationState.ATTENTION
    assert checks["physical-recovery-test"].state is ValidationState.BLOCKED


def test_validation_request_is_privacy_safe_and_enables_nothing(tmp_path) -> None:
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    device = AndroidDevice(
        serial="PRIVATE-SERIAL",
        state=DeviceState.DEVICE,
        manufacturer="Xiaomi\x00",
        model="2509FPN0BC\n",
        product="popsicle_global",
        codename="popsicle",
    )
    pack = registry.resolve(device).pack
    assert pack is not None
    service = DevicePackValidationService()

    exported = service.export_request(service.assess(pack, device), tmp_path)
    payload = json.loads((tmp_path / exported.output_path).read_text())
    encoded = json.dumps(payload)

    assert payload["format"] == service.FORMAT
    assert payload["authority"] == "evidence-request-only"
    assert payload["capabilities_enabled"] == []
    assert payload["privacy"] == {
        "serial_included": False,
        "imei_included": False,
        "accounts_included": False,
        "user_files_included": False,
    }
    assert "PRIVATE-SERIAL" not in encoded
    assert "\x00" not in encoded
    assert exported.size_bytes > 0


def test_physical_test_request_is_exact_privacy_safe_and_enables_nothing(tmp_path) -> None:
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    device = _xiaomi()
    pack = registry.resolve(device).pack
    assert pack is not None and pack.build_contract is not None
    service = DevicePackValidationService()

    exported = service.export_physical_attestation_request(
        pack,
        service.assess(pack, device),
        tmp_path,
    )
    payload = json.loads((tmp_path / exported.output_path).read_text())
    encoded = json.dumps(payload)

    assert payload["format"] == service.PHYSICAL_REQUEST_FORMAT
    assert payload["pack_sha256"] == pack.sha256
    assert payload["source_build_id"] == pack.build_contract.source.build_id
    assert set(payload["required_scenarios"]) == {
        "stock_restore",
        "failed_flash_recovery",
        "slot_recovery",
        "first_boot_validation",
    }
    assert payload["authority"] == "physical-test-request-only"
    assert payload["capabilities_enabled"] == []
    assert "private-serial-never-exported" not in encoded
    assert exported.size_bytes > 0
