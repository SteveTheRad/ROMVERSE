from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from romverse.ascension.assessment import AscensionAssessmentService
from romverse.ascension.build_handoff import RootRomBuildHandoffService
from romverse.ascension.handoff import load_root_patch_handoff
from romverse.ascension.integration import RootRomIntegrationService
from romverse.ascension.journey import build_journey_brief
from romverse.ascension.manager_launch import load_root_manager_launch
from romverse.ascension.manifest import AscensionGuardianManifestService
from romverse.ascension.models import AscensionMethod
from romverse.ascension.planning import AscensionRootPlanService
from romverse.ascension.preparation import RootPatchPreparationService
from romverse.ascension.releases import OfficialRootReleaseService
from romverse.ascension.resolution import build_resolution_plan
from romverse.ascension.route import AscensionRouteRecordService
from romverse.core.privacy import WorkspacePrivacy
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device.root_identity import review_root_identity
from romverse.device_packs.attestations import DevicePackAttestationStore
from romverse.device_packs.registry import DevicePackRegistry
from romverse.rom.guided import GuidedMissionStore
from romverse.rom.projects import ProjectError, RomProjectStore


@dataclass(frozen=True, slots=True)
class AscensionCompanionStatus:
    state: str = "no_project"
    project_name: str = ""
    method: str = "none"
    target_partition: str = ""
    blocker_count: int = 0
    phone_changed: bool = False
    execution_authority: str = "none"
    stage_number: int = 0
    stage_title: str = ""
    next_action: str = ""
    why: str = ""
    romverse_action: str = ""
    manager_state: str = "unavailable"
    manager_repository: str = ""
    manager_tag: str = ""
    manager_asset: str = ""
    manager_sha256_ref: str = ""


