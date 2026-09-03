from __future__ import annotations

import fnmatch
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from romverse.device.models import AndroidDevice
from romverse.device_packs.attestations import (
    DevicePackAttestationVerifier,
    PhysicalRecoveryAttestationReport,
)
from romverse.device_packs.models import (
    AvbPolicyAuthority,
    CapabilityStatus,
    DeviceMode,
    DevicePack,
    DeviceRecoveryOperation,
    DeviceRecoveryStrategy,
    DeviceTransitionOperation,
    PartitionVerificationMethod,
)

_REQUIRED_POST_BOOT_PROPERTIES = frozenset(
    {
        "sys.boot_completed",
        "ro.product.device",
        "ro.build.fingerprint",
        "ro.build.version.incremental",
        "ro.build.version.sdk",
        "ro.build.version.security_patch",
        "ro.boot.verifiedbootstate",
    }
)
_ALLOWED_POST_BOOT_PROPERTIES = _REQUIRED_POST_BOOT_PROPERTIES | {
    "ro.product.manufacturer",
    "ro.product.model",
    "ro.build.id",
    "ro.build.type",
    "ro.build.tags",
    "ro.boot.slot_suffix",
    "ro.boot.veritymode",
    "ro.boot.vbmeta.device_state",
}


class ValidationState(StrEnum):
    PASS = "pass"
    ATTENTION = "attention"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class ValidationCheck:
    check_id: str
    label: str
    state: ValidationState
    evidence: str
    resolution: str
    required_for: str


@dataclass(frozen=True, slots=True)
class DevicePackValidationReport:
    schema_version: int
    report_id: str
    created_at: str
    pack_id: str
    pack_version: str
    pack_sha256: str
    manufacturer: str
    model: str
    product: str
    codename: str
    checks: tuple[ValidationCheck, ...]
    build_contract_ready: bool
    flash_contract_ready: bool
    report_digest: str

    @property
    def passed_count(self) -> int:
        return sum(check.state is ValidationState.PASS for check in self.checks)


@dataclass(frozen=True, slots=True)
class DevicePackNextAction:
    """One deterministic, zero-authority handoff from a current readiness report."""

    action_id: str
    check_id: str
    scope: str
    title: str
    detail: str
    route: str
    article_key: str
    button_label: str


@dataclass(frozen=True, slots=True)
class ValidationRequestExport:
    output_path: str
    sha256: str
    size_bytes: int


