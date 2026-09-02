from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from romverse.device.catalog import DeviceCatalogMatch
from romverse.device_packs.models import DevicePack
from romverse.device_packs.validation import (
    DevicePackValidationReport,
    ValidationCheck,
    ValidationState,
)
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
class DeviceRequirementsBlueprint:
    """One read-only answer for identity, build, compile, and flash requirements."""

    report_digest: str
    pack_id: str
    pack_sha256: str
    model: str
    codename: str
    lanes: tuple[DeviceRequirementLane, ...]

    def lane(self, lane_id: str) -> DeviceRequirementLane | None:
        return next((lane for lane in self.lanes if lane.lane_id == lane_id), None)


class DeviceRequirementsService:
    """Derive requirements only from current catalog, Pack, and validation evidence."""

    GUIDE_KEY = "device-build-requirements-blueprint"

    def assess(
        self,
        pack: DevicePack,
        report: DevicePackValidationReport,
        official_identity: DeviceCatalogMatch | None = None,
        tool_statuses: tuple[ToolStatus, ...] | None = None,
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

        identity = self._identity_lane(exact_model, official_identity, report)
        build = self._build_lane(pack, report, build_unresolved)
        compile_lane = self._compile_lane(pack, tool_statuses)
        flash = self._flash_lane(report, flash_unresolved)
        return DeviceRequirementsBlueprint(
            report.report_digest,
            pack.pack_id,
            pack.sha256,
            report.model,
            report.codename,
            (identity, build, compile_lane, flash),
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
                "The Pack's recovery, AVB, physical-test, publisher, and partition-write gates pass for this exact evidence.",
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