class AscensionCompanionStatusService:
    """Summarize local Ascension evidence for authenticated read-only display."""

    def __init__(
        self,
        store: RomProjectStore,
        registry: DevicePackRegistry,
        attestation_store: DevicePackAttestationStore | None = None,
        release_service: OfficialRootReleaseService | None = None,
    ) -> None:
        self.store = store
        self.registry = registry
        self.attestation_store = attestation_store
        self.release_service = release_service or OfficialRootReleaseService(store.workspace)

    def snapshot(
        self,
        project_id: str = "",
        device: AndroidDevice | None = None,
        companion: object | None = None,
    ) -> AscensionCompanionStatus:
        if not project_id:
            return AscensionCompanionStatus()
        try:
            project = self.store.get(project_id)
        except ProjectError:  # A removed project is equivalent to no active project for telemetry.
            return AscensionCompanionStatus()

        if device is not None and device.root_detected is True:
            root_review = review_root_identity(
                device.root_detected,
                device.root_manager_candidate,
                root_signal_source=device.root_signal_source,
                manager_evidence=device.root_manager_evidence,
            )
            return AscensionCompanionStatus(
                state="blocked",
                project_name=project.name[:120],
                method=(
                    root_review.manager_candidate
                    if root_review.manager_candidate in {item.value for item in AscensionMethod}
                    else "none"
                ),
                blocker_count=1,
                stage_number=1,
                stage_title=root_review.title,
                next_action=root_review.next_action,
                why=root_review.summary,
                romverse_action=(
                    "ROMVERSE paused preparation, preserved the existing root evidence, and will "
                    "not layer a second method or change the phone during review."
                ),
            )

        guided = GuidedMissionStore(self.store.projects_root / project_id).load()
        if guided.root_choice == "skip":
            integrated = any(
                RootRomIntegrationService(self.store).load(project_id, method) is not None
                for method in AscensionMethod
            )
            if integrated:
                return AscensionCompanionStatus(
                    state="blocked",
                    project_name=project.name[:120],
                    blocker_count=1,
                    stage_title="Restore the unrooted ROM input",
                    next_action="Open Genesis Sequence on Desktop and confirm Continue unrooted so ROMVERSE can restore the pristine local boot image.",
                    why="An unrooted build cannot continue while a rooted image remains integrated in its local working tree.",
                    romverse_action="ROMVERSE detected a rooted image in the isolated build tree and will restore the sealed pristine input before continuing unrooted.",
                )
            return AscensionCompanionStatus(
                state="skipped",
                project_name=project.name[:120],
                stage_title="Unrooted ROM selected",
                next_action="Genesis Sequence will continue with the standard unrooted build route.",
                why="Root is optional and no Ascension image will be packaged for this project.",
                romverse_action="ROMVERSE will keep Ascension out of the package and continue the isolated ROM build with the verified stock boot input.",
            )

        planning = AscensionRootPlanService(self.store)
        manifests = AscensionGuardianManifestService(
            self.store,
            self.registry,
            self.attestation_store,
        )
        preparation = RootPatchPreparationService(self.store, self.release_service)
        for method in AscensionMethod:
            plan = planning.load(project_id, method)
            if plan is None:
                continue
            if (
                device is not None
                and device.state is DeviceState.DEVICE
                and not planning.matches_device(plan, device)
            ):
                return self._with_guidance(
                    AscensionCompanionStatus(
                        "blocked",
                        project.name[:120],
                        method.value,
                        plan.target_partition,
                        1,
                    ),
                    project_id,
                    method,
                    device,
                    companion,
                )
            manifest = manifests.load(project_id, method)
            if manifest is None:
                return self._with_guidance(
                    AscensionCompanionStatus(
                        "preparing",
                        project.name[:120],
                        method.value,
                        plan.target_partition,
                    ),
                    project_id,
                    method,
                    device,
                    companion,
                )
            return self._with_guidance(
                AscensionCompanionStatus(
                    "review_ready" if manifest.review_ready else "blocked",
                    project.name[:120],
                    method.value,
                    manifest.target_partition,
                    len(manifest.blockers),
                ),
                project_id,
                method,
                device,
                companion,
            )

        prepared_method = next(
            (
                method
                for method in AscensionMethod
                if preparation.load(project_id, method) is not None
            ),
            None,
        )
        if prepared_method is not None:
            return self._with_guidance(
                AscensionCompanionStatus(
                    "preparing",
                    project.name[:120],
                    prepared_method.value,
                ),
                project_id,
                prepared_method,
                device,
                companion,
            )
        assessment = AscensionAssessmentService(
            self.store,
            self.registry,
            self.release_service,
        )
        try:
            route_record = AscensionRouteRecordService(
                self.store,
                self.registry,
                assessment,
            ).resolve(project_id, device, companion)
            method = route_record.candidate_method
            ready = route_record.ready_for_local_preparation
        except ProjectError:
            recommendation = assessment.recommend(project_id, device, companion)
            method = recommendation.method
            ready = recommendation.ready
        route = assessment.assess(project_id, method, device, companion)
        blockers = sum(gate.state.value == "blocked" for gate in route.gates)
        status = self._with_guidance(
            AscensionCompanionStatus(
                "not_started" if ready else "blocked",
                project.name[:120],
                method.value if ready else "none",
                _partition(route.patch_target),
                blockers,
            ),
            project_id,
            method,
            device,
            companion,
        )
        resolution = build_resolution_plan(route)
        if not ready and resolution.primary is not None:
            return replace(
                status,
                next_action=resolution.primary.user_action[:500],
                why=resolution.primary.why[:500],
                romverse_action=resolution.primary.romverse_action[:500],
            )
        return status

    def _with_guidance(
        self,
        status: AscensionCompanionStatus,
        project_id: str,
        method: AscensionMethod,
        device: AndroidDevice | None,
        companion: object | None,
    ) -> AscensionCompanionStatus:
        """Attach the same bounded next-step guide used by Desktop Ascension."""

        preparation = RootPatchPreparationService(self.store, self.release_service)
        capsule = preparation.load(project_id, method)
        patched = preparation.load_patched(project_id, method)
        integration = RootRomIntegrationService(self.store).load(project_id, method)
        build_handoff = RootRomBuildHandoffService(self.store).load(project_id, method)
        plan = AscensionRootPlanService(self.store).load(project_id, method)
        phone_handoff = load_root_patch_handoff(self.store, project_id, method)
        handoff_matches_device = phone_handoff is not None and (
            device is None
            or (
                device.state is DeviceState.DEVICE
                and bool(device.serial)
                and WorkspacePrivacy(self.store.workspace).pseudonym(device.serial)
                == phone_handoff.device_key
                and device.codename.casefold() == phone_handoff.device_codename.casefold()
            )
        )
        manager_launch = load_root_manager_launch(
            self.store,
            self.release_service,
            project_id,
            method,
        )
        manifest = AscensionGuardianManifestService(
            self.store,
            self.registry,
            self.attestation_store,
        ).load(project_id, method)
        report = AscensionAssessmentService(
            self.store,
            self.registry,
            self.release_service,
        ).assess(
            project_id,
            method,
            device,
            companion,
        )
        manager = self.release_service.load_verified(method)
        manager_verified = manager is not None
        brief = build_journey_brief(
            method,
            blocked=report.blocked and patched is None and not handoff_matches_device,
            manager_verified=manager_verified,
            capsule_ready=capsule is not None,
            handoff_ready=handoff_matches_device,
            patched_ready=patched is not None,
            integration_ready=integration is not None,
            build_handoff_ready=build_handoff is not None,
            plan_ready=plan is not None,
            manifest_ready=manifest is not None,
            review_ready=bool(manifest and manifest.review_ready),
            manager_opened=manager_launch is not None,
        )
        manager_evidence = {}
        if manager is not None and status.method == method.value:
            release, _path = manager
            manager_evidence = {
                "manager_state": "verified",
                "manager_repository": release.repository,
                "manager_tag": release.tag,
                "manager_asset": release.asset.name,
                "manager_sha256_ref": release.asset.sha256[:16],
            }
        target_partition = status.target_partition
        if not target_partition and plan is not None:
            target_partition = plan.target_partition
        if not target_partition and capsule is not None:
            target_partition = _partition(capsule.input_image_path)
        return replace(
            status,
            target_partition=target_partition,
            stage_number=brief.stage_number,
            stage_title=brief.title[:120],
            next_action=brief.user_action[:500],
            why=brief.why[:500],
            romverse_action=brief.romverse_action[:500],
            **manager_evidence,
        )


def _partition(value: str) -> str:
    candidate = Path(value).stem.casefold()
    supported = ("init_boot", "vendor_boot", "recovery", "boot")
    if candidate in supported:
        return candidate
    prefix, separator, suffix = candidate.partition("-")
    if (
        separator
        and len(prefix) == 16
        and all(character in "0123456789abcdef" for character in prefix)
        and suffix in supported
    ):
        return suffix
    return ""
