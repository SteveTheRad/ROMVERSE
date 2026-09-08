"""Run one complete Guided Recovery journey with strictly inert local evidence.

The output directory must be new. No Android tool, subprocess, firmware command,
physical phone, production adapter, or existing ROMVERSE workspace is used. The
script exercises ROMVERSE's production Recovery services with an in-memory phone
transport and an ephemeral test-only signing identity, then emits a JSON report.
It is simulation evidence only and can never authorize real device execution.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from romverse.device.engine import DeviceEngine
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.models import (
    AvbExecutionPolicy,
    AvbPolicyAuthority,
    AvbPolicyMode,
    CapabilityStatus,
    DeviceBuildContract,
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
    FirmwareSourceContract,
    PackCapability,
    PartitionReadbackRule,
    PartitionVerificationMethod,
    PartitionWriteRule,
    PostBootPropertyRule,
)
from romverse.device_packs.registry import DevicePackRegistry
from romverse.guardian.recovery_adapter_package import (
    GuardianRecoveryAdapterReleaseTrustRoot,
    RecoveryAdapterTrustScope,
    build_guardian_recovery_adapter_manifest,
    create_signed_guardian_recovery_adapter_package,
    verify_guardian_recovery_adapter_package,
)
from romverse.guardian.recovery_adapter_runner import GuardianRecoveryAdapterRunner
from romverse.guardian.recovery_consent import GuardianRecoveryConsentReceiptService
from romverse.guardian.recovery_execution import (
    GuardianRecoveryExecutionService,
    RecoveryStepOutcome,
)
from romverse.guardian.recovery_execution_result import (
    GuardianRecoveryExecutionResultService,
)
from romverse.guardian.recovery_live_target import GuardianRecoveryLiveTargetReceiptService
from romverse.guardian.recovery_preparation import GuardianRecoveryPreparationService
from romverse.guardian.recovery_runtime_adapter import (
    GuardianTrustedRecoveryProcessAdapter,
    RecoveryAdapterProcessResult,
)
from romverse.guardian.recovery_step_target import GuardianRecoveryStepTargetService
from romverse.infrastructure.process import CommandResult
from romverse.repair.autopilot import (
    RecoveryAutopilotContext,
    RecoveryAutopilotService,
    RecoveryIncidentState,
    RecoveryRouteKind,
    RecoveryTrigger,
)
from romverse.rom.boot_observation import BootObservationService
from romverse.rom.projects import RomProjectStore
from romverse.rom.recovery_evidence import RecoveryEvidenceService
from romverse.ui.recovery_operation_session import (
    RecoveryOperationPhase,
    RecoveryOperationSession,
)

SIMULATED_AT = datetime(2026, 9, 5, 10, 0, tzinfo=UTC)
SERIAL = "ROMVERSE-INERT-0001"
PRODUCT = "romverse_simulator"
BUILD_ID = "SIM.RECOVERY.1"
BUILD_FINGERPRINT = (
    "radforge/romverse_simulator/romverse_simulator:17/SIM.RECOVERY.1/1:userdebug/test-keys"
)


class InertPhone:
    """A bounded state model. It exposes observations but cannot run a command."""

    def __init__(self) -> None:
        self.mode = "bootloader"
        self.adapter_actions: list[str] = []


class InertAdb:
    def __init__(self, phone: InertPhone) -> None:
        self.phone = phone
        self.discovery_count = 0
        self.probe_ids: list[str] = []

    def devices(self) -> CommandResult:
        self.discovery_count += 1
        rows = f"{SERIAL}\tdevice usb:1-1\n" if self.phone.mode == "android" else ""
        return CommandResult(
            ("inert-adb", "devices", "-l"),
            0,
            f"List of devices attached\n{rows}",
            "",
        )

    def probe(
        self,
        serial: str,
        probe_id: str,
        args: tuple[str, ...],
        timeout: float = 4,
    ) -> CommandResult:
        if serial != SERIAL or timeout != 4 or self.phone.mode != "android":
            raise AssertionError("Inert ADB probe escaped the exact simulated target")
        values = {
            "ro.product.device": PRODUCT,
            "sys.boot_completed": "1",
            "ro.boot.slot_suffix": "_a",
        }
        if args[-1] not in values:
            raise AssertionError(f"Unexpected inert ADB property: {args[-1]}")
        self.probe_ids.append(probe_id)
        return CommandResult(("inert-adb", *args), 0, values[args[-1]] + "\n", "")


class InertFastboot:
    def __init__(self, phone: InertPhone) -> None:
        self.phone = phone
        self.discovery_count = 0
        self.variables: list[str] = []

    def devices(self) -> CommandResult:
        self.discovery_count += 1
        rows = f"{SERIAL}\tfastboot usb:1-1\n" if self.phone.mode != "android" else ""
        return CommandResult(("inert-fastboot", "devices", "-l"), 0, rows, "")

    def getvar(self, serial: str, variable: str, timeout: float = 4) -> CommandResult:
        if serial != SERIAL or timeout != 4 or self.phone.mode == "android":
            raise AssertionError("Inert Fastboot probe escaped the exact simulated target")
        values = {
            "product": PRODUCT,
            "current-slot": "a",
            "unlocked": "yes",
            "secure": "yes",
            "is-userspace": "yes" if self.phone.mode == "fastbootd" else "no",
        }
        if variable not in values:
            raise AssertionError(f"Unexpected inert Fastboot variable: {variable}")
        self.variables.append(variable)
        return CommandResult(
            ("inert-fastboot", "getvar", variable),
            0,
            "",
            f"(bootloader) {variable}: {values[variable]}\nOKAY\n",
        )


class InertRecoveryProcess:
    """Return one strict protocol result and only mutate the in-memory phone model."""

    def __init__(self, phone: InertPhone) -> None:
        self.phone = phone
        self.invocations: list[dict[str, object]] = []

    def run(self, package, request_bytes: bytes, timeout_seconds: int):
        request = json.loads(request_bytes)
        if timeout_seconds != request["timeout_seconds"]:
            raise AssertionError("Inert adapter timeout escaped its sealed request")
        self.invocations.append(request)
        self.phone.adapter_actions.append(str(request["adapter_action_id"]))
        self.phone.mode = str(request["expected_to_mode"])
        evidence = hashlib.sha256(
            json.dumps(
                {
                    "simulation_only": True,
                    "request_digest": request["request_digest"],
                    "step_order": request["step_order"],
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("ascii")
        ).hexdigest()
        response = {
            "schema_version": 1,
            "protocol_version": 1,
            "request_digest": request["request_digest"],
            "package_sha256": package.package_sha256,
            "adapter_id": request["adapter_id"],
            "adapter_version": package.manifest.adapter_version,
            "adapter_action_id": request["adapter_action_id"],
            "step_order": request["step_order"],
            "outcome": RecoveryStepOutcome.SUCCEEDED.value,
            "dispatch_started": True,
            "timed_out": False,
            "evidence_sha256": evidence,
        }
        encoded = json.dumps(
            response,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
        return RecoveryAdapterProcessResult(True, 0, encoded, b"", False, False)


def _simulated_pack(source_sha256: str) -> DevicePack:
    attestation = "a" * 64
    source = FirmwareSourceContract(BUILD_ID, source_sha256, "b" * 64)
    write_rule = PartitionWriteRule(
        "super",
        "super.img",
        DeviceWriteTransport.FASTBOOTD,
        "none",
        True,
    )
    verification = DevicePostWriteVerificationContract(
        "simulation-post-write",
        1,
        BUILD_ID,
        attestation,
        (
            PartitionReadbackRule(
                "super",
                DeviceWriteTransport.FASTBOOTD,
                "none",
                PartitionVerificationMethod.FASTBOOT_FETCH_SHA256,
                4096,
                "c" * 64,
            ),
        ),
        (
            PostBootPropertyRule("sys.boot_completed", "1"),
            PostBootPropertyRule("ro.product.device", PRODUCT),
            PostBootPropertyRule("ro.build.fingerprint", BUILD_FINGERPRINT),
            PostBootPropertyRule("ro.build.version.incremental", "1"),
            PostBootPropertyRule("ro.build.version.sdk", "37"),
            PostBootPropertyRule("ro.build.version.security_patch", "2026-09-01"),
            PostBootPropertyRule("ro.boot.verifiedbootstate", "orange"),
        ),
        True,
        300,
    )
    actions = (
        DeviceRecoveryActionRule(
            1,
            DeviceRecoveryOperation.RESTORE_STOCK_PACKAGE,
            "simulation.stock.adapter.restore",
            DeviceMode.BOOTLOADER,
            DeviceMode.BOOTLOADER,
            "none",
            1800,
            True,
        ),
        DeviceRecoveryActionRule(
            2,
            DeviceRecoveryOperation.REBOOT_SYSTEM,
            "simulation.stock.adapter.reboot",
            DeviceMode.BOOTLOADER,
            DeviceMode.ANDROID,
            "none",
            300,
            False,
        ),
        DeviceRecoveryActionRule(
            3,
            DeviceRecoveryOperation.VERIFY_POST_BOOT,
            "simulation.stock.adapter.verify",
            DeviceMode.ANDROID,
            DeviceMode.ANDROID,
            "none",
            300,
            False,
        ),
    )
    recovery = DeviceRecoveryContract(
        DeviceRecoveryStrategy.STOCK_PACKAGE_RESTORE,
        "simulation.stock.adapter",
        source_sha256,
        DeviceMode.BOOTLOADER,
        actions,
        True,
        True,
        False,
        True,
        False,
        False,
    )
    transition = DeviceTransitionRecoveryContract(
        "simulation-transition-recovery",
        1,
        BUILD_ID,
        attestation,
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
        recovery,
        True,
        "none",
        False,
    )
    policy = AvbExecutionPolicy(
        AvbPolicyMode.UNLOCKED_UNSIGNED_CHILD,
        AvbPolicyAuthority.FLASH_VALIDATED,
        BUILD_ID,
        "preserve_exact_source",
        "vbmeta_system",
        "NONE",
        0,
        0,
        0,
        True,
        True,
        True,
        "a",
        "b",
        attestation,
    )
    write = DeviceWriteContract(
        "simulation-exact-writes",
        3,
        BUILD_ID,
        attestation,
        True,
        True,
        True,
        True,
        (write_rule,),
        False,
        verification,
        transition,
    )
    build = DeviceBuildContract(
        "simulation-exact-build",
        2,
        source,
        4096,
        512,
        2,
        False,
        (),
        (),
        (),
        "d" * 64,
        "e" * 64,
        ("super.img",),
        avb_execution_policy=policy,
        partition_write_contract=write,
    )
    return DevicePack(
        "simulation.guided.recovery",
        "1.0.0-inert",
        "ROMVERSE inert Guided Recovery Pack",
        100,
        ("radforge simulation",),
        ("virtual recovery phone",),
        (PRODUCT,),
        (
            PackCapability(
                "firmware.operations",
                "Inert Recovery simulation",
                CapabilityStatus.SUPPORTED,
                "simulation_only",
                "Exercises evidence boundaries without a physical-device transport.",
            ),
        ),
        ("Simulation only; never enroll as a production Device Pack.",),
        "f" * 64,
        build,
    )


def _test_adapter(root: Path, prepared, phone: InertPhone):
    package_root = root / "test-only-adapter"
    package_root.mkdir()
    artifact_name = (
        "ROMVERSE-Recovery-Adapter.exe" if os.name == "nt" else "ROMVERSE-Recovery-Adapter"
    )
    artifact = package_root / artifact_name
    artifact.write_bytes(b"ROMVERSE INERT ADAPTER PLACEHOLDER - NEVER EXECUTED\n")
    artifact.chmod(0o700)
    private_key = Ed25519PrivateKey.generate()
    trust = GuardianRecoveryAdapterReleaseTrustRoot.from_public_key(
        key_id="test.simulation.recovery-adapter-release",
        public_key=private_key.public_key(),
        scope=RecoveryAdapterTrustScope.TEST_ONLY,
    )
    platform = "windows-x86_64" if os.name == "nt" else "linux-x86_64"
    manifest = build_guardian_recovery_adapter_manifest(
        package_id="romverse.recovery-adapter.simulation",
        package_version="0.1.0-simulation.1",
        created_at=SIMULATED_AT.isoformat().replace("+00:00", "Z"),
        platform=platform,
        artifact_path=artifact,
        adapter_id=prepared.recovery_adapter_id,
        adapter_version=1,
        supported_action_ids=tuple(step.adapter_action_id for step in prepared.steps),
    )
    envelope = create_signed_guardian_recovery_adapter_package(
        manifest,
        private_key,
        trust.key_id,
    )
    package = verify_guardian_recovery_adapter_package(
        envelope=envelope,
        trust_root=trust,
        package_directory=package_root,
        expected_platform=platform,
    )
    process = InertRecoveryProcess(phone)
    return GuardianTrustedRecoveryProcessAdapter(package, process), process


def _android_device(scanned: AndroidDevice, uptime_seconds: int) -> AndroidDevice:
    return replace(
        scanned,
        state=DeviceState.DEVICE,
        transport="inert-usb",
        boot_completed=True,
        uptime_seconds=uptime_seconds,
        slot_suffix="_a",
        build_id=BUILD_ID,
        build_fingerprint=BUILD_FINGERPRINT,
        android_version="17",
        api_level="37",
        security_patch="2026-09-01",
        verified_boot="orange",
    )


def run(output: Path) -> dict[str, object]:
    root = output.absolute()
    root.mkdir(parents=False, exist_ok=False)
    workspace = root / "workspace"
    source = root / "ROMVERSE-INERT-STOCK-PACKAGE.zip"
    source.write_bytes(b"ROMVERSE INERT STOCK PACKAGE - NO FIRMWARE PAYLOAD\n")
    backup = root / "ROMVERSE-INERT-EXTERNAL-BACKUP.bin"
    backup.write_bytes(b"ROMVERSE INERT BACKUP EVIDENCE - NO USER DATA\n")
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    pack = _simulated_pack(source_sha256)
    registry = DevicePackRegistry((pack,))
    write = pack.build_contract.partition_write_contract if pack.build_contract else None
    if write is None or not registry.transition_recovery_contract_is_valid(
        write, pack.build_contract.source
    ):
        raise AssertionError("Inert Device Pack failed the production contract parser")

    store = RomProjectStore(workspace)
    project = store.create("SIMULATED Guided Recovery", pack.pack_id)
    project = store.import_original(project.project_id, source)
    evidence = RecoveryEvidenceService(store)
    evidence.register(project.project_id, "external_backup", backup)
    evidence.register(project.project_id, "stock_recovery", source)

    phone_state = InertPhone()
    adb = InertAdb(phone_state)
    fastboot = InertFastboot(phone_state)
    scanned_devices = DeviceEngine(None, fastboot).scan()
    if len(scanned_devices) != 1:
        raise AssertionError("The inert scan did not identify exactly one device")
    scanned = replace(
        scanned_devices[0],
        manufacturer="RadForge Simulation",
        brand="RadForge Simulation",
        model="Virtual Recovery Phone",
        marketing_name="ROMVERSE inert phone",
        ab_update=True,
        slot_suffix="_a",
    )
    resolution = registry.resolve(scanned)
    if not resolution.matched or resolution.pack != pack:
        raise AssertionError("The inert scan did not match its exact Device Pack")

    autopilot = RecoveryAutopilotService(workspace, registry)
    incident = autopilot.start(
        RecoveryAutopilotContext(
            RecoveryTrigger.BOOTLOOP,
            device=scanned,
            project_id=project.project_id,
            recovery_evidence=evidence.assess(project.project_id, scanned),
        )
    )
    route = next(
        item for item in incident.routes if item.kind is RecoveryRouteKind.EXACT_STOCK_RESTORE
    )
    preparations = GuardianRecoveryPreparationService(store, registry, autopilot)
    prepared = preparations.prepare(incident.incident_id, route.route_id, [scanned])

    live_targets = GuardianRecoveryLiveTargetReceiptService(
        preparations,
        adb,
        fastboot,
        clock=lambda: SIMULATED_AT,
    )
    target = live_targets.observe(prepared, scanned)
    consents = GuardianRecoveryConsentReceiptService(
        live_targets,
        clock=lambda: SIMULATED_AT + timedelta(seconds=30),
    )
    consent = consents.issue(prepared, target, scanned, confirmed=True)
    execution_time = SIMULATED_AT + timedelta(seconds=60)
    live_targets.clock = lambda: execution_time
    executions = GuardianRecoveryExecutionService(
        consents,
        clock=lambda: execution_time,
    )
    grant = executions.admit(prepared, target, consent, scanned)
    targets = GuardianRecoveryStepTargetService(executions, clock=lambda: execution_time)
    elapsed = [0.0]
    runner = GuardianRecoveryAdapterRunner(
        executions,
        targets,
        monotonic=lambda: elapsed[0],
        sleeper=lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds),
        allow_test_adapter_trust=True,
    )
    adapter, inert_process = _test_adapter(root, prepared, phone_state)
    step_runs = [runner.execute_next(grant, prepared, adapter) for _step in prepared.steps]
    if any(run.durable_outcome is not RecoveryStepOutcome.SUCCEEDED for run in step_runs):
        raise AssertionError("The inert adapter sequence did not record exact durable success")

    results = GuardianRecoveryExecutionResultService(executions, clock=lambda: execution_time)
    aggregate = results.record(prepared)
    observed_at = [datetime.now(UTC) - timedelta(seconds=310)]
    session = RecoveryOperationSession(
        prepared,
        results,
        autopilot,
        BootObservationService(store, registry),
        clock=lambda: observed_at[0],
    )
    reassessed = session.snapshot()
    first = _android_device(scanned, 600)
    session.accept_scan((first,))
    for seconds in (60, 120, 180, 240):
        observed_at[0] = observed_at[0] + timedelta(seconds=60)
        session.accept_scan((_android_device(scanned, 600 + seconds),))
    observed_at[0] = datetime.now(UTC)
    verified = session.accept_scan((_android_device(scanned, 910),))
    persisted = RecoveryAutopilotService(workspace, registry).load(incident.incident_id)
    reopened_project = RomProjectStore(workspace).get(project.project_id)

    if (
        reassessed.phase is not RecoveryOperationPhase.WAITING_FOR_ANDROID
        or reassessed.incident_state is not RecoveryIncidentState.VERIFYING
        or verified.phase is not RecoveryOperationPhase.VERIFIED
        or not verified.recovered
        or persisted.state is not RecoveryIncidentState.RECOVERED
        or reopened_project.original is None
        or reopened_project.original.sha256 != source_sha256
    ):
        raise AssertionError("The inert Guided Recovery journey did not persist to verification")

    report: dict[str, object] = {
        "simulation_only": True,
        "physical_phone_connected": False,
        "physical_phone_changed": False,
        "external_process_started": False,
        "production_adapter_used": False,
        "production_execution_enabled": False,
        "test_trust_material_persisted": False,
        "automatic_retry_allowed": False,
        "bootloader_relock_allowed": False,
        "project_reopened": True,
        "journey": {
            "scan": {
                "status": "completed",
                "device_count": len(scanned_devices),
                "mode": scanned.state.value,
            },
            "match": {
                "status": "completed",
                "device_pack_id": pack.pack_id,
                "reason": resolution.reason,
            },
            "prepare": {
                "status": prepared.preparation_status,
                "step_count": prepared.step_count,
                "execution_authority": prepared.execution_authority,
            },
            "consent": {
                "status": "recorded",
                "consent_scope_only": consent.receipt.consent_scope_only,
                "execution_authority": consent.receipt.execution_authority,
            },
            "result": {
                "status": aggregate.state.value,
                "completed_step_count": aggregate.completed_step_count,
                "journal_entry_count": aggregate.journal_entry_count,
                "recovery_verified": aggregate.recovery_verified,
            },
            "reassessment": {
                "status": reassessed.phase.value,
                "incident_state": reassessed.incident_state.value,
                "recovered": reassessed.recovered,
            },
            "verification": {
                "status": verified.phase.value,
                "incident_state": persisted.state.value,
                "recovered": verified.recovered,
                "verified_reboot": persisted.verified_reboot,
            },
        },
        "adapter_action_ids": phone_state.adapter_actions,
        "adapter_invocation_count": len(inert_process.invocations),
        "workspace": str(workspace),
        "source_sha256": source_sha256,
        "incident_id": incident.incident_id,
        "result_digest": aggregate.result_digest,
        "final_incident_digest": persisted.record_digest,
    }
    serialized_workspace = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in workspace.rglob("*")
        if path.is_file() and path.stat().st_size <= 2 * 1024 * 1024
    )
    if SERIAL in serialized_workspace:
        raise AssertionError("Raw simulated device serial leaked into durable evidence")
    (root / "guided-recovery-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    options = parser.parse_args(argv)
    print(json.dumps(run(options.output), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
