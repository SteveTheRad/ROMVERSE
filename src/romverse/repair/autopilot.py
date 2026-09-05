from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from romverse.core.privacy import WorkspacePrivacy
from romverse.core.recovery_contracts import (
    RECOVERY_BOOT_OBSERVATION_SCHEMA_VERSION,
    BootFailureKind,
    BootObservationReceipt,
    BootObservationStatus,
    GuardianRecoveryPreparation,
    RecoveryAutopilotError,
    RecoveryBootEvidenceStore,
    RecoveryContractError,
    RecoveryExecutionResultEvidenceStore,
    RecoveryExecutionResultState,
    RecoveryIncident,
    RecoveryIncidentEvent,
    RecoveryIncidentEvidenceStore,
    RecoveryIncidentState,
    RecoveryRoute,
    RecoveryRouteKind,
    RecoveryRouteRisk,
    RecoveryTargetMismatchError,
    RecoveryTrigger,
    validate_recovery_boot_evidence,
    validate_recovery_execution_result_evidence,
)
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.models import DevicePack
from romverse.device_packs.registry import DevicePackRegistry
from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    bounded_regular_files,
    ensure_private_directory,
    read_json_object,
    remove_regular_file,
)
from romverse.knowledge.models import KnowledgeLookupReport, MatchConfidence
from romverse.rom.models import ProjectError
from romverse.rom.recovery_evidence import RecoveryEvidenceAssessment


@dataclass(frozen=True, slots=True)
class RecoveryAutopilotContext:
    trigger: RecoveryTrigger
    device: AndroidDevice | None = None
    project_id: str = ""
    message: str = ""
    boot_observation: BootObservationReceipt | None = None
    knowledge_report: KnowledgeLookupReport | None = None
    recovery_evidence: RecoveryEvidenceAssessment | None = None
    before_evidence_digest: str = ""
    host_repair_available: bool = False
    # Recovery-only attribution. This never grants boot, write, retry or route
    # execution authority; it keeps a disconnected incident bound to the phone
    # for which its sealed evidence was recorded.
    expected_device_key: str = ""


