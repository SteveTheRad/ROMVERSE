from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import StrEnum

from romverse.device.catalog import DeviceCatalogMatch
from romverse.device_packs.models import DevicePack
from romverse.device_packs.validation import (
    DevicePackValidationReport,
    ValidationCheck,
    ValidationState,
)
from romverse.infrastructure.provisioning import ROM_STUDIO_TOOL_CATALOG
from romverse.infrastructure.tools import ToolStatus


class RequirementState(StrEnum):
    VERIFIED = "verified"
    DECLARED = "declared"
    NEEDS_EVIDENCE = "needs-evidence"
    LOCKED = "locked"


@dataclass(frozen=True, slots=True)
class DeviceRequirementLane:
    lane_id: str
    title: str
    state: RequirementState
    badge: str
    summary: str
    requirements: tuple[str, ...]
    route: str
    article_key: str
    button_label: str


@dataclass(frozen=True, slots=True)
class ProjectSourceRequirements:
    """Strict project-local source evidence carried into Device Atlas.

    This can prove a protected source and its local preparation requirements. It is
    deliberately unable to grant a published Device Pack or phone-write authority.
    """

    project_id: str
    project_name: str
    source_sha256: str
    device_pack_id: str
    source_kind: str
    blueprint_digest: str
    plan_digest: str
    authority: str
    manufacturer: str
    codename: str
    build_id: str
    partition_count: int
    required_tools: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DeviceRequirementsBlueprint:
    """One read-only answer for identity, build, compile, and flash requirements."""

    report_digest: str
    pack_id: str
    pack_sha256: str
    model: str
    codename: str
    lanes: tuple[DeviceRequirementLane, ...]
    project_id: str = ""
    project_name: str = ""
    project_source_sha256: str = ""
    project_device_pack_id: str = ""
    source_kind: str = ""
    source_blueprint_digest: str = ""
    source_plan_digest: str = ""
    source_authority: str = ""
    source_build_id: str = ""
    source_partition_count: int = 0
    source_required_tools: tuple[str, ...] = ()

    def lane(self, lane_id: str) -> DeviceRequirementLane | None:
        return next((lane for lane in self.lanes if lane.lane_id == lane_id), None)

    @property
    def project_scoped(self) -> bool:
        return bool(self.project_id and self.project_source_sha256)


