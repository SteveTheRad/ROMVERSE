from __future__ import annotations

import hashlib
import hmac
import json
import math
from dataclasses import asdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from romverse.core.privacy import WorkspacePrivacy
from romverse.core.recovery_contracts import (
    BootFailureKind,
    BootObservationReceipt,
    BootObservationStatus,
    BootSample,
    GuardianRecoveryPreparation,
    RecoveryBootEvidenceStore,
    RecoveryContractError,
    RecoveryExecutionResultEvidenceStore,
    RecoveryExecutionResultState,
    RecoveryProjectEvidence,
    validate_recovery_execution_result_evidence,
)
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.registry import DevicePackRegistry
from romverse.guardian.execution_result_receipt import (
    ExecutionTerminalState,
    GatewayResultOutcome,
    GuardianExecutionResultReceipt,
    VerifiedGuardianExecutionResult,
    canonical_execution_result_bytes,
    execution_result_digest,
)
from romverse.infrastructure.local_store import LocalStoreError, atomic_write_json, read_json_object
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore

if TYPE_CHECKING:
    from romverse.knowledge.models import KnowledgeFailure


class BootObservationService(RecoveryBootEvidenceStore):
    """Accumulate boot evidence and link it only to a verified Guardian result."""

    NAME = "boot-observation.romverse"
    FORMAT = "romverse.boot-observation"
    SCHEMA_VERSION = 3
    MAX_BYTES = 256 * 1024
    MIN_SAMPLE_INTERVAL_SECONDS = 60
    STABILITY_WINDOW_SECONDS = 300
    MAX_SAMPLES = 30
    SAMPLE_FIELDS = {
        "observed_at",
        "device_pseudonym",
        "state",
        "boot_completed",
        "uptime_seconds",
        "slot_suffix",
        "build_id",
        "build_fingerprint",
        "battery_percent",
        "probe_errors",
    }
    RECEIPT_FIELDS_V1 = {
        "format",
        "schema_version",
        "project_id",
        "pack_id",
        "contract_id",
        "source_original_sha256",
        "samples",
        "status",
        "stable",
        "reboot_detected",
        "flash_linked",
        "verified_first_boot",
        "diagnosis",
        "phone_changed",
        "receipt_digest",
    }
    RECEIPT_FIELDS_V2 = RECEIPT_FIELDS_V1 | {"failure_kind", "knowledge_queries"}
    RECEIPT_FIELDS_V3 = RECEIPT_FIELDS_V2 | {"guardian_execution_receipt_digest"}

    def __init__(self, store: RomProjectStore, registry: DevicePackRegistry) -> None:
        self.store = store
        self.registry = registry
        self.privacy = WorkspacePrivacy(store.workspace)
        self._verified_flash_digests: set[str] = set()

    @property
    def workspace(self):
        return self.store.workspace.resolve()

    def project_evidence(self, project_id: str) -> RecoveryProjectEvidence:
        """Expose only the project identity needed for independent Recovery verification."""

        project = self.store.get(project_id)
        return RecoveryProjectEvidence(
            project_id=project.project_id,
            device_pack_id=project.device_pack_id,
            source_original_sha256=(
                project.original.sha256 if project.original is not None else ""
            ),
        )

    def observe(
        self,
        project_id: str,
        device: AndroidDevice,
        observed_at: datetime | None = None,
        *,
        verified_flash: VerifiedGuardianExecutionResult | None = None,
    ) -> BootObservationReceipt:
        now = (observed_at or datetime.now(UTC)).astimezone(UTC)
        verified_flash_digest = ""
        if verified_flash is not None:
            verified_flash_digest = self.verified_flash_digest(
                project_id,
                device,
                verified_flash,
                observed_at=now,
            )
        return self._observe(project_id, device, now, verified_flash_digest)

    def observe_recovery(
        self,
        project_id: str,
        device: AndroidDevice,
        preparation: GuardianRecoveryPreparation,
        execution_results: RecoveryExecutionResultEvidenceStore,
        observed_at: datetime | None = None,
    ) -> BootObservationReceipt:
        """Collect read-only boot evidence linked to one exact completed Recovery result."""

        now = observed_at or datetime.now(UTC)
        if now.tzinfo is None or now.utcoffset() is None:
            raise ProjectError("Recovery boot observation time requires a timezone")
        now = now.astimezone(UTC)
        digest = self.verified_recovery_digest(
            project_id,
            device,
            preparation,
            execution_results,
            observed_at=now,
        )
        return self._observe(
            project_id,
            device,
            now,
            digest,
            replace_verified_session=True,
        )

    def _observe(
        self,
        project_id: str,
        device: AndroidDevice,
        now: datetime,
        verified_flash_digest: str,
        *,
        replace_verified_session: bool = False,
    ) -> BootObservationReceipt:
        project = self.store.get(project_id)
        pack = next(
            (item for item in self.registry.packs if item.pack_id == project.device_pack_id), None
        )
        if project.original is None or pack is None or pack.build_contract is None:
            raise ProjectError("Boot observation requires an exact source-bound Device Pack")
        resolution = self.registry.resolve(device)
        if resolution.pack is None or resolution.pack.pack_id != pack.pack_id:
            raise ProjectError("Connected device does not match the project's exact Device Pack")
        pseudonym = self.privacy.pseudonym(device.serial)
        previous = self.load(project_id)
        evidence_path = self.store.projects_root / project_id / self.NAME
        if previous is None and evidence_path.exists() and replace_verified_session:
            previous = self._load_replaceable_history(project_id)
        if previous is None and evidence_path.exists():
            raise ProjectError(
                "Existing boot evidence could not be verified and will not be overwritten"
            )
        if (
            verified_flash_digest
            and previous is not None
            and (
                not previous.flash_linked
                or previous.guardian_execution_receipt_digest != verified_flash_digest
            )
        ):
            # A genuine new flash begins a new first-boot observation session. Never
            # mix a pre-flash baseline or an earlier installation into this timeline.
            previous = None
        if previous is not None and previous.samples:
            if previous.samples[0].device_pseudonym != pseudonym:
                raise ProjectError("Boot observation is already bound to another device")
            latest = previous.samples[-1]
            elapsed = (now - datetime.fromisoformat(latest.observed_at)).total_seconds()
            if elapsed < self.MIN_SAMPLE_INTERVAL_SECONDS:
                return previous
        sample = BootSample(
            now.isoformat(),
            pseudonym,
            device.state.value,
            device.boot_completed,
            device.uptime_seconds,
            device.slot_suffix,
            device.build_id[:160],
            device.build_fingerprint[:500],
            device.battery_percent,
            tuple(error[:240] for error in device.errors[:12]),
        )
        samples = ((*previous.samples, sample) if previous is not None else (sample,))[
            -self.MAX_SAMPLES :
        ]
        status, stable, rebooted, diagnosis, failure_kind = self._classify(samples)
        knowledge_queries = self._knowledge_queries(samples, failure_kind)
        flash_receipt_digest = verified_flash_digest or (
            previous.guardian_execution_receipt_digest
            if previous is not None and previous.flash_linked
            else ""
        )
        flash_linked = bool(flash_receipt_digest)
        verified_first_boot = bool(stable and flash_linked)
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "project_id": project_id,
            "pack_id": pack.pack_id,
            "contract_id": pack.build_contract.contract_id,
            "source_original_sha256": project.original.sha256,
            "samples": [asdict(item) for item in samples],
            "status": status.value,
            "stable": stable,
            "reboot_detected": rebooted,
            "flash_linked": flash_linked,
            "guardian_execution_receipt_digest": flash_receipt_digest,
            "verified_first_boot": verified_first_boot,
            "diagnosis": diagnosis,
            "phone_changed": False,
            "failure_kind": failure_kind.value,
            "knowledge_queries": list(knowledge_queries),
        }
        digest = _digest(payload)
        receipt = BootObservationReceipt(
            self.SCHEMA_VERSION,
            project_id,
            pack.pack_id,
            pack.build_contract.contract_id,
            project.original.sha256,
            samples,
            status,
            stable,
            rebooted,
            flash_linked,
            flash_receipt_digest,
            verified_first_boot,
            diagnosis,
            False,
            failure_kind,
            knowledge_queries,
            digest,
        )
        atomic_write_json(
            self.store.projects_root / project_id / self.NAME,
            {"format": self.FORMAT, **asdict(receipt)},
            boundary=self.store.projects_root / project_id,
            maximum_bytes=self.MAX_BYTES,
        )
        return receipt

    def load_recovery(
        self,
        project_id: str,
        device: AndroidDevice,
        preparation: GuardianRecoveryPreparation,
        execution_results: RecoveryExecutionResultEvidenceStore,
    ) -> BootObservationReceipt | None:
        """Reload a persisted Recovery-linked boot receipt after exact revalidation."""

        try:
            self.verified_recovery_digest(
                project_id,
                device,
                preparation,
                execution_results,
            )
        except ProjectError:
            return None
        return self.load(project_id)

    def _load_replaceable_history(self, project_id: str) -> BootObservationReceipt | None:
        """Validate older linked evidence only so a new exact Recovery session may replace it."""

        path = self.store.projects_root / project_id / self.NAME
        try:
            data = read_json_object(
                path,
                boundary=self.store.projects_root / project_id,
                maximum_bytes=self.MAX_BYTES,
            )
        except (LocalStoreError, OSError, ValueError, TypeError, json.JSONDecodeError):
            return None
        digest = data.get("guardian_execution_receipt_digest")
        if (
            data.get("format") != self.FORMAT
            or data.get("schema_version") != self.SCHEMA_VERSION
            or data.get("flash_linked") is not True
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
        ):
            return None
        already_verified = digest in self._verified_flash_digests
        self._verified_flash_digests.add(digest)
        try:
            return self.load(project_id)
        finally:
            if not already_verified:
                self._verified_flash_digests.discard(digest)

    def load(
        self,
        project_id: str,
        *,
        verified_flash: VerifiedGuardianExecutionResult | None = None,
        device: AndroidDevice | None = None,
    ) -> BootObservationReceipt | None:
        if verified_flash is not None:
            if device is None:
                return None
            try:
                self.verified_flash_digest(project_id, device, verified_flash)
            except ProjectError:
                return None
        path = self.store.projects_root / project_id / self.NAME
        try:
            data = read_json_object(
                path,
                boundary=self.store.projects_root / project_id,
                maximum_bytes=self.MAX_BYTES,
            )
            schema = data.get("schema_version")
            if (
                data.get("format") != self.FORMAT
                or type(schema) is not int
                or schema not in {1, 2, self.SCHEMA_VERSION}
                or set(data) != self._receipt_fields(schema)
            ):
                return None
            raw_samples = data.get("samples")
            if not isinstance(raw_samples, list) or not 1 <= len(raw_samples) <= self.MAX_SAMPLES:
                return None
            samples = tuple(self._parse_sample(item) for item in raw_samples)
            status = BootObservationStatus(data["status"])
            failure_kind = (
                BootFailureKind(data["failure_kind"])
                if schema == self.SCHEMA_VERSION
                else self._classify(samples)[4]
            )
            if schema == self.SCHEMA_VERSION:
                raw_queries = data["knowledge_queries"]
                if (
                    not isinstance(raw_queries, list)
                    or len(raw_queries) > 6
                    or any(not self._text(item, 500) for item in raw_queries)
                ):
                    return None
                queries = tuple(raw_queries)
            else:
                queries = self._knowledge_queries(samples, failure_kind)
            receipt = BootObservationReceipt(
                self.SCHEMA_VERSION,
                data["project_id"],
                data["pack_id"],
                data["contract_id"],
                data["source_original_sha256"],
                samples,
                status,
                data["stable"],
                data["reboot_detected"],
                data["flash_linked"],
                data["guardian_execution_receipt_digest"] if schema == self.SCHEMA_VERSION else "",
                data["verified_first_boot"],
                data["diagnosis"],
                data["phone_changed"],
                failure_kind,
                queries,
                data["receipt_digest"],
            )
        except (
            LocalStoreError,
            OSError,
            ValueError,
            TypeError,
            KeyError,
            json.JSONDecodeError,
        ):
            return None
        if not self._valid_receipt(receipt, project_id, source_schema=schema):
            return None
        return receipt

    @classmethod
    def needs_knowledge_lookup(cls, receipt: BootObservationReceipt | None) -> bool:
        """Return whether current boot evidence should trigger an offline Archives scan."""

        return bool(
            receipt is not None
            and receipt.status is BootObservationStatus.ATTENTION
            and receipt.failure_kind is not BootFailureKind.NONE
            and receipt.knowledge_queries
        )

    @classmethod
    def knowledge_failure(
        cls,
        receipt: BootObservationReceipt | None,
    ) -> KnowledgeFailure | None:
        """Translate verified boot evidence into a bounded, non-executing archive query."""

        if not cls.needs_knowledge_lookup(receipt) or receipt is None:
            return None
        from romverse.knowledge.models import KnowledgeFailure

        latest = receipt.samples[-1]
        probe_detail = tuple(error for error in latest.probe_errors if cls._text(error, 500))
        return KnowledgeFailure(
            phase="boot",
            message="\n".join((receipt.diagnosis, *receipt.knowledge_queries, *probe_detail)),
            finding_ids=("boot.incomplete", f"boot.{receipt.failure_kind.value}"),
            operation="read-only boot observation",
            verified_inputs=(
                f"pack:{receipt.pack_id}",
                f"source:{receipt.source_original_sha256}",
            ),
        )

    @classmethod
    def next_sample_wait_seconds(
        cls,
        receipt: BootObservationReceipt | None,
        observed_at: datetime | None = None,
    ) -> int:
        if receipt is None or not receipt.samples:
            return 0
        now = (observed_at or datetime.now(UTC)).astimezone(UTC)
        elapsed = (now - datetime.fromisoformat(receipt.samples[-1].observed_at)).total_seconds()
        return max(0, math.ceil(cls.MIN_SAMPLE_INTERVAL_SECONDS - elapsed))

    @staticmethod
    def next_step(receipt: BootObservationReceipt | None) -> str:
        if receipt is None:
            return "Record a read-only baseline only if the exact target phone is connected. This is not proof that ROMVERSE flashed it."
        if receipt.status is BootObservationStatus.SETTLING:
            return "Leave the phone connected and unlocked while Android finishes starting, then record another sample."
        if receipt.status is BootObservationStatus.WAITING:
            return "Keep the phone connected. Record a follow-up after the five-minute stability window."
        if receipt.status is BootObservationStatus.STABLE:
            if receipt.verified_first_boot:
                return "Verified first boot is stable and linked to the successful Guardian execution receipt. Continue with subsystem health checks."
            return "Android looks stable on the same build and slot. A matching signed Guardian write receipt is still required before this can become verified first-boot evidence."
        return "Stop and review the diagnosis before any further device-changing work. ROMVERSE will not call this a successful boot."

    @classmethod
    def _receipt_fields(cls, schema: int) -> set[str]:
        if schema == cls.SCHEMA_VERSION:
            return cls.RECEIPT_FIELDS_V3
        if schema == 2:
            return cls.RECEIPT_FIELDS_V2
        return cls.RECEIPT_FIELDS_V1

    def verified_flash_digest(
        self,
        project_id: str,
        device: AndroidDevice,
        verified: VerifiedGuardianExecutionResult,
        *,
        observed_at: datetime | None = None,
    ) -> str:
        """Accept only an already cryptographically verified successful exact-device result."""

        project = self.store.get(project_id)
        pack = next(
            (item for item in self.registry.packs if item.pack_id == project.device_pack_id), None
        )
        receipt = (
            verified.receipt if isinstance(verified, VerifiedGuardianExecutionResult) else None
        )
        now = (observed_at or datetime.now(UTC)).astimezone(UTC)
        try:
            completed_at = datetime.fromisoformat(receipt.completed_at.replace("Z", "+00:00"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ProjectError("Guardian execution result has an invalid completion time") from exc
        if completed_at.tzinfo is None:
            raise ProjectError("Guardian execution result completion time requires a zone")
        unsigned = asdict(receipt) if isinstance(receipt, GuardianExecutionResultReceipt) else {}
        receipt_digest = unsigned.pop("receipt_digest", "")
        signed_receipt_sha256 = (
            hashlib.sha256(canonical_execution_result_bytes(asdict(receipt))).hexdigest()
            if isinstance(receipt, GuardianExecutionResultReceipt)
            else ""
        )
        if (
            project.original is None
            or pack is None
            or pack.build_contract is None
            or not isinstance(receipt, GuardianExecutionResultReceipt)
            or receipt.project_id != project_id
            or receipt.device_pack_id != pack.pack_id
            or receipt.device_key != self.privacy.pseudonym(device.serial)
            or receipt.terminal_state is not ExecutionTerminalState.SUCCEEDED
            or receipt.forward_result_count != len(receipt.forward_results)
            or not receipt.forward_results
            or any(
                result.outcome is not GatewayResultOutcome.PASSED
                for result in receipt.forward_results
            )
            or receipt.forward_results_digest
            != execution_result_digest(
                {"forward_results": [asdict(result) for result in receipt.forward_results]}
            )
            or not receipt.phone_change_attempted
            or not receipt.phone_change_verified
            or receipt.phone_state_uncertain
            or not receipt.postconditions_verified
            or completed_at.astimezone(UTC) > now
            or not isinstance(verified.signed_receipt_sha256, str)
            or len(verified.signed_receipt_sha256) != 64
            or any(char not in "0123456789abcdef" for char in verified.signed_receipt_sha256)
            or verified.signer_key_id != receipt.runtime_signer_key_id
            or receipt_digest != execution_result_digest(unsigned)
            or verified.signed_receipt_sha256 != signed_receipt_sha256
        ):
            raise ProjectError(
                "Boot observation requires a successful verified Guardian result for this exact project and device"
            )
        self._verified_flash_digests.add(verified.signed_receipt_sha256)
        return verified.signed_receipt_sha256

    def verified_recovery_digest(
        self,
        project_id: str,
        device: AndroidDevice,
        preparation: GuardianRecoveryPreparation,
        execution_results: RecoveryExecutionResultEvidenceStore,
        *,
        observed_at: datetime | None = None,
    ) -> str:
        """Validate a completed exact Recovery result for read-only boot linkage."""

        if (
            not isinstance(preparation, GuardianRecoveryPreparation)
            or not isinstance(execution_results, RecoveryExecutionResultEvidenceStore)
            or execution_results.workspace.resolve() != self.workspace
        ):
            raise ProjectError("Boot observation requires an exact local Recovery result")
        result = execution_results.load(preparation)
        if result is None:
            raise ProjectError("Boot observation requires an exact durable Recovery result")
        try:
            validate_recovery_execution_result_evidence(preparation, result)
        except RecoveryContractError as exc:
            raise ProjectError("Boot observation requires sealed Recovery result evidence") from exc
        now = (observed_at or datetime.now(UTC)).astimezone(UTC)
        try:
            recorded_at = datetime.fromisoformat(result.recorded_at)
        except ValueError as exc:
            raise ProjectError("Recovery result has an invalid completion time") from exc
        project = self.store.get(project_id)
        pack = next(
            (
                item
                for item in self.registry.packs
                if item.pack_id == result.device_pack_id
                and hmac.compare_digest(item.sha256, result.device_pack_sha256)
            ),
            None,
        )
        resolution = self.registry.resolve(device)
        if (
            result.state
            is not RecoveryExecutionResultState.SEQUENCE_COMPLETED_AWAITING_REASSESSMENT
            or result.sequence_actions_completed is not True
            or result.completed_step_count != result.step_count
            or result.known_failure_recorded is not False
            or result.unknown_outcome_recorded is not False
            or result.recovery_verified is not False
            or result.device_repaired is not False
            or result.execution_authority != "none"
            or result.automatic_retry_allowed is not False
            or result.bootloader_relock_allowed is not False
            or project.project_id != result.project_id
            or project_id != result.project_id
            or project.original is None
            or not hmac.compare_digest(project.original.sha256, result.source_original_sha256)
            or project.device_pack_id != result.device_pack_id
            or pack is None
            or pack.build_contract is None
            or resolution.pack is None
            or resolution.pack.pack_id != pack.pack_id
            or not hmac.compare_digest(resolution.pack.sha256, pack.sha256)
            or not device.serial
            or not hmac.compare_digest(
                self.privacy.pseudonym(device.serial),
                result.device_key,
            )
            or recorded_at > now
        ):
            raise ProjectError(
                "Boot observation requires a completed Recovery result for this exact project and device"
            )
        self._verified_flash_digests.add(result.result_digest)
        return result.result_digest

    @classmethod
    def _parse_sample(cls, value: object) -> BootSample:
        if not isinstance(value, dict) or set(value) != cls.SAMPLE_FIELDS:
            raise ValueError("Boot sample has an invalid shape")
        observed_at = value["observed_at"]
        pseudonym = value["device_pseudonym"]
        state = value["state"]
        boot_completed = value["boot_completed"]
        uptime = value["uptime_seconds"]
        slot = value["slot_suffix"]
        build_id = value["build_id"]
        fingerprint = value["build_fingerprint"]
        battery = value["battery_percent"]
        errors = value["probe_errors"]
        if (
            not cls._timestamp(observed_at)
            or not isinstance(pseudonym, str)
            or len(pseudonym) != 20
            or any(char not in "0123456789abcdef" for char in pseudonym)
            or not isinstance(state, str)
            or state not in {item.value for item in DeviceState}
            or (boot_completed is not None and type(boot_completed) is not bool)
            or (uptime is not None and (type(uptime) is not int or not 0 <= uptime <= 10**9))
            or not cls._text(slot, 32)
            or not cls._text(build_id, 160)
            or not cls._text(fingerprint, 500)
            or (battery is not None and (type(battery) is not int or not 0 <= battery <= 100))
            or not isinstance(errors, list)
            or len(errors) > 12
            or any(not cls._text(item, 240) for item in errors)
        ):
            raise ValueError("Boot sample contains invalid evidence")
        return BootSample(
            observed_at,
            pseudonym,
            state,
            boot_completed,
            uptime,
            slot,
            build_id,
            fingerprint,
            battery,
            tuple(errors),
        )

    def _valid_receipt(
        self,
        receipt: BootObservationReceipt,
        project_id: str,
        *,
        source_schema: int,
    ) -> bool:
        try:
            project = self.store.get(project_id)
        except ProjectError:
            return False
        pack = next(
            (item for item in self.registry.packs if item.pack_id == project.device_pack_id), None
        )
        classified = self._classify(receipt.samples)
        status, stable, rebooted, diagnosis, failure_kind = classified
        queries = self._knowledge_queries(receipt.samples, failure_kind)
        if (
            receipt.schema_version != self.SCHEMA_VERSION
            or receipt.project_id != project_id
            or receipt.phone_changed
            or type(receipt.flash_linked) is not bool
            or type(receipt.verified_first_boot) is not bool
            or receipt.flash_linked != bool(receipt.guardian_execution_receipt_digest)
            or (
                receipt.flash_linked
                and receipt.guardian_execution_receipt_digest not in self._verified_flash_digests
            )
            or (
                receipt.guardian_execution_receipt_digest
                and (
                    len(receipt.guardian_execution_receipt_digest) != 64
                    or any(
                        char not in "0123456789abcdef"
                        for char in receipt.guardian_execution_receipt_digest
                    )
                )
            )
            or receipt.verified_first_boot is not bool(receipt.flash_linked and receipt.stable)
            or project.original is None
            or receipt.source_original_sha256 != project.original.sha256
            or pack is None
            or pack.build_contract is None
            or receipt.pack_id != pack.pack_id
            or receipt.contract_id != pack.build_contract.contract_id
            or receipt.status is not status
            or receipt.stable is not stable
            or receipt.reboot_detected is not rebooted
            or receipt.diagnosis != diagnosis
            or receipt.failure_kind is not failure_kind
            or receipt.knowledge_queries != queries
            or not self._valid_sample_sequence(receipt.samples)
        ):
            return False
        payload = asdict(receipt)
        digest = payload.pop("receipt_digest", "")
        payload["schema_version"] = source_schema
        if source_schema < 3:
            payload.pop("guardian_execution_receipt_digest", None)
        if source_schema == 1:
            payload.pop("failure_kind", None)
            payload.pop("knowledge_queries", None)
        return isinstance(digest, str) and len(digest) == 64 and _digest(payload) == digest

    @classmethod
    def _valid_sample_sequence(cls, samples: tuple[BootSample, ...]) -> bool:
        if not 1 <= len(samples) <= cls.MAX_SAMPLES:
            return False
        times = tuple(datetime.fromisoformat(item.observed_at) for item in samples)
        return bool(
            all(item.tzinfo is not None for item in times)
            and all(earlier < later for earlier, later in zip(times, times[1:], strict=False))
            and len({item.device_pseudonym for item in samples}) == 1
        )

    @staticmethod
    def _timestamp(value: object) -> bool:
        if not isinstance(value, str) or len(value) > 64:
            return False
        try:
            return datetime.fromisoformat(value).tzinfo is not None
        except ValueError:
            return False

    @staticmethod
    def _text(value: object, maximum: int) -> bool:
        return bool(
            isinstance(value, str)
            and len(value) <= maximum
            and "\0" not in value
            and all(char in "\n\t" or ord(char) >= 32 for char in value)
        )

    @staticmethod
    def _knowledge_queries(
        samples: tuple[BootSample, ...],
        failure_kind: BootFailureKind,
    ) -> tuple[str, ...]:
        if failure_kind is BootFailureKind.NONE:
            return ()
        latest = samples[-1]
        primary = {
            BootFailureKind.DEVICE_MODE: f"Android stuck in {latest.state} mode after update",
            BootFailureKind.IDENTITY_CHANGED: "Android build identity changed during first boot",
            BootFailureKind.REBOOT_LOOP: "Android boot loop uptime reset after firmware update",
            BootFailureKind.BOOT_TIMEOUT: "Android sys.boot_completed timeout after firmware update",
            BootFailureKind.PROBE_INCOMPLETE: "ADB boot property probes incomplete after update",
        }[failure_kind]
        candidates = [primary]
        if latest.build_id:
            candidates.append(f"Android build {latest.build_id} boot recovery")
        if latest.slot_suffix:
            candidates.append(f"Android A/B slot {latest.slot_suffix} boot recovery")
        candidates.append("Android verified boot recovery diagnosis")
        return tuple(dict.fromkeys(candidates))[:6]

    @classmethod
    def _classify(
        cls, samples: tuple[BootSample, ...]
    ) -> tuple[BootObservationStatus, bool, bool, str, BootFailureKind]:
        latest = samples[-1]
        pairs = tuple(zip(samples, samples[1:], strict=False))
        rebooted = any(
            earlier.uptime_seconds is not None
            and later.uptime_seconds is not None
            and later.uptime_seconds + 30 < earlier.uptime_seconds
            for earlier, later in pairs
        )
        fingerprint_changed = any(
            earlier.build_fingerprint
            and later.build_fingerprint
            and earlier.build_fingerprint != later.build_fingerprint
            for earlier, later in pairs
        )
        if latest.state != DeviceState.DEVICE.value:
            return (
                BootObservationStatus.ATTENTION,
                False,
                rebooted,
                f"ADB reports {latest.state}; stable Android userspace is not observable",
                BootFailureKind.DEVICE_MODE,
            )
        if fingerprint_changed:
            return (
                BootObservationStatus.ATTENTION,
                False,
                rebooted,
                "Build fingerprint changed inside one observation session",
                BootFailureKind.IDENTITY_CHANGED,
            )
        if rebooted:
            return (
                BootObservationStatus.ATTENTION,
                False,
                True,
                "Device uptime reset during observation; investigate a reboot or boot loop",
                BootFailureKind.REBOOT_LOOP,
            )
        if latest.probe_errors and latest.boot_completed is None and latest.uptime_seconds is None:
            return (
                BootObservationStatus.ATTENTION,
                False,
                False,
                "Android boot probes are incomplete; boot state cannot be established",
                BootFailureKind.PROBE_INCOMPLETE,
            )
        if latest.boot_completed is not True:
            status = (
                BootObservationStatus.ATTENTION
                if latest.uptime_seconds is not None and latest.uptime_seconds >= 20 * 60
                else BootObservationStatus.SETTLING
            )
            return (
                status,
                False,
                False,
                "Android has not yet reported sys.boot_completed=1",
                BootFailureKind.BOOT_TIMEOUT
                if status is BootObservationStatus.ATTENTION
                else BootFailureKind.NONE,
            )
        if len(samples) >= 2:
            latest_at = datetime.fromisoformat(latest.observed_at)
            for index, earlier in enumerate(samples[:-1]):
                stable_window = samples[index:]
                elapsed = (latest_at - datetime.fromisoformat(earlier.observed_at)).total_seconds()
                uptime_gain = (
                    latest.uptime_seconds - earlier.uptime_seconds
                    if latest.uptime_seconds is not None and earlier.uptime_seconds is not None
                    else -1
                )
                same_identity = bool(
                    len({sample.build_fingerprint for sample in stable_window}) == 1
                    and len({sample.slot_suffix for sample in stable_window}) == 1
                    and len({sample.device_pseudonym for sample in stable_window}) == 1
                )
                if (
                    elapsed >= cls.STABILITY_WINDOW_SECONDS
                    and uptime_gain >= elapsed - 60
                    and same_identity
                    and all(sample.boot_completed is True for sample in stable_window)
                ):
                    return (
                        BootObservationStatus.STABLE,
                        True,
                        False,
                        "Android remained boot-complete on the same build and slot across the stability window",
                        BootFailureKind.NONE,
                    )
        return (
            BootObservationStatus.WAITING,
            False,
            False,
            "Boot completion observed; collect another sample after the stability window",
            BootFailureKind.NONE,
        )


def _digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