class DevicePackValidationService:
    """Evidence-only Device Pack validation; it cannot enable capabilities."""

    FORMAT = "romverse.device-pack-validation-request"
    PHYSICAL_REQUEST_FORMAT = "romverse.device-pack-physical-attestation-request"
    REPORT_SCHEMA_VERSION = 2

    def next_safe_action(self, report: DevicePackValidationReport) -> DevicePackNextAction:
        """Choose one explainable next step without changing readiness or authority."""

        checks = {check.check_id: check for check in report.checks}

        def unresolved(check_id: str) -> bool:
            check = checks.get(check_id)
            return check is not None and check.state is not ValidationState.PASS

        if not report.build_contract_ready:
            if unresolved("exact-model"):
                check = checks["exact-model"]
                return DevicePackNextAction(
                    "confirm-exact-identity",
                    check.check_id,
                    "build",
                    "Confirm the exact model contract",
                    f"{check.evidence}. {check.resolution}",
                    "archives",
                    "android-device-identity-catalog",
                    "Open exact identity guide",
                )
            for check_id in (
                "firmware-contract",
                "partition-layout",
                "declarative-build-contract",
            ):
                if unresolved(check_id):
                    check = checks[check_id]
                    return DevicePackNextAction(
                        f"resolve-{check.check_id}",
                        check.check_id,
                        "build",
                        f"Resolve build gate • {check.label}",
                        f"{check.evidence}. {check.resolution}",
                        "archives",
                        "device-pack-readiness-roadmap",
                        "Open build-readiness guide",
                    )
            return DevicePackNextAction(
                "review-build-readiness",
                "",
                "build",
                "Review the incomplete build contract",
                "One or more build gates are unresolved. Review the exact Device Pack evidence "
                "before creating a build plan.",
                "archives",
                "device-pack-readiness-roadmap",
                "Open build-readiness guide",
            )

        if not report.flash_contract_ready:
            if unresolved("stock-recovery-route"):
                check = checks["stock-recovery-route"]
                return DevicePackNextAction(
                    "prepare-stock-recovery",
                    check.check_id,
                    "flash",
                    "Prepare the exact stock recovery route",
                    f"{check.evidence}. Time Machine can collect and verify recovery evidence, "
                    "but it cannot certify a Pack or authorize a phone write.",
                    "time_machine",
                    "",
                    "Open Time Machine",
                )
            for check_id in (
                "physical-recovery-test",
                "avb-execution-policy",
                "partition-write-contract",
                "post-write-verification-contract",
                "transition-recovery-contract",
                "publisher-signature",
            ):
                if unresolved(check_id):
                    check = checks[check_id]
                    return DevicePackNextAction(
                        f"resolve-{check.check_id}",
                        check.check_id,
                        "flash",
                        f"Resolve flash gate • {check.label}",
                        f"{check.evidence}. {check.resolution}",
                        "archives",
                        "device-pack-readiness-roadmap",
                        "Open flash-readiness guide",
                    )
            return DevicePackNextAction(
                "review-flash-readiness",
                "",
                "flash",
                "Review the incomplete flash contract",
                "The build contract is ready, but independent flash evidence remains unresolved. "
                "No device-changing action is available.",
                "archives",
                "device-pack-readiness-roadmap",
                "Open flash-readiness guide",
            )

        return DevicePackNextAction(
            "continue-rom-studio",
            "",
            "ready",
            "Device Pack evidence is ready for project planning",
            "Continue with the exact current Device Pack in ROM Studio. Guardian still reviews "
            "the protected source, plan, approvals, and every future device-changing action.",
            "rom_studio",
            "",
            "Continue to ROM Studio",
        )

    def assess(
        self,
        pack: DevicePack,
        device: AndroidDevice,
        attestation: PhysicalRecoveryAttestationReport | None = None,
    ) -> DevicePackValidationReport:
        manufacturer = _bounded(device.manufacturer or "Unknown OEM")
        model = _bounded(device.model or "Unknown model")
        product = _bounded(device.product or "Unknown product")
        codename = _bounded(device.codename or device.product or "Unknown codename")
        exact_patterns = tuple(
            pattern
            for pattern in (*pack.model_patterns, *pack.product_patterns)
            if pattern not in {"", "*"}
        )
        exact_match = bool(
            exact_patterns
            and (
                _matches(model, pack.model_patterns)
                or _matches(product, pack.product_patterns)
                or _matches(codename, pack.product_patterns)
            )
        )
        firmware = next(
            (
                capability
                for capability in pack.capabilities
                if "firmware" in capability.capability_id
            ),
            None,
        )
        firmware_ready = bool(
            firmware
            and firmware.status is CapabilityStatus.SUPPORTED
            and firmware.scope != "locked"
        )
        partition = next(
            (
                capability
                for capability in pack.capabilities
                if "partition" in capability.capability_id
                or "firmware_layout" in capability.capability_id
            ),
            None,
        )
        partition_ready = bool(
            partition
            and partition.status is CapabilityStatus.SUPPORTED
            and partition.scope != "locked"
        )
        recovery = next(
            (
                capability
                for capability in pack.capabilities
                if "recovery" in capability.capability_id
            ),
            None,
        )
        recovery_ready = bool(
            recovery
            and recovery.status is CapabilityStatus.SUPPORTED
            and recovery.scope != "locked"
        )
        avb_policy = pack.build_contract.avb_execution_policy if pack.build_contract else None
        write_contract = (
            pack.build_contract.partition_write_contract if pack.build_contract else None
        )
        attestation_ready = bool(
            attestation
            and attestation.verified
            and attestation.pack_id == pack.pack_id
            and attestation.pack_sha256 == pack.sha256
            and pack.build_contract is not None
            and attestation.source_build_id == pack.build_contract.source.build_id
            and attestation.model.casefold() == model.casefold()
            and attestation.product.casefold() in {product.casefold(), codename.casefold()}
            and set(attestation.scenarios) == DevicePackAttestationVerifier.REQUIRED_SCENARIOS
        )
        avb_policy_ready = bool(
            avb_policy
            and avb_policy.authority is AvbPolicyAuthority.FLASH_VALIDATED
            and attestation_ready
            and attestation is not None
            and avb_policy.attestation_sha256 == attestation.envelope_sha256
        )
        write_contract_ready = bool(
            write_contract
            and avb_policy_ready
            and attestation is not None
            and pack.build_contract is not None
            and write_contract.source_build_id == pack.build_contract.source.build_id
            and write_contract.attestation_sha256 == attestation.envelope_sha256
            and write_contract.require_unlocked_bootloader
            and not write_contract.bootloader_relock_allowed
            and write_contract.writes
        )
        verification_contract = (
            write_contract.post_write_verification_contract if write_contract else None
        )
        post_boot_values = {
            item.property_name: item.expected_value
            for item in (
                verification_contract.post_boot_properties if verification_contract else ()
            )
        }
        write_targets = {
            (item.partition, item.transport, item.target_slot)
            for item in (write_contract.writes if write_contract else ())
        }
        readback_targets = {
            (item.partition, item.transport, item.target_slot)
            for item in (verification_contract.readbacks if verification_contract else ())
        }
        post_write_verification_ready = bool(
            write_contract_ready
            and write_contract is not None
            and write_contract.version in {2, 3}
            and verification_contract is not None
            and verification_contract.version == 1
            and pack.build_contract is not None
            and attestation is not None
            and verification_contract.source_build_id == pack.build_contract.source.build_id
            and verification_contract.attestation_sha256 == attestation.envelope_sha256
            and verification_contract.require_adb_authorized
            and 30 <= verification_contract.boot_timeout_seconds <= 900
            and len(verification_contract.readbacks) == len(write_contract.writes)
            and readback_targets == write_targets
            and all(
                item.method is PartitionVerificationMethod.FASTBOOT_FETCH_SHA256
                and type(item.expected_size_bytes) is int
                and 0 < item.expected_size_bytes <= 128 << 30
                and item.expected_size_bytes % 512 == 0
                and _is_sha256(item.expected_sha256)
                for item in verification_contract.readbacks
            )
            and len(post_boot_values) == len(verification_contract.post_boot_properties)
            and _REQUIRED_POST_BOOT_PROPERTIES.issubset(post_boot_values)
            and set(post_boot_values).issubset(_ALLOWED_POST_BOOT_PROPERTIES)
            and all(
                isinstance(value, str)
                and 1 <= len(value) <= 240
                and all(ord(character) >= 32 for character in value)
                for value in post_boot_values.values()
            )
            and post_boot_values.get("sys.boot_completed") == "1"
        )
        transition_contract = (
            write_contract.transition_recovery_contract if write_contract is not None else None
        )
        recovery_contract = (
            transition_contract.recovery if transition_contract is not None else None
        )
        transition_recovery_semantics_ready = False
        if write_contract is not None and pack.build_contract is not None:
            # Registry-loaded Packs already pass this parser. Repeating the strict check here also
            # prevents a constructed or replaced in-memory Pack from bypassing Device Atlas.
            from romverse.device_packs.registry import DevicePackRegistry

            transition_recovery_semantics_ready = (
                DevicePackRegistry.transition_recovery_contract_is_valid(
                    write_contract,
                    pack.build_contract.source,
                )
            )
        transition_recovery_ready = bool(
            post_write_verification_ready
            and transition_recovery_semantics_ready
            and write_contract is not None
            and write_contract.version == 3
            and transition_contract is not None
            and transition_contract.version == 1
            and pack.build_contract is not None
            and attestation is not None
            and transition_contract.source_build_id == pack.build_contract.source.build_id
            and transition_contract.attestation_sha256 == attestation.envelope_sha256
            and transition_contract.entry_mode in {DeviceMode.BOOTLOADER, DeviceMode.FASTBOOTD}
            and transition_contract.final_mode is DeviceMode.ANDROID
            and transition_contract.transitions
            and tuple(item.order for item in transition_contract.transitions)
            == tuple(range(1, len(transition_contract.transitions) + 1))
            and transition_contract.transitions[-1].operation
            is DeviceTransitionOperation.REBOOT_SYSTEM
            and transition_contract.final_consent_required
            and transition_contract.execution_authority == "none"
            and not transition_contract.bootloader_relock_allowed
            and recovery_contract is not None
            and recovery_contract.strategy
            in {
                DeviceRecoveryStrategy.STOCK_PACKAGE_RESTORE,
                DeviceRecoveryStrategy.RECORDED_SLOT_THEN_STOCK_PACKAGE,
            }
            and recovery_contract.stock_package_sha256 == pack.build_contract.source.archive_sha256
            and recovery_contract.require_external_backup
            and recovery_contract.require_stock_recovery
            and recovery_contract.actions
            and tuple(item.order for item in recovery_contract.actions)
            == tuple(range(1, len(recovery_contract.actions) + 1))
            and sum(
                item.operation is DeviceRecoveryOperation.RESTORE_STOCK_PACKAGE
                for item in recovery_contract.actions
            )
            == 1
            and recovery_contract.actions[-1].operation is DeviceRecoveryOperation.VERIFY_POST_BOOT
            and recovery_contract.actions[-1].to_mode is DeviceMode.ANDROID
            and recovery_contract.may_wipe_user_data
            == any(item.may_wipe_user_data for item in recovery_contract.actions)
            and not recovery_contract.automatic_wipe_allowed
            and not recovery_contract.bootloader_relock_allowed
        )
        checks = (
            ValidationCheck(
                "integrity",
                "Pack integrity index",
                ValidationState.PASS,
                f"Bundled SHA-256 verified: {pack.sha256[:16]}…",
                "Reload the signed or bundled pack if its digest changes.",
                "build",
            ),
            ValidationCheck(
                "exact-model",
                "Exact model and codename scope",
                ValidationState.PASS if exact_match else ValidationState.BLOCKED,
                (
                    f"Pack patterns match {model} / {codename}"
                    if exact_match
                    else "Pack is OEM-wide and does not declare this exact model/codename"
                ),
                "Publish explicit model/product patterns for this hardware; a manufacturer-only match is insufficient.",
                "build",
            ),
            ValidationCheck(
                "firmware-contract",
                "Firmware build capability",
                ValidationState.PASS if firmware_ready else ValidationState.BLOCKED,
                firmware.detail if firmware else "No firmware capability is declared",
                "A reviewed pack update must mark the model-specific firmware capability supported and non-locked.",
                "build",
            ),
            ValidationCheck(
                "partition-layout",
                "Partition and payload descriptors",
                ValidationState.PASS if partition_ready else ValidationState.BLOCKED,
                partition.detail
                if partition
                else "No validated partition-layout capability is declared",
                "Add versioned partition names, slot behavior, image formats, size constraints, and payload rules validated against this exact model.",
                "build",
            ),
            ValidationCheck(
                "declarative-build-contract",
                "Machine-readable build contract",
                ValidationState.PASS
                if pack.build_contract is not None
                else ValidationState.BLOCKED,
                (
                    f"Contract {pack.build_contract.contract_id} v{pack.build_contract.version}; editable: {', '.join(pack.build_contract.editable_partitions)}"
                    if pack.build_contract is not None
                    else "The pack has no bounded, declarative build contract"
                ),
                "Publish exact source hashes, partition sizes/groups, passthrough hashes, editable partitions, and allowed outputs in pack schema 2.",
                "build",
            ),
            ValidationCheck(
                "partition-write-contract",
                "Exact partition-to-artifact write contract",
                ValidationState.PASS if write_contract_ready else ValidationState.BLOCKED,
                (
                    f"Contract {write_contract.contract_id} v{write_contract.version} binds "
                    f"{len(write_contract.writes)} ordered image write(s) to signed exact-build "
                    "evidence; bootloader relocking is prohibited"
                    if write_contract_ready and write_contract is not None
                    else (
                        "A partition-write contract is declared, but its exact physical "
                        "attestation is not verified for this Pack, build, and phone"
                        if write_contract is not None
                        else "No explicit signed partition-to-artifact write contract is declared"
                    )
                ),
                "Publish a schema-two build contract with bounded image writes, explicit transport and slots, supported data modes, permanent relock prohibition, and the same exact signed physical-attestation digest as the AVB policy.",
                "flash",
            ),
            ValidationCheck(
                "post-write-verification-contract",
                "Exact readback and first-boot verification contract",
                (
                    ValidationState.PASS
                    if post_write_verification_ready
                    else ValidationState.BLOCKED
                ),
                (
                    f"Contract {verification_contract.contract_id} v{verification_contract.version} "
                    f"binds {len(verification_contract.readbacks)} full partition readback(s) and "
                    f"{len(verification_contract.post_boot_properties)} exact post-boot properties"
                    if post_write_verification_ready and verification_contract is not None
                    else (
                        "A write contract exists, but it has no signed exact partition-readback and "
                        "post-boot Device DNA contract"
                        if write_contract is not None
                        else "No partition write contract exists to verify"
                    )
                ),
                "Publish write-contract schema 2 or 3 with one physically tested full-partition Fastboot fetch digest per write, authorized-ADB first-boot properties, a bounded timeout, and the same exact signed physical-attestation digest.",
                "flash",
            ),
            ValidationCheck(
                "transition-recovery-contract",
                "Exact transition, slot and recovery orchestration contract",
                ValidationState.PASS if transition_recovery_ready else ValidationState.BLOCKED,
                (
                    f"Contract {transition_contract.contract_id} v{transition_contract.version} "
                    f"binds {len(transition_contract.transitions)} forward transition(s), "
                    f"{len(recovery_contract.actions)} recovery action(s), and exact stock package "
                    f"{recovery_contract.stock_package_sha256[:16]}… with zero execution authority"
                    if transition_recovery_ready
                    and transition_contract is not None
                    and recovery_contract is not None
                    else (
                        "A verified write/readback contract exists, but it has no signed exact "
                        "mode, slot, reboot and stock-recovery orchestration"
                        if post_write_verification_ready
                        else "Post-write verification must be proven before transition/recovery orchestration"
                    )
                ),
                "Publish write-contract schema 3 with a contiguous mode/slot sequence, exact source-bound stock-recovery adapter actions, backup requirements, wipe disclosure, separate final consent, zero execution authority, and permanent relock prohibition.",
                "flash",
            ),
            ValidationCheck(
                "avb-execution-policy",
                "Exact AVB execution policy",
                ValidationState.PASS if avb_policy_ready else ValidationState.BLOCKED,
                (
                    f"Flash-validated {avb_policy.mode.value} policy bound to signed evidence for {avb_policy.evidence_build_id}"
                    if avb_policy_ready and avb_policy is not None
                    else (
                        f"Historical {avb_policy.mode.value} evidence from {avb_policy.evidence_build_id} is reference-only"
                        if avb_policy is not None
                        and avb_policy.authority is AvbPolicyAuthority.REFERENCE_ONLY
                        else (
                            "Declared flash policy is not bound to the verified physical-attestation envelope"
                            if avb_policy is not None
                            else "No machine-readable AVB execution policy is declared"
                        )
                    )
                ),
                "Validate the exact firmware's AVB chain, required boot state, target slots, recovery path, and physical result; bind the signed attestation to this Device Pack.",
                "flash",
            ),
            ValidationCheck(
                "publisher-signature",
                "Publisher signature attestation",
                ValidationState.PASS if attestation_ready else ValidationState.ATTENTION,
                (
                    f"Ed25519 signer {attestation.signer_id} binds exact Pack {pack.sha256[:16]}…"
                    if attestation_ready and attestation is not None
                    else "Built-in SHA-256 integrity is present; no verified external publisher attestation is active"
                ),
                "Import an unexpired Ed25519 attestation from a trusted, non-revoked publisher key that binds this exact Pack digest.",
                "public-release",
            ),
            ValidationCheck(
                "stock-recovery-route",
                "Exact stock recovery route",
                ValidationState.PASS if recovery_ready else ValidationState.BLOCKED,
                recovery.detail
                if recovery
                else "No supported stock-recovery capability is declared",
                "Document exact stock firmware, verified hashes, required host tools, and a model-specific restore path.",
                "flash",
            ),
            ValidationCheck(
                "physical-recovery-test",
                "Independent physical recovery test",
                ValidationState.PASS if attestation_ready else ValidationState.BLOCKED,
                (
                    f"Signed report {attestation.report_sha256[:16]}… covers {', '.join(attestation.scenarios)}"
                    if attestation_ready and attestation is not None
                    else "No trusted signature proves recovery and first-boot tests on this exact hardware and Pack"
                ),
                "A pack maintainer must recover matching physical hardware from stock-restore, failed-flash, slot-recovery, and first-boot scenarios and publish a signed report.",
                "flash",
            ),
        )
        build_ready = all(
            check.state is ValidationState.PASS for check in checks if check.required_for == "build"
        )
        flash_ready = build_ready and all(
            check.state is ValidationState.PASS for check in checks if check.required_for == "flash"
        )
        digest_payload = {
            "schema_version": self.REPORT_SCHEMA_VERSION,
            "pack_id": pack.pack_id,
            "pack_version": pack.version,
            "pack_sha256": pack.sha256,
            "manufacturer": manufacturer,
            "model": model,
            "product": product,
            "codename": codename,
            "checks": [asdict(check) for check in checks],
            "build_contract_ready": build_ready,
            "flash_contract_ready": flash_ready,
        }
        digest = _digest(digest_payload)
        return DevicePackValidationReport(
            schema_version=self.REPORT_SCHEMA_VERSION,
            report_id=digest[:24],
            created_at=datetime.now(UTC).isoformat(),
            pack_id=pack.pack_id,
            pack_version=pack.version,
            pack_sha256=pack.sha256,
            manufacturer=manufacturer,
            model=model,
            product=product,
            codename=codename,
            checks=checks,
            build_contract_ready=build_ready,
            flash_contract_ready=flash_ready,
            report_digest=digest,
        )

    def export_request(
        self, report: DevicePackValidationReport, workspace: Path
    ) -> ValidationRequestExport:
        root = workspace.resolve() / "device_pack_requests"
        root.mkdir(parents=True, exist_ok=True)
        payload = {
            "format": self.FORMAT,
            **asdict(report),
            "privacy": {
                "serial_included": False,
                "imei_included": False,
                "accounts_included": False,
                "user_files_included": False,
            },
            "authority": "evidence-request-only",
            "capabilities_enabled": [],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        safe_pack = (
            "".join(
                character if character.isalnum() or character in ".-_" else "-"
                for character in report.pack_id
            ).strip(".-")
            or "device-pack"
        )
        destination = root / f"{safe_pack}-{digest[:16]}.romverse.json"
        temporary = root / f".{destination.name}.tmp-{uuid4().hex}"
        try:
            temporary.write_bytes(encoded)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        relative = destination.relative_to(workspace.resolve()).as_posix()
        return ValidationRequestExport(relative, digest, len(encoded))

    def export_physical_attestation_request(
        self,
        pack: DevicePack,
        report: DevicePackValidationReport,
        workspace: Path,
    ) -> ValidationRequestExport:
        """Export an exact, privacy-safe challenge for an independent physical test lab."""
        if (
            pack.build_contract is None
            or report.pack_id != pack.pack_id
            or report.pack_version != pack.version
            or report.pack_sha256 != pack.sha256
        ):
            raise ValueError("Validation report does not bind the exact Device Pack contract")
        root = workspace.resolve() / "device_pack_requests"
        root.mkdir(parents=True, exist_ok=True)
        payload = {
            "format": self.PHYSICAL_REQUEST_FORMAT,
            "schema_version": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "pack_id": pack.pack_id,
            "pack_version": pack.version,
            "pack_sha256": pack.sha256,
            "source_build_id": pack.build_contract.source.build_id,
            "model": report.model,
            "product": report.product,
            "codename": report.codename,
            "required_signature_algorithm": "ed25519",
            "required_scenarios": sorted(DevicePackAttestationVerifier.REQUIRED_SCENARIOS),
            "expected_result": "pass",
            "privacy": {
                "serial_included": False,
                "imei_included": False,
                "accounts_included": False,
                "user_files_included": False,
            },
            "authority": "physical-test-request-only",
            "capabilities_enabled": [],
            "instructions": (
                "Test every required scenario on matching physical hardware, publish the "
                "content-addressed report, and return a detached Ed25519-signed ROMVERSE "
                "physical-attestation envelope. This request grants no device authority."
            ),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        safe_pack = (
            "".join(
                character if character.isalnum() or character in ".-_" else "-"
                for character in pack.pack_id
            ).strip(".-")
            or "device-pack"
        )
        destination = root / f"{safe_pack}-physical-test-{digest[:16]}.romverse.json"
        temporary = root / f".{destination.name}.tmp-{uuid4().hex}"
        try:
            temporary.write_bytes(encoded)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        relative = destination.relative_to(workspace.resolve()).as_posix()
        return ValidationRequestExport(relative, digest, len(encoded))


def _matches(value: str, patterns: tuple[str, ...]) -> bool:
    normalized = value.casefold().strip()
    return any(
        pattern not in {"", "*"} and fnmatch.fnmatchcase(normalized, pattern.casefold())
        for pattern in patterns
    )


def _bounded(value: str) -> str:
    clean = "".join(character for character in value.strip() if ord(character) >= 32)
    return clean[:120] or "Unknown"


def _digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