class DeviceRequirementsService:
    """Derive requirements from current identity, Pack, tools, and strict project evidence."""

    GUIDE_KEY = "device-build-requirements-blueprint"

    def assess(
        self,
        pack: DevicePack,
        report: DevicePackValidationReport,
        official_identity: DeviceCatalogMatch | None = None,
        tool_statuses: tuple[ToolStatus, ...] | None = None,
        project_source: ProjectSourceRequirements | None = None,
    ) -> DeviceRequirementsBlueprint:
        if (
            report.pack_id != pack.pack_id
            or report.pack_version != pack.version
            or report.pack_sha256 != pack.sha256
        ):
            raise ValueError("Device requirements need the exact current Device Pack report")
        checks = {check.check_id: check for check in report.checks}
        build_unresolved = self._unresolved(report.checks, "build")
        flash_unresolved = self._unresolved(report.checks, "flash")
        exact_model = checks.get("exact-model")
        project_required_tools: tuple[str, ...] = ()

        identity = self._identity_lane(exact_model, official_identity, report)
        if project_source is None:
            build = self._build_lane(pack, report, build_unresolved)
            compile_lane = self._compile_lane(pack, tool_statuses)
            flash = self._flash_lane(report, flash_unresolved)
        else:
            self._validate_project_source(project_source, report)
            source_bound_contract = bool(
                pack.build_contract is not None
                and report.build_contract_ready
                and pack.build_contract.source.archive_sha256 == project_source.source_sha256
            )
            project_required_tools = (
                pack.build_contract.required_tools
                if source_bound_contract and pack.build_contract is not None
                else project_source.required_tools
            )
            build = self._project_build_lane(project_source, pack, source_bound_contract)
            compile_lane = self._project_compile_lane(
                project_source,
                pack,
                tool_statuses,
                source_bound_contract,
            )
            flash = self._project_flash_lane(
                project_source,
                report,
                flash_unresolved,
                source_bound_contract,
            )
        return DeviceRequirementsBlueprint(
            report_digest=report.report_digest,
            pack_id=pack.pack_id,
            pack_sha256=pack.sha256,
            model=report.model,
            codename=report.codename,
            lanes=(identity, build, compile_lane, flash),
            project_id=project_source.project_id if project_source is not None else "",
            project_name=project_source.project_name if project_source is not None else "",
            project_source_sha256=(
                project_source.source_sha256 if project_source is not None else ""
            ),
            project_device_pack_id=(
                project_source.device_pack_id if project_source is not None else ""
            ),
            source_kind=project_source.source_kind if project_source is not None else "",
            source_blueprint_digest=(
                project_source.blueprint_digest if project_source is not None else ""
            ),
            source_plan_digest=(project_source.plan_digest if project_source is not None else ""),
            source_authority=project_source.authority if project_source is not None else "",
            source_build_id=project_source.build_id if project_source is not None else "",
            source_partition_count=(
                project_source.partition_count if project_source is not None else 0
            ),
            source_required_tools=(project_required_tools if project_source is not None else ()),
        )

    @staticmethod
    def _validate_project_source(
        source: ProjectSourceRequirements,
        report: DevicePackValidationReport,
    ) -> None:
        authority = {
            "ota-payload": "project-local-build-evidence-only",
            "fastboot-super": "project-local-build-evidence-only",
            "partition-bundle": "project-local-inventory-evidence-only",
        }.get(source.source_kind)
        if (
            not re.fullmatch(r"[a-z0-9-]{1,64}", source.project_id)
            or not source.project_name.strip()
            or len(source.project_name) > 80
            or not re.fullmatch(r"[0-9a-f]{64}", source.source_sha256)
            or not re.fullmatch(r"[0-9a-f]{64}", source.blueprint_digest)
            or not re.fullmatch(r"[0-9a-f]{64}", source.plan_digest)
            or authority is None
            or source.authority != authority
            or not source.manufacturer.strip()
            or not source.codename.strip()
            or not source.build_id.strip()
            or not 1 <= source.partition_count <= 1_024
            or not source.required_tools
            or len(source.required_tools) != len(set(source.required_tools))
            or any(not name.strip() or len(name) > 80 for name in source.required_tools)
            or any(name not in ROM_STUDIO_TOOL_CATALOG for name in source.required_tools)
            or source.manufacturer.casefold() != report.manufacturer.casefold()
            or source.codename.casefold() != report.codename.casefold()
        ):
            raise ValueError(
                "Project requirements need an exact current source blueprint and matching phone"
            )

    @staticmethod
    def _unresolved(
        checks: tuple[ValidationCheck, ...],
        required_for: str,
    ) -> tuple[ValidationCheck, ...]:
        return tuple(
            check
            for check in checks
            if check.required_for == required_for and check.state is not ValidationState.PASS
        )

    def _identity_lane(
        self,
        exact_model: ValidationCheck | None,
        official: DeviceCatalogMatch | None,
        report: DevicePackValidationReport,
    ) -> DeviceRequirementLane:
        if official is not None and official.matched:
            retail = official.marketing_name or report.model
            return DeviceRequirementLane(
                "identity",
                "1 • Identify the phone",
                RequirementState.VERIFIED,
                "OFFICIAL ID • READ ONLY",
                f"Google's catalog identifies {retail} from the exact Build.BRAND / Build.DEVICE pair.",
                (
                    "Keep retail identity separate from firmware, partition, build, and flash authority.",
                ),
                "archives",
                "android-device-identity-catalog",
                "Review identity evidence",
            )
        if exact_model is not None and exact_model.state is ValidationState.PASS:
            return DeviceRequirementLane(
                "identity",
                "1 • Identify the phone",
                RequirementState.DECLARED,
                "PACK-SCOPED ID • VERIFY OFFICIAL",
                f"The active Device Pack explicitly matches {report.model} / {report.codename}.",
                (
                    "Sync the official Android ID catalog when available for an independent retail-name check.",
                ),
                "archives",
                "android-device-identity-catalog",
                "Review identity boundary",
            )
        reason = (
            official.reason
            if official is not None and official.reason
            else "No exact official or Device Pack model identity is verified"
        )
        return DeviceRequirementLane(
            "identity",
            "1 • Identify the phone",
            RequirementState.NEEDS_EVIDENCE,
            "IDENTITY UNCONFIRMED • NO GUESS",
            reason,
            (
                "A fresh Build.BRAND, Build.DEVICE, model, product, and codename scan",
                "An exact official catalog match or reviewed model-scoped Device Pack",
            ),
            "archives",
            "android-device-identity-catalog",
            "Open identity guide",
        )

    def _build_lane(
        self,
        pack: DevicePack,
        report: DevicePackValidationReport,
        unresolved: tuple[ValidationCheck, ...],
    ) -> DeviceRequirementLane:
        contract = pack.build_contract
        if report.build_contract_ready and contract is not None:
            return DeviceRequirementLane(
                "build",
                "2 • Bind the build contract",
                RequirementState.VERIFIED,
                "EXACT BUILD CONTRACT • READY",
                f"{contract.contract_id} v{contract.version} binds the protected source, partition layout, and allowed outputs.",
                tuple(f"Editable partition: {name}" for name in contract.editable_partitions)
                + (f"Allowed outputs: {', '.join(contract.allowed_outputs)}",),
                "rom_studio",
                "",
                "Continue build planning",
            )
        missing = tuple(check.label for check in unresolved) or (
            "Exact model/source-bound build contract",
        )
        return DeviceRequirementLane(
            "build",
            "2 • Bind the build contract",
            RequirementState.LOCKED,
            "BUILD LOCKED • EVIDENCE REQUIRED",
            "Identity alone cannot define firmware hashes, dynamic partitions, editable images, or allowed outputs.",
            missing,
            "archives",
            self.GUIDE_KEY,
            "Open build requirements",
        )

    def _project_build_lane(
        self,
        source: ProjectSourceRequirements,
        pack: DevicePack,
        source_bound_contract: bool,
    ) -> DeviceRequirementLane:
        contract = pack.build_contract
        if source_bound_contract and contract is not None:
            return DeviceRequirementLane(
                "build",
                "2 • Bind the project build",
                RequirementState.VERIFIED,
                "PROJECT + EXACT PACK • BUILD READY",
                f"{contract.contract_id} v{contract.version} and the strict {source.source_kind} blueprint bind this exact protected project source.",
                tuple(f"Editable partition: {name}" for name in contract.editable_partitions)
                + (f"Allowed outputs: {', '.join(contract.allowed_outputs)}",),
                "rom_studio_project",
                "",
                "Review exact project build",
            )
        return DeviceRequirementLane(
            "build",
            "2 • Bind the project build",
            RequirementState.VERIFIED,
            "PROJECT SOURCE • LOCAL BASELINE READY",
            f"A strict {source.source_kind} blueprint binds {source.build_id}, the protected source, and {source.partition_count} observed partition records for local build preparation.",
            (
                f"Protected source SHA-256: {source.source_sha256}",
                f"Source plan: {source.plan_digest}",
                "Project-local preparation only; this is not a published Device Pack or flash contract",
            ),
            "rom_studio_project",
            "",
            "Review project Build & Proof",
        )

    def _project_compile_lane(
        self,
        source: ProjectSourceRequirements,
        pack: DevicePack,
        tool_statuses: tuple[ToolStatus, ...] | None,
        source_bound_contract: bool,
    ) -> DeviceRequirementLane:
        contract = pack.build_contract
        required = (
            contract.required_tools
            if source_bound_contract and contract is not None
            else source.required_tools
        )
        basis = (
            "the exact source-bound Device Pack contract"
            if source_bound_contract
            else f"the strict {source.source_kind} project blueprint"
        )
        if tool_statuses is None:
            return DeviceRequirementLane(
                "compile",
                "3 • Verify the project toolchain",
                RequirementState.DECLARED,
                f"{len(required)} SOURCE TOOLS • HOST CHECK NEEDED",
                f"Forge Arsenal must freshly verify every executable selected by {basis}.",
                required,
                "forge_arsenal_project",
                "",
                "Inspect project build tools",
            )
        verified: dict[str, ToolStatus] = {}
        duplicates: set[str] = set()
        for status in tool_statuses:
            if not isinstance(status, ToolStatus):
                continue
            if status.name in verified:
                duplicates.add(status.name)
            verified[status.name] = status
        missing = tuple(
            name
            for name in required
            if name in duplicates or name not in verified or not verified[name].available
        )
        ready = len(required) - len(missing)
        if missing:
            return DeviceRequirementLane(
                "compile",
                "3 • Verify the project toolchain",
                RequirementState.NEEDS_EVIDENCE,
                f"{ready}/{len(required)} TOOLS VERIFIED • {len(missing)} MISSING",
                f"The project source is known, but this host has not freshly verified every executable selected by {basis}.",
                missing,
                "forge_arsenal_project",
                "",
                "Resolve project build tools",
            )
        return DeviceRequirementLane(
            "compile",
            "3 • Verify the project toolchain",
            RequirementState.VERIFIED,
            f"{ready}/{len(required)} TOOLS VERIFIED • HOST READY",
            f"Forge Arsenal freshly verified every executable selected by {basis}.",
            required,
            "forge_arsenal_project",
            "",
            "Review project toolchain",
        )

    def _project_flash_lane(
        self,
        source: ProjectSourceRequirements,
        report: DevicePackValidationReport,
        unresolved: tuple[ValidationCheck, ...],
        source_bound_contract: bool,
    ) -> DeviceRequirementLane:
        if source_bound_contract:
            lane = self._flash_lane(report, unresolved)
            if lane.route == "rom_studio":
                return replace(
                    lane,
                    route="rom_studio_project",
                    summary=(
                        lane.summary
                        + " The current project source is bound to that same exact Pack contract."
                    ),
                )
            return lane
        return DeviceRequirementLane(
            "flash",
            "4 • Prove the flash contract",
            RequirementState.LOCKED,
            "FLASH LOCKED • EXACT WRITE CONTRACT REQUIRED",
            f"The verified {source.source_kind} project blueprint proves local source preparation only; it cannot authorize writes to this phone.",
            (
                "A reviewed Device Pack bound to this exact source and target",
                "Recovery, AVB, publisher, and independent physical-test evidence",
                "A signed exact partition-write contract for the produced artifact",
                "Guardian artifact binding and fresh explicit approval",
            ),
            "archives",
            self.GUIDE_KEY,
            "Open exact flash requirements",
        )

    def _compile_lane(
        self,
        pack: DevicePack,
        tool_statuses: tuple[ToolStatus, ...] | None,
    ) -> DeviceRequirementLane:
        contract = pack.build_contract
        if contract is not None:
            if tool_statuses is not None:
                verified: dict[str, ToolStatus] = {}
                duplicates: set[str] = set()
                for status in tool_statuses:
                    if not isinstance(status, ToolStatus):
                        continue
                    if status.name in verified:
                        duplicates.add(status.name)
                    verified[status.name] = status
                missing = tuple(
                    name
                    for name in contract.required_tools
                    if name in duplicates or name not in verified or not verified[name].available
                )
                ready = len(contract.required_tools) - len(missing)
                if not missing:
                    return DeviceRequirementLane(
                        "compile",
                        "3 • Verify the compile toolchain",
                        RequirementState.VERIFIED,
                        f"{ready}/{len(contract.required_tools)} TOOLS VERIFIED • HOST READY",
                        "Forge Arsenal freshly verified every executable declared by this exact Device Pack build contract.",
                        contract.required_tools,
                        "forge_arsenal",
                        "",
                        "Review verified toolchain",
                    )
                return DeviceRequirementLane(
                    "compile",
                    "3 • Verify the compile toolchain",
                    RequirementState.NEEDS_EVIDENCE,
                    f"{ready}/{len(contract.required_tools)} TOOLS VERIFIED • {len(missing)} MISSING",
                    "The exact contract is known, but this host has not freshly verified every required executable.",
                    missing,
                    "forge_arsenal",
                    "",
                    "Resolve missing build tools",
                )
            return DeviceRequirementLane(
                "compile",
                "3 • Verify the compile toolchain",
                RequirementState.DECLARED,
                f"{len(contract.required_tools)} TOOLS DECLARED • HOST CHECK NEEDED",
                "Forge Arsenal must freshly verify each exact executable before ROM Studio can use it.",
                contract.required_tools,
                "forge_arsenal",
                "",
                "Inspect exact build tools",
            )
        return DeviceRequirementLane(
            "compile",
            "3 • Verify the compile toolchain",
            RequirementState.LOCKED,
            "TOOLCHAIN UNKNOWN • NO GENERIC GUESS",
            "ROMVERSE will not install a generic tool bundle before an exact build contract declares what this firmware needs.",
            (
                "A reviewed ordered required_tools contract",
                "Official sources and a supported provisioning strategy for every missing tool",
            ),
            "archives",
            self.GUIDE_KEY,
            "Open toolchain requirements",
        )

    def _flash_lane(
        self,
        report: DevicePackValidationReport,
        unresolved: tuple[ValidationCheck, ...],
    ) -> DeviceRequirementLane:
        if report.flash_contract_ready:
            return DeviceRequirementLane(
                "flash",
                "4 • Prove the flash contract",
                RequirementState.VERIFIED,
                "FLASH CONTRACT EVIDENCE • READY",
                "The Pack's recovery, AVB, physical-test, publisher, write/readback, and transition-orchestration gates pass for this exact evidence.",
                (
                    "A built and signed artifact is still required",
                    "Guardian artifact binding and fresh explicit approval remain mandatory",
                ),
                "rom_studio",
                "",
                "Continue artifact build",
            )
        if not report.build_contract_ready:
            return DeviceRequirementLane(
                "flash",
                "4 • Prove the flash contract",
                RequirementState.LOCKED,
                "FLASH LOCKED • BUILD CONTRACT FIRST",
                "Flash evidence cannot be evaluated as ready while this phone lacks an exact build contract.",
                ("Complete every build-contract gate before evaluating device-writing evidence.",),
                "archives",
                self.GUIDE_KEY,
                "Review flash prerequisites",
            )
        stock_route = next(
            (check for check in unresolved if check.check_id == "stock-recovery-route"),
            None,
        )
        return DeviceRequirementLane(
            "flash",
            "4 • Prove the flash contract",
            RequirementState.NEEDS_EVIDENCE,
            "FLASH LOCKED • INDEPENDENT PROOF NEEDED",
            "Local build readiness does not prove that this exact phone can safely accept or recover from the resulting images.",
            tuple(check.label for check in unresolved),
            "time_machine" if stock_route is not None else "archives",
            "" if stock_route is not None else self.GUIDE_KEY,
            "Open stock recovery path" if stock_route is not None else "Open flash requirements",
        )