class RecoveryAutopilotService(RecoveryIncidentEvidenceStore):
    """Evidence-led recovery triage with a private, tamper-evident incident ledger.

    The service ranks routes and records decisions. It deliberately owns no ADB,
    Fastboot, wipe, slot, or stock-restore executor; an existing typed owner must
    independently revalidate and confirm any action.
    """

    FORMAT = "romverse.recovery-autopilot"
    SCHEMA_VERSION = 1
    SUFFIX = ".romverse-recovery.json"
    MAXIMUM_BYTES = 512 * 1024
    MAX_INCIDENTS = 100
    MAX_SCAN_ENTRIES = 512
    MAX_EVENTS = 128
    ACTION_OUTCOMES = frozenset(
        {"reviewed", "confirmed", "declined", "started", "succeeded", "failed"}
    )
    EXECUTION_COMPLETED_EVENT = "recovery_execution_completed"
    EXECUTION_FAILED_EVENT = "recovery_execution_failed"
    EXECUTION_UNKNOWN_EVENT = "recovery_execution_unknown"
    EXECUTION_VERIFIED_EVENT = "recovery_execution_verified"
    MAX_RECOVERY_BOOT_EVIDENCE_AGE_SECONDS = 120
    EXECUTION_REASSESSMENT_EVENTS = frozenset(
        {
            EXECUTION_COMPLETED_EVENT,
            EXECUTION_FAILED_EVENT,
            EXECUTION_UNKNOWN_EVENT,
        }
    )

    def __init__(self, workspace: Path, registry: DevicePackRegistry) -> None:
        self.workspace = workspace
        self.root = workspace / "diagnostics" / "recovery-incidents"
        self.registry = registry
        self.privacy = WorkspacePrivacy(workspace)

    def open(self, context: RecoveryAutopilotContext) -> RecoveryIncident:
        """Start a new incident or refresh the matching unfinished incident."""

        current_key = self._context_device_key(context)
        existing = next(
            (
                incident
                for incident in self.list_recent()
                if not incident.repaired
                and incident.project_id == self._project_id(context.project_id)
                and (
                    hmac.compare_digest(incident.device_key, current_key)
                    if current_key
                    else not incident.device_key
                )
            ),
            None,
        )
        if existing is not None:
            return self.refresh(existing.incident_id, context)
        return self.start(context)

    def start(self, context: RecoveryAutopilotContext) -> RecoveryIncident:
        now = datetime.now(UTC).isoformat()
        incident = self._assess(context, None, now)
        self._save(incident)
        self._prune()
        return incident

    def refresh(
        self,
        incident_id: str,
        context: RecoveryAutopilotContext,
    ) -> RecoveryIncident:
        current = self.load(incident_id)
        if current.repaired:
            return current
        execution_reassessment = self._execution_reassessment_event(current)
        if execution_reassessment is not None:
            context_project_id = self._project_id(context.project_id)
            if context_project_id and context_project_id != current.project_id:
                raise RecoveryAutopilotError(
                    "Fresh evidence belongs to a different Recovery project"
                )
            if not context_project_id and current.project_id:
                context = replace(context, project_id=current.project_id)
        current_device_key = self._context_device_key(context)
        if current.device_key:
            if current_device_key and not hmac.compare_digest(
                current.device_key, current_device_key
            ):
                raise RecoveryTargetMismatchError(
                    "Fresh device evidence does not match this recovery incident"
                )
        elif current_device_key:
            raise RecoveryTargetMismatchError(
                "This targetless recovery incident has no sealed device identity"
            )
        updated = self._assess(context, current, datetime.now(UTC).isoformat())
        if execution_reassessment is not None and (
            updated.incident_id != current.incident_id
            or updated.project_id != current.project_id
            or not hmac.compare_digest(updated.device_key, current.device_key)
            or updated.pack_id != current.pack_id
            or not hmac.compare_digest(updated.pack_sha256, current.pack_sha256)
        ):
            raise RecoveryAutopilotError(
                "Fresh evidence changed the sealed execution incident identity"
            )
        if self._semantic_state(updated) == self._semantic_state(current):
            return current
        self._save(updated)
        return updated

    def reassess_execution(
        self,
        preparation: GuardianRecoveryPreparation,
        execution_results: RecoveryExecutionResultEvidenceStore,
    ) -> RecoveryIncident:
        """Consume one exact aggregate without retrying, repairing, or verifying."""

        if not isinstance(preparation, GuardianRecoveryPreparation) or not isinstance(
            execution_results, RecoveryExecutionResultEvidenceStore
        ):
            raise RecoveryAutopilotError("Recovery reassessment input is not an exact aggregate")
        if execution_results.workspace.resolve() != self.workspace.resolve():
            raise RecoveryAutopilotError(
                "Recovery reassessment evidence belongs to a different workspace"
            )
        result = execution_results.load(preparation)
        if result is None:
            raise RecoveryAutopilotError(
                "Recovery reassessment requires the exact durable execution result"
            )
        try:
            validate_recovery_execution_result_evidence(preparation, result)
        except RecoveryContractError as exc:
            raise RecoveryAutopilotError(
                "Recovery reassessment requires sealed aggregate evidence"
            ) from exc
        incident = self.load(result.incident_id)
        mapping = {
            RecoveryExecutionResultState.SEQUENCE_COMPLETED_AWAITING_REASSESSMENT: (
                self.EXECUTION_COMPLETED_EVENT,
                RecoveryIncidentState.VERIFYING,
                "Recovery actions completed; verification is still required",
                "The exact Recovery action sequence completed. ROMVERSE has not declared the "
                "phone repaired; independent fresh post-repair verification is required next.",
            ),
            RecoveryExecutionResultState.FAILED_AWAITING_REASSESSMENT: (
                self.EXECUTION_FAILED_EVENT,
                RecoveryIncidentState.EMERGENCY,
                "Recovery execution stopped after a known failure",
                "The exact Recovery action sequence recorded a known failure at step "
                f"{result.terminal_step_order}. Execution is stopped for diagnosis; no action "
                "will be retried automatically.",
            ),
            RecoveryExecutionResultState.UNKNOWN_AWAITING_RECONSTRUCTION: (
                self.EXECUTION_UNKNOWN_EVENT,
                RecoveryIncidentState.EMERGENCY,
                "Recovery execution outcome is unknown",
                "The exact Recovery action sequence has an unknown outcome at step "
                f"{result.terminal_step_order}. Device state must be reconstructed before any "
                "new action; ROMVERSE will not blindly retry it.",
            ),
        }
        event_type, state, title, detail = mapping[result.state]
        latest = self._execution_reassessment_event(incident)
        if latest is not None:
            if (
                latest.event_type != event_type
                or latest.state is not state
                or latest.title != title
                or latest.detail != detail
                or not hmac.compare_digest(latest.evidence_digest, result.result_digest)
                or incident.incident_id != result.incident_id
                or incident.project_id != result.project_id
                or not hmac.compare_digest(incident.device_key, result.device_key)
                or incident.pack_id != result.device_pack_id
                or not hmac.compare_digest(incident.pack_sha256, result.device_pack_sha256)
                or incident.state is not state
                or incident.routes
                or incident.diagnosis != detail
                or incident.repaired
                or incident.verified_reboot
                or incident.phone_changed
            ):
                raise RecoveryAutopilotError(
                    "Recovery incident changed after its execution reassessment"
                )
            return incident
        route = next((item for item in incident.routes if item.route_id == result.route_id), None)
        if (
            incident.repaired
            or incident.phone_changed
            or not hmac.compare_digest(incident.record_digest, result.incident_record_digest)
            or incident.incident_id != result.incident_id
            or incident.project_id != result.project_id
            or not hmac.compare_digest(incident.device_key, result.device_key)
            or incident.pack_id != result.device_pack_id
            or not hmac.compare_digest(incident.pack_sha256, result.device_pack_sha256)
            or route is None
            or not route.changes_device
            or not route.confirmation_required
            or route.execution_authority != "none"
            or route.owner_route != "guardian_core"
            or result.same_incident_preserved is not True
            or result.recovery_reassessment_required is not True
            or result.recovery_verified is not False
            or result.device_repaired is not False
            or result.execution_authority != "none"
            or result.automatic_retry_allowed is not False
            or result.bootloader_relock_allowed is not False
        ):
            raise RecoveryAutopilotError(
                "Recovery aggregate no longer matches the exact active incident"
            )
        now = datetime.now(UTC).isoformat()
        event = RecoveryIncidentEvent(
            sequence=len(incident.events) + 1,
            observed_at=now,
            event_type=event_type,
            state=state,
            mode=incident.mode,
            title=title,
            detail=detail,
            evidence_digest=result.result_digest,
        )
        updated = self._seal(
            replace(
                incident,
                updated_at=now,
                state=state,
                diagnosis=detail,
                routes=(),
                events=(*incident.events, event)[-self.MAX_EVENTS :],
                repaired=False,
                verified_reboot=False,
                phone_changed=False,
                record_digest="",
            )
        )
        self._save(updated)
        persisted = self.load(updated.incident_id)
        if persisted != updated:
            raise RecoveryAutopilotError(
                "Recovery reassessment could not be verified after durable recording"
            )
        return persisted

    def verify_execution_recovery(
        self,
        preparation: GuardianRecoveryPreparation,
        execution_results: RecoveryExecutionResultEvidenceStore,
        boot_observations: RecoveryBootEvidenceStore,
        device: AndroidDevice,
    ) -> RecoveryIncident:
        """Verify one completed Recovery execution from fresh read-only boot evidence."""

        if (
            not isinstance(preparation, GuardianRecoveryPreparation)
            or not isinstance(execution_results, RecoveryExecutionResultEvidenceStore)
            or not isinstance(boot_observations, RecoveryBootEvidenceStore)
            or not isinstance(device, AndroidDevice)
        ):
            raise RecoveryAutopilotError(
                "Recovery verification requires exact typed evidence inputs"
            )
        if (
            execution_results.workspace.resolve() != self.workspace.resolve()
            or boot_observations.workspace.resolve() != self.workspace.resolve()
            or boot_observations.registry is not self.registry
        ):
            raise RecoveryAutopilotError(
                "Recovery verification evidence belongs to a different workspace"
            )
        result = execution_results.load(preparation)
        if result is None:
            raise RecoveryAutopilotError(
                "Recovery verification requires the exact durable execution result"
            )
        try:
            validate_recovery_execution_result_evidence(preparation, result)
        except RecoveryContractError as exc:
            raise RecoveryAutopilotError(
                "Recovery verification requires sealed aggregate evidence"
            ) from exc
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
        ):
            raise RecoveryAutopilotError(
                "Only a completed exact sequence can enter Recovery verification"
            )
        incident = self.load(result.incident_id)
        reassessment = self._execution_reassessment_event(incident)
        if (
            reassessment is None
            or reassessment.event_type != self.EXECUTION_COMPLETED_EVENT
            or reassessment.state is not RecoveryIncidentState.VERIFYING
            or not hmac.compare_digest(reassessment.evidence_digest, result.result_digest)
            or incident.incident_id != result.incident_id
            or incident.project_id != result.project_id
            or not hmac.compare_digest(incident.device_key, result.device_key)
            or incident.pack_id != result.device_pack_id
            or not hmac.compare_digest(incident.pack_sha256, result.device_pack_sha256)
            or incident.phone_changed
            or incident.routes
        ):
            raise RecoveryAutopilotError(
                "Recovery verification no longer matches the exact reassessed incident"
            )
        observed_key = self._device_key(device)
        if not observed_key or not hmac.compare_digest(observed_key, result.device_key):
            raise RecoveryTargetMismatchError(
                "Fresh device evidence does not match the exact Recovery phone"
            )
        now = datetime.now(UTC)
        receipt = boot_observations.load_recovery(
            result.project_id,
            device,
            preparation,
            execution_results,
        )
        try:
            validate_recovery_boot_evidence(receipt)
        except RecoveryContractError as exc:
            raise RecoveryAutopilotError(
                "Recovery verification boot evidence is incomplete or unreadable"
            ) from exc
        pack = next(
            (
                item
                for item in self.registry.packs
                if item.pack_id == result.device_pack_id
                and hmac.compare_digest(item.sha256, result.device_pack_sha256)
            ),
            None,
        )
        try:
            project = boot_observations.project_evidence(result.project_id)
            resolution = self.registry.resolve(device)
            first_sample_at = datetime.fromisoformat(receipt.samples[0].observed_at)
            latest_sample_at = datetime.fromisoformat(receipt.samples[-1].observed_at)
            result_recorded_at = datetime.fromisoformat(result.recorded_at)
        except (AttributeError, IndexError, ProjectError, TypeError, ValueError) as exc:
            raise RecoveryAutopilotError(
                "Recovery verification boot evidence is incomplete or unreadable"
            ) from exc
        latest_sample = receipt.samples[-1]
        build = pack.build_contract if pack is not None else None
        existing_verification = next(
            (
                event
                for event in reversed(incident.events)
                if event.event_type == self.EXECUTION_VERIFIED_EVENT
            ),
            None,
        )
        if (
            receipt is None
            or pack is None
            or build is None
            or project.project_id != result.project_id
            or project.device_pack_id != result.device_pack_id
            or not hmac.compare_digest(
                project.source_original_sha256,
                result.source_original_sha256,
            )
            or resolution.pack is None
            or resolution.pack.pack_id != pack.pack_id
            or not hmac.compare_digest(resolution.pack.sha256, pack.sha256)
            or not observed_key
            or not hmac.compare_digest(observed_key, result.device_key)
            or device.state is not DeviceState.DEVICE
            or device.boot_completed is not True
            or receipt.project_id != result.project_id
            or receipt.pack_id != result.device_pack_id
            or receipt.contract_id != build.contract_id
            or not hmac.compare_digest(
                receipt.source_original_sha256,
                result.source_original_sha256,
            )
            or receipt.status is not BootObservationStatus.STABLE
            or receipt.stable is not True
            or receipt.reboot_detected is not False
            or receipt.flash_linked is not True
            or not hmac.compare_digest(
                receipt.guardian_execution_receipt_digest,
                result.result_digest,
            )
            or receipt.verified_first_boot is not True
            or receipt.phone_changed is not False
            or receipt.failure_kind is not BootFailureKind.NONE
            or not receipt.samples
            or any(
                not hmac.compare_digest(sample.device_pseudonym, result.device_key)
                for sample in receipt.samples
            )
            or latest_sample.state != DeviceState.DEVICE.value
            or latest_sample.boot_completed is not True
            or latest_sample.slot_suffix != device.slot_suffix
            or latest_sample.build_id != device.build_id
            or latest_sample.build_fingerprint != device.build_fingerprint
            or (
                latest_sample.uptime_seconds is not None
                and device.uptime_seconds is not None
                and device.uptime_seconds + 30 < latest_sample.uptime_seconds
            )
            or first_sample_at < result_recorded_at
            or latest_sample_at > now
            or (
                existing_verification is None
                and (now - latest_sample_at).total_seconds()
                > self.MAX_RECOVERY_BOOT_EVIDENCE_AGE_SECONDS
            )
        ):
            raise RecoveryAutopilotError(
                "Recovery verification requires fresh stable boot evidence from the exact phone"
            )
        evidence_digest = self._digest(
            {
                "aggregate_result_digest": result.result_digest,
                "reassessment_evidence_digest": reassessment.evidence_digest,
                "boot_observation_digest": receipt.receipt_digest,
                "device_evidence_digest": self._device_evidence_digest(device),
            }
        )
        if existing_verification is not None:
            if (
                incident.state is not RecoveryIncidentState.RECOVERED
                or incident.repaired is not True
                or incident.verified_reboot is not True
                or incident.boot_observation_digest != receipt.receipt_digest
                or not hmac.compare_digest(
                    existing_verification.evidence_digest,
                    evidence_digest,
                )
            ):
                raise RecoveryAutopilotError(
                    "Recovery verification history changed after completion"
                )
            return incident
        if (
            incident.state is not RecoveryIncidentState.VERIFYING
            or incident.repaired
            or incident.verified_reboot
        ):
            raise RecoveryAutopilotError(
                "Recovery incident is not awaiting independent verification"
            )
        detail = (
            "Fresh exact-device evidence proves Android remained boot-complete on the same build "
            "and slot across the stability window after the completed Recovery sequence."
        )
        event = RecoveryIncidentEvent(
            sequence=len(incident.events) + 1,
            observed_at=now.isoformat(),
            event_type=self.EXECUTION_VERIFIED_EVENT,
            state=RecoveryIncidentState.RECOVERED,
            mode="adb",
            title="Recovery verified by fresh stable boot evidence",
            detail=detail,
            evidence_digest=evidence_digest,
        )
        updated = self._seal(
            replace(
                incident,
                updated_at=now.isoformat(),
                mode="adb",
                state=RecoveryIncidentState.RECOVERED,
                diagnosis=detail,
                after_evidence_digest=self._after_evidence_digest(device, pack),
                boot_observation_digest=receipt.receipt_digest,
                routes=(),
                events=(*incident.events, event)[-self.MAX_EVENTS :],
                repaired=True,
                verified_reboot=True,
                phone_changed=False,
                record_digest="",
            )
        )
        self._save(updated)
        persisted = self.load(updated.incident_id)
        if persisted != updated:
            raise RecoveryAutopilotError(
                "Recovery verification could not be confirmed after durable recording"
            )
        return persisted

    def record_route_result(
        self,
        incident_id: str,
        route_id: str,
        outcome: str,
        detail: str,
    ) -> RecoveryIncident:
        incident = self.load(incident_id)
        clean_route = self._identifier(route_id, 80, "route identifier")
        normalized_outcome = self._identifier(outcome, 24, "route outcome")
        if normalized_outcome not in self.ACTION_OUTCOMES:
            raise RecoveryAutopilotError("Unsupported Recovery Autopilot route outcome")
        route = next((item for item in incident.routes if item.route_id == clean_route), None)
        if route is None:
            raise RecoveryAutopilotError("Recovery route no longer matches this incident")
        now = datetime.now(UTC).isoformat()
        clean_detail = self._text(detail, 1_000, optional=True) or (
            "No additional result detail was supplied."
        )
        event = RecoveryIncidentEvent(
            sequence=len(incident.events) + 1,
            observed_at=now,
            event_type=f"route_{normalized_outcome}",
            state=incident.state,
            mode=incident.mode,
            title=f"{route.title} • {normalized_outcome.replace('_', ' ')}",
            detail=clean_detail,
            evidence_digest=self._digest(
                {
                    "incident_id": incident.incident_id,
                    "route_id": route.route_id,
                    "outcome": normalized_outcome,
                    "detail": clean_detail,
                }
            ),
        )
        state = (
            RecoveryIncidentState.VERIFYING if normalized_outcome == "succeeded" else incident.state
        )
        updated = self._seal(
            replace(
                incident,
                updated_at=now,
                state=state,
                events=(*incident.events, event)[-self.MAX_EVENTS :],
                repaired=False,
                verified_reboot=False,
                record_digest="",
            )
        )
        self._save(updated)
        return updated

    def validate_route_handoff(
        self,
        incident_id: str,
        route_id: str,
        *,
        owner_route: str = "",
        device: AndroidDevice | None = None,
        require_exact_device: bool = False,
    ) -> tuple[RecoveryIncident, RecoveryRoute]:
        """Reload one route and, when consequential, bind it to fresh device evidence.

        This is the shared domain boundary for typed route owners.  A UI selection,
        historical device name, matching model, or earlier route review is never
        sufficient to assign a phone-changing Recovery route to a current target.
        """

        incident = self.load(incident_id)
        if incident.repaired or incident.phone_changed:
            raise RecoveryAutopilotError("Recovery incident is no longer active")
        clean_route = self._identifier(route_id, 80, "route identifier")
        route = next((item for item in incident.routes if item.route_id == clean_route), None)
        if route is None:
            raise RecoveryAutopilotError("Recovery route no longer matches this incident")
        if owner_route and route.owner_route != self._identifier(owner_route, 60, "route owner"):
            raise RecoveryAutopilotError("Recovery route owner changed after ranking")
        exact_device_required = require_exact_device or route.changes_device
        if exact_device_required:
            if device is None or not incident.device_key:
                raise RecoveryTargetMismatchError(
                    "The phone involved in this Recovery incident is not freshly available"
                )
            observed_key = self._device_key(device)
            if not observed_key or not hmac.compare_digest(incident.device_key, observed_key):
                raise RecoveryTargetMismatchError(
                    "Fresh device evidence does not match this Recovery incident"
                )
        return incident, route

    def load(self, incident_id: str) -> RecoveryIncident:
        clean_id = self._hex(incident_id, 32, "incident identifier")
        try:
            payload = read_json_object(
                self.root / f"{clean_id}{self.SUFFIX}",
                boundary=self.workspace,
                maximum_bytes=self.MAXIMUM_BYTES,
            )
            return self._parse(payload)
        except (LocalStoreError, KeyError, TypeError, ValueError) as exc:
            raise RecoveryAutopilotError(f"Recovery incident is unreadable: {exc}") from exc

    def list_recent(self) -> tuple[RecoveryIncident, ...]:
        try:
            paths = bounded_regular_files(
                self.root,
                self.SUFFIX,
                boundary=self.workspace,
                maximum_entries=self.MAX_SCAN_ENTRIES,
            )
        except (FileNotFoundError, LocalStoreError, OSError):
            return ()
        incidents: list[RecoveryIncident] = []
        for path in paths:
            try:
                payload = read_json_object(
                    path,
                    boundary=self.workspace,
                    maximum_bytes=self.MAXIMUM_BYTES,
                )
                incidents.append(self._parse(payload))
            except (LocalStoreError, KeyError, TypeError, ValueError):
                continue
        return tuple(
            sorted(incidents, key=lambda item: item.updated_at, reverse=True)[: self.MAX_INCIDENTS]
        )

    def _assess(
        self,
        context: RecoveryAutopilotContext,
        previous: RecoveryIncident | None,
        now: str,
    ) -> RecoveryIncident:
        device = context.device
        project_id = self._project_id(context.project_id)
        device_key = self._context_device_key(context) or (previous.device_key if previous else "")
        device_name = (
            self._text(device.display_name, 120)
            if device is not None
            else previous.device_name
            if previous is not None
            else "Android device"
        )
        pack = self._pack(device, previous)
        execution_reassessment = self._execution_reassessment_event(previous)
        if execution_reassessment is not None and context.boot_observation is not None:
            raise RecoveryAutopilotError(
                "Post-repair evidence requires the independent verification boundary"
            )
        self._validate_boot_observation(context, project_id, device_key, pack)
        mode = self._mode(device)
        after_digest = self._after_evidence_digest(device, pack)
        before_digest = self._optional_hex(context.before_evidence_digest, 64) or (
            previous.before_evidence_digest if previous is not None else after_digest
        )
        boot = context.boot_observation
        boot_digest = (self._optional_hex(boot.receipt_digest, 64) if boot is not None else "") or (
            previous.boot_observation_digest if previous is not None else ""
        )
        archive_digest = (
            self._optional_hex(context.knowledge_report.archive_digest, 64)
            if context.knowledge_report is not None
            else ""
        ) or (previous.knowledge_archive_digest if previous is not None else "")
        recovery_ready = bool(
            context.recovery_evidence is not None and context.recovery_evidence.ready
        )
        verified_reboot = (
            False
            if execution_reassessment is not None
            else self._verified_reboot(context, previous, device_key)
        )
        repaired = verified_reboot
        if execution_reassessment is not None and not repaired:
            state = (
                RecoveryIncidentState.VERIFYING
                if execution_reassessment.event_type == self.EXECUTION_COMPLETED_EVENT
                else RecoveryIncidentState.EMERGENCY
            )
            routes = ()
            diagnosis = execution_reassessment.detail
        else:
            state = self._state(context, previous, repaired)
            routes = () if repaired else self._routes(context, pack, mode)
            diagnosis = self._diagnosis(context, state, mode, pack)
        evidence_digest = self._digest(
            {
                "trigger": context.trigger.value,
                "project_id": project_id,
                "device_key": device_key,
                "mode": mode,
                "state": state.value,
                "after_evidence_digest": after_digest,
                "boot_observation_digest": boot_digest,
                "knowledge_archive_digest": archive_digest,
                "recovery_evidence_ready": recovery_ready,
                "routes": [asdict(item) for item in routes],
            }
        )
        events = previous.events if previous is not None else ()
        changed = (
            previous is None
            or previous.state is not state
            or previous.mode != mode
            or previous.after_evidence_digest != after_digest
            or previous.boot_observation_digest != boot_digest
            or previous.routes != routes
        )
        if changed:
            event = RecoveryIncidentEvent(
                sequence=len(events) + 1,
                observed_at=now,
                event_type="incident_opened" if previous is None else "evidence_refreshed",
                state=state,
                mode=mode,
                title=(
                    "Recovery verified by fresh boot evidence"
                    if repaired
                    else "Recovery incident opened"
                    if previous is None
                    else "Recovery evidence refreshed"
                ),
                detail=diagnosis,
                evidence_digest=evidence_digest,
            )
            events = (*events, event)[-self.MAX_EVENTS :]
        incident = RecoveryIncident(
            schema_version=self.SCHEMA_VERSION,
            incident_id=previous.incident_id if previous is not None else uuid4().hex,
            created_at=previous.created_at if previous is not None else now,
            updated_at=now,
            project_id=project_id,
            trigger=previous.trigger if previous is not None else context.trigger,
            device_key=device_key,
            device_name=device_name,
            pack_id=pack.pack_id if pack is not None else previous.pack_id if previous else "",
            pack_sha256=(
                pack.sha256 if pack is not None else previous.pack_sha256 if previous else ""
            ),
            mode=mode,
            state=state,
            diagnosis=diagnosis,
            before_evidence_digest=before_digest,
            after_evidence_digest=after_digest,
            boot_observation_digest=boot_digest,
            knowledge_archive_digest=archive_digest,
            recovery_evidence_ready=recovery_ready,
            routes=routes,
            events=events,
            repaired=repaired,
            verified_reboot=verified_reboot,
            phone_changed=False,
            record_digest="",
        )
        return self._seal(incident)

    def _execution_reassessment_event(
        self,
        incident: RecoveryIncident | None,
    ) -> RecoveryIncidentEvent | None:
        if incident is None:
            return None
        return next(
            (
                event
                for event in reversed(incident.events)
                if event.event_type in self.EXECUTION_REASSESSMENT_EVENTS
            ),
            None,
        )

    def _routes(
        self,
        context: RecoveryAutopilotContext,
        pack: DevicePack | None,
        mode: str,
    ) -> tuple[RecoveryRoute, ...]:
        device = context.device
        routes: list[RecoveryRoute] = []
        knowledge_ids, knowledge_evidence, knowledge_boost = self._knowledge(context)

        def add(
            kind: RecoveryRouteKind,
            title: str,
            summary: str,
            confidence: int,
            risk: RecoveryRouteRisk,
            owner: str,
            *,
            changes: bool = False,
            confirmation: bool = False,
            authority: str = "none",
            requirements: tuple[str, ...] = (),
            evidence: tuple[str, ...] = (),
            use_knowledge: bool = False,
        ) -> None:
            attached_ids = knowledge_ids if use_knowledge else ()
            attached_evidence = knowledge_evidence if use_knowledge else ()
            routes.append(
                RecoveryRoute(
                    route_id=f"recovery.{kind.value}",
                    kind=kind,
                    title=title,
                    summary=summary,
                    confidence=min(99, confidence + (knowledge_boost if use_knowledge else 0)),
                    risk=risk,
                    rank=0,
                    changes_device=changes,
                    confirmation_required=confirmation,
                    execution_authority=authority,
                    owner_route=owner,
                    requirements=requirements,
                    evidence=(*evidence, *attached_evidence),
                    knowledge_record_ids=attached_ids,
                )
            )

        if device is None:
            add(
                RecoveryRouteKind.RECONNECT_USB,
                "Restore the USB evidence link",
                "Reconnect the same phone with a known-good data cable, then run a fresh read-only scan.",
                96,
                RecoveryRouteRisk.LOW,
                "command_deck",
                requirements=(
                    "Same target phone",
                    "USB data connection",
                    "Fresh Device Engine scan",
                ),
                evidence=("No Android transport is currently visible",),
            )
            add(
                RecoveryRouteKind.PHYSICAL_CHECK,
                "Check power and volume buttons",
                "Remove the case and verify no hardware button is held before another boot attempt.",
                74,
                RecoveryRouteRisk.INFORMATIONAL,
                "recovery_bay",
                evidence=("A held key can repeatedly force bootloader or recovery entry",),
                use_knowledge=True,
            )
        elif device.state is DeviceState.UNAUTHORIZED:
            add(
                RecoveryRouteKind.AUTHORIZE_ADB,
                "Authorize this computer on the phone",
                "Unlock the screen, confirm the RSA prompt, and refresh. ROMVERSE cannot bypass Android authorization.",
                98,
                RecoveryRouteRisk.LOW,
                "command_deck",
                requirements=("Visible Android RSA prompt", "User confirmation on the exact phone"),
                evidence=("ADB reports unauthorized",),
            )
        elif device.state is DeviceState.OFFLINE:
            if context.host_repair_available:
                add(
                    RecoveryRouteKind.HOST_ADB_REPAIR,
                    "Restart only the host ADB service",
                    "Use the existing bounded host-only recovery plan, then rescan the phone.",
                    94,
                    RecoveryRouteRisk.LOW,
                    "recovery_bay",
                    confirmation=True,
                    authority="confirmed-host-only",
                    requirements=(
                        "Verified Platform Tools",
                        "Explicit confirmation",
                        "Fresh rescan",
                    ),
                    evidence=(
                        "ADB reports the selected transport offline",
                        "No phone command is included",
                    ),
                )
            add(
                RecoveryRouteKind.RECONNECT_USB,
                "Re-establish the USB transport",
                "Reconnect the same phone and rerun Device Engine before considering a device change.",
                88,
                RecoveryRouteRisk.LOW,
                "command_deck",
                evidence=("ADB transport is present but offline",),
            )
        elif device.state in {DeviceState.RECOVERY, DeviceState.SIDELOAD}:
            add(
                RecoveryRouteKind.RECOVERY_LOG_REVIEW,
                "Inspect recovery state and logs",
                "Capture read-only recovery evidence and identify the exact failed partition or update step.",
                91,
                RecoveryRouteRisk.INFORMATIONAL,
                "recovery_bay",
                requirements=("Exact recovery mode", "Read-only evidence capture"),
                evidence=(f"Device Engine reports {mode}",),
                use_knowledge=True,
            )
        elif device.is_fastboot:
            add(
                RecoveryRouteKind.REFRESH_SCAN,
                "Confirm exact bootloader identity and mode",
                "Refresh read-only evidence before choosing a slot or stock-restoration route.",
                95,
                RecoveryRouteRisk.INFORMATIONAL,
                "device_atlas",
                evidence=(f"Device Engine reports {mode}",),
            )
        else:
            add(
                RecoveryRouteKind.OBSERVE_BOOT,
                "Continue measured boot observation",
                "Keep the phone connected and collect the next valid sample; elapsed time alone cannot prove recovery.",
                96,
                RecoveryRouteRisk.INFORMATIONAL,
                "rom_studio",
                requirements=(
                    "Fresh boot sample",
                    "Stable Android reconnect",
                    "Matching Device DNA",
                ),
                evidence=(
                    f"Android boot-completed signal: {device.boot_completed}",
                    f"Current slot: {device.slot_suffix or 'not reported'}",
                ),
                use_knowledge=True,
            )

        transition = self._transition_contract(pack)
        if transition is not None and device is not None:
            build = pack.build_contract if pack is not None else None
            write = build.partition_write_contract if build is not None else None
            if device.ab_update is True and device.slot_suffix in {"_a", "_b", "a", "b"}:
                add(
                    RecoveryRouteKind.SLOT_REVIEW,
                    "Review the recorded pre-write slot route",
                    "Guardian can review the Pack-declared rollback slot. No slot switch starts from this recommendation.",
                    82,
                    RecoveryRouteRisk.MEDIUM,
                    "guardian_core",
                    changes=True,
                    confirmation=True,
                    requirements=(
                        "Signed schema-three Device Pack",
                        "Recorded pre-write slot evidence",
                        "Fresh exact-target check",
                        "Separate Guardian confirmation",
                    ),
                    evidence=(
                        f"Current A/B slot reports {device.slot_suffix}",
                        f"Recovery contract {transition.contract_id}",
                    ),
                    use_knowledge=True,
                )
            if write is not None and write.writes:
                targets = tuple(f"{rule.partition} ← {rule.artifact}" for rule in write.writes)
                add(
                    RecoveryRouteKind.IMAGE_RESTORE_REVIEW,
                    "Review exact partition-image restoration",
                    "Guardian can review only the Pack-declared, source-bound image set. The recommendation cannot flash or substitute an image.",
                    76,
                    RecoveryRouteRisk.HIGH,
                    "guardian_core",
                    changes=True,
                    confirmation=True,
                    requirements=(
                        "Signed schema-three Device Pack",
                        "Fresh hashes for every exact source-bound image",
                        "Exact partition-to-artifact binding",
                        "Verified readback and rollback route",
                        "Separate Guardian confirmation",
                    ),
                    evidence=(
                        f"Write contract {write.contract_id}",
                        "Pack-declared image set: " + ", ".join(targets),
                    ),
                    use_knowledge=True,
                )
            stock_ready = bool(
                context.recovery_evidence is not None
                and context.recovery_evidence.stock_recovery_ready
            )
            add(
                RecoveryRouteKind.EXACT_STOCK_RESTORE,
                "Review exact stock-package restoration",
                "Use only the source-bound stock package and Pack-declared recovery adapter after Guardian revalidation.",
                78 if stock_ready else 61,
                RecoveryRouteRisk.HIGH,
                "guardian_core" if stock_ready else "time_machine",
                changes=True,
                confirmation=True,
                requirements=(
                    "Exact source-bound stock package"
                    + (" verified" if stock_ready else " must be registered and verified"),
                    "External backup when required by the signed contract",
                    "Fresh exact-target check",
                    "Separate Guardian confirmation",
                ),
                evidence=(
                    f"Recovery adapter {transition.recovery.adapter_id}",
                    f"Stock package SHA-256 {transition.recovery.stock_package_sha256[:20]}…",
                ),
                use_knowledge=True,
            )
            if transition.recovery.may_wipe_user_data:
                add(
                    RecoveryRouteKind.DATA_RESET_GUIDANCE,
                    "Last resort: review a data-reset consequence",
                    "A reset is destructive and never automatic. Back up first and confirm separately only if exact evidence requires it.",
                    35,
                    RecoveryRouteRisk.DESTRUCTIVE,
                    "guardian_core",
                    changes=True,
                    confirmation=True,
                    requirements=(
                        "All non-destructive routes exhausted",
                        "Verified external backup",
                        "Separate explicit destructive-action confirmation",
                    ),
                    evidence=("Signed contract declares that recovery may wipe user data",),
                )

        cache_ids, cache_evidence, cache_boost = self._cache_guidance(context)
        if cache_ids:
            add(
                RecoveryRouteKind.CACHE_GUIDANCE,
                "Review device-scoped cache guidance",
                "Follow only the matched Archive record and confirm the exact non-user-data cache scope. ROMVERSE does not assume that a cache partition exists.",
                min(88, 69 + cache_boost),
                RecoveryRouteRisk.MEDIUM,
                "recovery_bay",
                changes=True,
                confirmation=True,
                requirements=(
                    "Medium-or-better Device DNA or failure-evidence match",
                    "Exact cache target and recovery method confirmed",
                    "No user-data scope or ambiguous partition deletion",
                    "Separate confirmation and fresh boot verification",
                ),
                evidence=cache_evidence,
            )
            routes[-1] = replace(routes[-1], knowledge_record_ids=cache_ids)

        if knowledge_ids:
            add(
                RecoveryRouteKind.ARCHIVES_REVIEW,
                "Review matched offline recovery evidence",
                "Open the source-labelled Archives matches that informed this ranking.",
                72,
                RecoveryRouteRisk.INFORMATIONAL,
                "archives",
                use_knowledge=True,
            )
        add(
            RecoveryRouteKind.AUTHORIZED_SERVICE,
            "Escalate with the incident evidence bundle",
            "If identity, power, storage, or signed recovery evidence remains uncertain, stop and use an authorized repair route.",
            30,
            RecoveryRouteRisk.LOW,
            "recovery_bay",
            requirements=("Export the privacy-safe incident timeline",),
            evidence=("This fallback performs no automated device change",),
        )
        risk_order = {
            RecoveryRouteRisk.INFORMATIONAL: 0,
            RecoveryRouteRisk.LOW: 1,
            RecoveryRouteRisk.MEDIUM: 2,
            RecoveryRouteRisk.HIGH: 3,
            RecoveryRouteRisk.DESTRUCTIVE: 4,
        }
        ordered = sorted(routes, key=lambda item: (risk_order[item.risk], -item.confidence))
        return tuple(replace(item, rank=index) for index, item in enumerate(ordered, 1))

    def _verified_reboot(
        self,
        context: RecoveryAutopilotContext,
        previous: RecoveryIncident | None,
        device_key: str,
    ) -> bool:
        device = context.device
        if (
            device is None
            or device.state is not DeviceState.DEVICE
            or device.boot_completed is not True
            or not device_key
        ):
            return False
        if (
            previous is not None
            and previous.device_key
            and not hmac.compare_digest(previous.device_key, device_key)
        ):
            return False
        boot = context.boot_observation
        post_flash = context.trigger in {
            RecoveryTrigger.FLASH_FAILURE,
            RecoveryTrigger.BOOTLOOP,
            RecoveryTrigger.BOOT_ATTENTION,
        } or (
            previous is not None
            and previous.trigger
            in {
                RecoveryTrigger.FLASH_FAILURE,
                RecoveryTrigger.BOOTLOOP,
                RecoveryTrigger.BOOT_ATTENTION,
            }
        )
        if post_flash:
            return bool(
                boot is not None
                and boot.status is BootObservationStatus.STABLE
                and boot.stable
                and boot.flash_linked
                and boot.verified_first_boot
                and boot.samples
                and boot.samples[-1].device_pseudonym == device_key
                and boot.samples[-1].state == DeviceState.DEVICE.value
                and boot.samples[-1].boot_completed is True
            )
        if previous is None:
            return False
        return any(event.mode != "adb" for event in previous.events)

    def _validate_boot_observation(
        self,
        context: RecoveryAutopilotContext,
        project_id: str,
        device_key: str,
        pack: DevicePack | None,
    ) -> None:
        """Refuse boot evidence that is not bound to the fresh exact target."""

        receipt = context.boot_observation
        if receipt is None:
            return
        observed_device_key = self._device_key(context.device)
        if not observed_device_key:
            raise RecoveryAutopilotError(
                "Fresh exact-device evidence is required before boot observation can be attached"
            )
        if not device_key or not hmac.compare_digest(device_key, observed_device_key):
            raise RecoveryTargetMismatchError(
                "Boot observation does not match this recovery incident"
            )
        try:
            receipt_project_id = self._project_id(receipt.project_id)
            receipt_digest = self._optional_hex(receipt.receipt_digest, 64)
            guardian_digest = self._optional_hex(
                receipt.guardian_execution_receipt_digest,
                64,
            )
        except (TypeError, ValueError) as exc:
            raise RecoveryAutopilotError("Boot observation evidence is invalid") from exc
        build = pack.build_contract if pack is not None else None
        if (
            receipt.phone_changed
            or receipt_project_id != project_id
            or pack is None
            or build is None
            or receipt.pack_id != pack.pack_id
            or receipt.contract_id != build.contract_id
            or receipt.source_original_sha256 != build.source.archive_sha256
            or not receipt.samples
            or any(
                not isinstance(sample.device_pseudonym, str)
                or not hmac.compare_digest(sample.device_pseudonym, observed_device_key)
                for sample in receipt.samples
            )
        ):
            raise RecoveryTargetMismatchError(
                "Boot observation does not match this recovery incident"
            )
        if (
            receipt.schema_version != RECOVERY_BOOT_OBSERVATION_SCHEMA_VERSION
            or not receipt_digest
            or receipt.flash_linked != bool(guardian_digest)
            or receipt.verified_first_boot is not bool(receipt.flash_linked and receipt.stable)
        ):
            raise RecoveryAutopilotError("Boot observation evidence is invalid")

    @staticmethod
    def _state(
        context: RecoveryAutopilotContext,
        previous: RecoveryIncident | None,
        repaired: bool,
    ) -> RecoveryIncidentState:
        if repaired:
            return RecoveryIncidentState.RECOVERED
        device = context.device
        if device is None or device.state in {
            DeviceState.OFFLINE,
            DeviceState.RECOVERY,
            DeviceState.SIDELOAD,
            DeviceState.FASTBOOT,
            DeviceState.FASTBOOTD,
            DeviceState.BOOTLOADER,
            DeviceState.UNKNOWN,
        }:
            return RecoveryIncidentState.EMERGENCY
        if device.state is DeviceState.UNAUTHORIZED:
            return RecoveryIncidentState.STABILIZING
        if previous is not None and any(
            event.event_type in {"route_started", "route_succeeded"}
            for event in previous.events[-4:]
        ):
            return RecoveryIncidentState.VERIFYING
        return RecoveryIncidentState.STABILIZING

    def _diagnosis(
        self,
        context: RecoveryAutopilotContext,
        state: RecoveryIncidentState,
        mode: str,
        pack: DevicePack | None,
    ) -> str:
        if state is RecoveryIncidentState.RECOVERED:
            return (
                "Fresh evidence shows the same phone booted, reconnected through authorized ADB, "
                "and satisfied the required verified boot observation."
            )
        detail = self._text(context.message, 1_000, optional=True)
        boot = context.boot_observation
        if boot is not None:
            detail = self._text(boot.diagnosis, 1_000, optional=True) or detail
        pack_text = (
            f" Exact Device Pack: {pack.display_name}."
            if pack is not None
            else " No exact Device Pack is currently proven."
        )
        lead = {
            "disconnected": "The target phone is not visible to Device Engine.",
            "adb-unauthorized": "The USB transport is visible, but Android authorization is missing.",
            "adb-offline": "ADB sees the transport but cannot communicate with it reliably.",
            "recovery": "The phone is in recovery mode instead of a verified Android boot.",
            "sideload": "The phone is in recovery sideload mode instead of a verified Android boot.",
            "fastboot": "The phone is in Fastboot mode instead of a verified Android boot.",
            "fastbootd": "The phone is in Fastbootd mode instead of a verified Android boot.",
            "bootloader": "The phone is in bootloader mode instead of a verified Android boot.",
            "adb": "Android is visible; stable post-recovery boot proof is still pending.",
        }.get(mode, "The current connection state is not sufficient to prove recovery.")
        return self._text(f"{lead}{pack_text}" + (f" Evidence: {detail}" if detail else ""), 1_500)

    def _knowledge(
        self,
        context: RecoveryAutopilotContext,
    ) -> tuple[tuple[str, ...], tuple[str, ...], int]:
        report = context.knowledge_report
        if report is None or report.execution_authority != "none":
            return (), (), 0
        matches = report.matches[:3]
        ids = tuple(match.record.record_id for match in matches)
        evidence = tuple(
            f"Offline Archives: {match.record.title} ({match.confidence.value} match)"
            for match in matches
        )
        boost = max(
            (
                {
                    MatchConfidence.EXACT: 8,
                    MatchConfidence.HIGH: 6,
                    MatchConfidence.MEDIUM: 3,
                    MatchConfidence.LOW: 1,
                    MatchConfidence.UNCONFIRMED: 0,
                }[match.confidence]
                for match in matches
            ),
            default=0,
        )
        return ids, evidence, boost

    @staticmethod
    def _cache_guidance(
        context: RecoveryAutopilotContext,
    ) -> tuple[tuple[str, ...], tuple[str, ...], int]:
        """Return only scoped Archive evidence that explicitly discusses cache recovery."""

        report = context.knowledge_report
        if report is None or report.execution_authority != "none":
            return (), (), 0
        accepted = {
            MatchConfidence.EXACT: 8,
            MatchConfidence.HIGH: 6,
            MatchConfidence.MEDIUM: 3,
        }
        scoped = []
        for match in report.matches[:8]:
            if match.confidence not in accepted:
                continue
            record = match.record
            corpus = " ".join(
                (
                    record.title,
                    record.summary,
                    *record.symptoms,
                    *record.diagnostic_steps,
                    *record.fix_steps,
                    *record.prerequisites,
                    *record.recovery_routes,
                    *record.tags,
                )
            ).casefold()
            if re.search(r"\bcach(?:e|es|ed|ing)\b", corpus):
                scoped.append(match)
        matches = tuple(scoped[:3])
        if not matches:
            return (), (), 0
        return (
            tuple(match.record.record_id for match in matches),
            tuple(
                f"Scoped Archives cache guidance: {match.record.title} "
                f"({match.confidence.value} match)"
                for match in matches
            ),
            max(accepted[match.confidence] for match in matches),
        )

    def _pack(
        self,
        device: AndroidDevice | None,
        previous: RecoveryIncident | None,
    ) -> DevicePack | None:
        if device is not None:
            resolution = self.registry.resolve(device)
            if resolution.pack is not None and resolution.pack.manufacturers != ("*",):
                return resolution.pack
        if previous is not None and previous.pack_id:
            return next(
                (
                    pack
                    for pack in self.registry.packs
                    if pack.pack_id == previous.pack_id and pack.sha256 == previous.pack_sha256
                ),
                None,
            )
        return None

    def _transition_contract(self, pack: DevicePack | None):
        build = pack.build_contract if pack is not None else None
        write = build.partition_write_contract if build is not None else None
        if (
            build is None
            or write is None
            or not self.registry.transition_recovery_contract_is_valid(write, build.source)
        ):
            return None
        return write.transition_recovery_contract

    def _after_evidence_digest(
        self,
        device: AndroidDevice | None,
        pack: DevicePack | None,
    ) -> str:
        transition = self._transition_contract(pack)
        return self._digest(
            {
                "device_dna_digest": self._device_evidence_digest(device),
                "pack_id": pack.pack_id if pack is not None else "",
                "pack_sha256": pack.sha256 if pack is not None else "",
                "partition_recovery_contract": (
                    transition.contract_id if transition is not None else ""
                ),
                "slot_suffix": device.slot_suffix[:32] if device is not None else "",
            }
        )

    def _device_key(self, device: AndroidDevice | None) -> str:
        return self.privacy.pseudonym(device.serial) if device is not None and device.serial else ""

    def _context_device_key(self, context: RecoveryAutopilotContext) -> str:
        try:
            expected = self._optional_hex(context.expected_device_key, 20)
        except (TypeError, ValueError) as exc:
            raise RecoveryAutopilotError(
                "The recovery incident's sealed device identity is invalid"
            ) from exc
        observed = self._device_key(context.device)
        if expected and observed and not hmac.compare_digest(expected, observed):
            raise RecoveryTargetMismatchError(
                "Fresh device evidence does not match this recovery incident"
            )
        return expected or observed

    @staticmethod
    def _mode(device: AndroidDevice | None) -> str:
        if device is None:
            return "disconnected"
        return {
            DeviceState.DEVICE: "adb",
            DeviceState.UNAUTHORIZED: "adb-unauthorized",
            DeviceState.OFFLINE: "adb-offline",
        }.get(device.state, device.state.value)

    def _device_evidence_digest(self, device: AndroidDevice | None) -> str:
        if device is None:
            return self._digest({"mode": "disconnected"})
        return self._digest(
            {
                "device_key": self._device_key(device),
                "state": device.state.value,
                "manufacturer": device.manufacturer[:80],
                "model": device.model[:120],
                "product": device.product[:120],
                "codename": device.codename[:120],
                "build_id": device.build_id[:160],
                "build_fingerprint": device.build_fingerprint[:500],
                "build_incremental": device.build_incremental[:160],
                "slot_suffix": device.slot_suffix[:32],
                "boot_completed": device.boot_completed,
                "verified_boot": device.verified_boot[:80],
                "bootloader_locked": device.bootloader_locked,
            }
        )

    def _save(self, incident: RecoveryIncident) -> None:
        if not incident.integrity_verified or not hmac.compare_digest(
            incident.record_digest, self._incident_digest(incident)
        ):
            raise RecoveryAutopilotError("Recovery incident integrity envelope is invalid")
        payload: dict[str, object] = {
            "format": self.FORMAT,
            "schema_version": self.SCHEMA_VERSION,
            "privacy": "pseudonymous-local",
            "incident": asdict(incident),
        }
        try:
            self._parse(payload)
            ensure_private_directory(self.root, boundary=self.workspace)
            atomic_write_json(
                self.root / f"{incident.incident_id}{self.SUFFIX}",
                payload,
                boundary=self.workspace,
                maximum_bytes=self.MAXIMUM_BYTES,
            )
        except (LocalStoreError, KeyError, TypeError, ValueError) as exc:
            raise RecoveryAutopilotError(f"Could not preserve recovery incident: {exc}") from exc

    def _parse(self, payload: object) -> RecoveryIncident:
        if not isinstance(payload, dict) or set(payload) != {
            "format",
            "schema_version",
            "privacy",
            "incident",
        }:
            raise ValueError("recovery incident envelope is invalid")
        if (
            payload["format"] != self.FORMAT
            or payload["schema_version"] != self.SCHEMA_VERSION
            or payload["privacy"] != "pseudonymous-local"
        ):
            raise ValueError("unsupported recovery incident schema")
        item = payload["incident"]
        if not isinstance(item, dict) or set(item) != set(RecoveryIncident.__dataclass_fields__):
            raise ValueError("recovery incident fields do not match the schema")
        routes = self._parse_routes(item["routes"])
        events = self._parse_events(item["events"])
        incident = RecoveryIncident(
            schema_version=self._integer(item["schema_version"], 1, 1),
            incident_id=self._hex(item["incident_id"], 32, "incident identifier"),
            created_at=self._timestamp(item["created_at"]),
            updated_at=self._timestamp(item["updated_at"]),
            project_id=self._project_id(item["project_id"]),
            trigger=RecoveryTrigger(item["trigger"]),
            device_key=self._optional_hex(item["device_key"], 20),
            device_name=self._text(item["device_name"], 120),
            pack_id=self._optional_identifier(item["pack_id"], 100),
            pack_sha256=self._optional_hex(item["pack_sha256"], 64),
            mode=self._identifier(item["mode"], 40, "device mode"),
            state=RecoveryIncidentState(item["state"]),
            diagnosis=self._text(item["diagnosis"], 1_500),
            before_evidence_digest=self._hex(
                item["before_evidence_digest"], 64, "before evidence digest"
            ),
            after_evidence_digest=self._hex(
                item["after_evidence_digest"], 64, "after evidence digest"
            ),
            boot_observation_digest=self._optional_hex(item["boot_observation_digest"], 64),
            knowledge_archive_digest=self._optional_hex(item["knowledge_archive_digest"], 64),
            recovery_evidence_ready=self._boolean(item["recovery_evidence_ready"]),
            routes=routes,
            events=events,
            repaired=self._boolean(item["repaired"]),
            verified_reboot=self._boolean(item["verified_reboot"]),
            phone_changed=self._boolean(item["phone_changed"]),
            record_digest=self._hex(item["record_digest"], 64, "record digest"),
        )
        if datetime.fromisoformat(incident.updated_at) < datetime.fromisoformat(
            incident.created_at
        ):
            raise ValueError("recovery incident update precedes creation")
        if not incident.events or tuple(event.sequence for event in incident.events) != tuple(
            range(incident.events[0].sequence, incident.events[0].sequence + len(incident.events))
        ):
            raise ValueError("recovery incident timeline is invalid")
        if incident.repaired != incident.verified_reboot or (
            incident.repaired and incident.state is not RecoveryIncidentState.RECOVERED
        ):
            raise ValueError("recovery outcome is not backed by verified reboot evidence")
        if incident.state is RecoveryIncidentState.RECOVERED and incident.routes:
            raise ValueError("recovered incident still contains pending routes")
        if not hmac.compare_digest(incident.record_digest, self._incident_digest(incident)):
            raise ValueError("recovery incident integrity mismatch")
        return incident

    def _parse_routes(self, value: object) -> tuple[RecoveryRoute, ...]:
        if not isinstance(value, (list, tuple)) or len(value) > 24:
            raise ValueError("recovery routes are invalid")
        routes: list[RecoveryRoute] = []
        for item in value:
            if not isinstance(item, dict) or set(item) != set(RecoveryRoute.__dataclass_fields__):
                raise ValueError("recovery route fields are invalid")
            routes.append(
                RecoveryRoute(
                    route_id=self._identifier(item["route_id"], 80, "route identifier"),
                    kind=RecoveryRouteKind(item["kind"]),
                    title=self._text(item["title"], 160),
                    summary=self._text(item["summary"], 600),
                    confidence=self._integer(item["confidence"], 0, 100),
                    risk=RecoveryRouteRisk(item["risk"]),
                    rank=self._integer(item["rank"], 1, 24),
                    changes_device=self._boolean(item["changes_device"]),
                    confirmation_required=self._boolean(item["confirmation_required"]),
                    execution_authority=self._identifier(
                        item["execution_authority"], 60, "execution authority"
                    ),
                    owner_route=self._identifier(item["owner_route"], 60, "owner route"),
                    requirements=self._text_tuple(item["requirements"], 16, 300),
                    evidence=self._text_tuple(item["evidence"], 24, 500),
                    knowledge_record_ids=self._identifier_tuple(
                        item["knowledge_record_ids"], 8, 120
                    ),
                )
            )
        if tuple(route.rank for route in routes) != tuple(range(1, len(routes) + 1)):
            raise ValueError("recovery route ranking is invalid")
        if len({route.route_id for route in routes}) != len(routes):
            raise ValueError("recovery route identifiers are duplicated")
        if any(
            route.changes_device
            and (not route.confirmation_required or route.execution_authority != "none")
            for route in routes
        ):
            raise ValueError("device-changing recovery route bypasses confirmation")
        destructive = [route for route in routes if route.risk is RecoveryRouteRisk.DESTRUCTIVE]
        if destructive and any(route.rank != len(routes) for route in destructive):
            # A destructive route can never outrank any non-destructive repair or
            # escalation path. It remains the absolute last resort.
            raise ValueError("destructive recovery route is not the last repair option")
        return tuple(routes)

    def _parse_events(self, value: object) -> tuple[RecoveryIncidentEvent, ...]:
        if not isinstance(value, (list, tuple)) or not 1 <= len(value) <= self.MAX_EVENTS:
            raise ValueError("recovery timeline is invalid")
        events: list[RecoveryIncidentEvent] = []
        for item in value:
            if not isinstance(item, dict) or set(item) != set(
                RecoveryIncidentEvent.__dataclass_fields__
            ):
                raise ValueError("recovery event fields are invalid")
            events.append(
                RecoveryIncidentEvent(
                    sequence=self._integer(item["sequence"], 1, 10_000),
                    observed_at=self._timestamp(item["observed_at"]),
                    event_type=self._identifier(item["event_type"], 60, "event type"),
                    state=RecoveryIncidentState(item["state"]),
                    mode=self._identifier(item["mode"], 40, "device mode"),
                    title=self._text(item["title"], 200),
                    detail=self._text(item["detail"], 1_500),
                    evidence_digest=self._hex(item["evidence_digest"], 64, "event evidence digest"),
                )
            )
        return tuple(events)

    def _prune(self) -> None:
        try:
            paths = bounded_regular_files(
                self.root,
                self.SUFFIX,
                boundary=self.workspace,
                maximum_entries=self.MAX_SCAN_ENTRIES,
            )
            dated = sorted(((path.stat().st_mtime_ns, path) for path in paths), reverse=True)
            for _modified, path in dated[self.MAX_INCIDENTS :]:
                remove_regular_file(path, boundary=self.workspace)
        except (FileNotFoundError, LocalStoreError, OSError):
            return

    @classmethod
    def _seal(cls, incident: RecoveryIncident) -> RecoveryIncident:
        return replace(incident, record_digest=cls._incident_digest(incident))

    @classmethod
    def _incident_digest(cls, incident: RecoveryIncident) -> str:
        payload = asdict(replace(incident, record_digest=""))
        payload.pop("record_digest")
        return cls._digest(payload)

    @staticmethod
    def _semantic_state(incident: RecoveryIncident) -> tuple[object, ...]:
        """Exclude only timestamps and the envelope digest from refresh deduplication."""

        return (
            incident.project_id,
            incident.trigger,
            incident.device_key,
            incident.device_name,
            incident.pack_id,
            incident.pack_sha256,
            incident.mode,
            incident.state,
            incident.diagnosis,
            incident.before_evidence_digest,
            incident.after_evidence_digest,
            incident.boot_observation_digest,
            incident.knowledge_archive_digest,
            incident.recovery_evidence_ready,
            incident.routes,
            incident.events,
            incident.repaired,
            incident.verified_reboot,
            incident.phone_changed,
        )

    @staticmethod
    def _digest(payload: object) -> str:
        return hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()

    @classmethod
    def _project_id(cls, value: object) -> str:
        if value == "":
            return ""
        return cls._identifier(value, 100, "project identifier")

    @staticmethod
    def _text(value: object, maximum: int, *, optional: bool = False) -> str:
        if not isinstance(value, str):
            raise TypeError("recovery incident text is invalid")
        clean = value.replace("\x00", " ").strip()
        if (not clean and not optional) or len(clean) > maximum:
            raise ValueError("recovery incident text is invalid")
        return clean

    @classmethod
    def _text_tuple(cls, value: object, maximum_items: int, maximum: int) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)) or len(value) > maximum_items:
            raise ValueError("recovery incident text collection is invalid")
        return tuple(cls._text(item, maximum) for item in value)

    @classmethod
    def _identifier(cls, value: object, maximum: int, label: str) -> str:
        clean = cls._text(value, maximum)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:\-]*", clean):
            raise ValueError(f"invalid {label}")
        return clean

    @classmethod
    def _optional_identifier(cls, value: object, maximum: int) -> str:
        return "" if value == "" else cls._identifier(value, maximum, "optional identifier")

    @classmethod
    def _identifier_tuple(cls, value: object, maximum_items: int, maximum: int) -> tuple[str, ...]:
        values = cls._text_tuple(value, maximum_items, maximum)
        normalized = tuple(cls._identifier(item, maximum, "identifier") for item in values)
        if len(set(normalized)) != len(normalized):
            raise ValueError("recovery identifiers are duplicated")
        return normalized

    @staticmethod
    def _integer(value: object, minimum: int, maximum: int) -> int:
        if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
            raise ValueError("recovery incident integer is invalid")
        return value

    @staticmethod
    def _boolean(value: object) -> bool:
        if type(value) is not bool:
            raise TypeError("recovery incident boolean is invalid")
        return value

    @staticmethod
    def _hex(value: object, length: int, label: str) -> str:
        if not isinstance(value, str) or not re.fullmatch(rf"[0-9a-f]{{{length}}}", value):
            raise ValueError(f"invalid {label}")
        return value

    @classmethod
    def _optional_hex(cls, value: object, length: int) -> str:
        return "" if value == "" else cls._hex(value, length, "optional digest")

    @staticmethod
    def _timestamp(value: object) -> str:
        if not isinstance(value, str) or len(value) > 80:
            raise ValueError("recovery incident timestamp is invalid")
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError("recovery incident timestamp requires a timezone")
        return parsed.astimezone(UTC).isoformat()
