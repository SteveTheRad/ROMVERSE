"""Compose a rebuilt ROM into its exact, understood base installation procedure.

The two rebuilt images replace their source roles. Every remaining image must be
proven identical to the build OTA. This is local experimental evidence, not a
publisher signature, an OEM trust claim, or authority to change a phone.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from romverse.device_packs.registry import DevicePackRegistry
from romverse.infrastructure.process import CommandRunner
from romverse.infrastructure.tools import ToolStatus
from romverse.rom.base_image_compatibility import BaseImageCompatibilityService
from romverse.rom.build_execution import LocalDeviceBuildExecutor
from romverse.rom.builds import RomBuildPlanner
from romverse.rom.models import ProjectError
from romverse.rom.project_flash import ProjectFlashImage, ProjectFlashPreparationService
from romverse.rom.projects import RomProjectStore
from romverse.rom.release_forge import ReleaseForgeService, SignedAssemblyReceipt
from romverse.rom.signing_ceremony import (
    OfflineSigningCeremonyService,
    OfflineSigningReceipt,
)
from romverse.rom.source_installation import (
    SourceInstallationRecipe,
    SourceInstallationService,
    SourceInstallImage,
    _hash_stream,
)

if TYPE_CHECKING:
    from romverse.rom.candidate_avb import CandidateAvbService


@dataclass(frozen=True, slots=True)
class CandidateImageOrigin:
    member: str
    source_kind: str
    # Only rebuilt images have a workspace-relative file path. The base archive
    # path belongs to the parent recipe; no absolute paths enter public evidence.
    relative_path: str


@dataclass(frozen=True, slots=True)
class CandidateInstallationRecipe(SourceInstallationRecipe):
    composition_version: int
    procedure_project_id: str
    procedure_source_sha256: str
    procedure_recipe_digest: str
    base_receipt_digest: str
    build_receipt_digest: str
    build_plan_digest: str
    build_pack_sha256: str
    build_recipe_digest: str
    build_toolchain_digest: str
    avb_receipt_digest: str
    signing_receipt_digest: str
    signed_assembly_receipt_digest: str
    origins: tuple[CandidateImageOrigin, ...]

    @property
    def composition_digest(self) -> str:
        return self.recipe_digest


class CandidateInstallationService:
    """Prepare a complete local candidate without commands, extraction or fallback.

    Preparation saves the base/AVB services' private evidence. Verification only
    reads and freshly checks it; it must not renew those receipts behind an
    already reviewed plan. The transport still needs separate exact-device
    inspection, immutable-plan consent and private image staging.
    """

    COMPOSITION_VERSION = 2
    REBUILT_ROLES = ("super", "vbmeta_system")
    OUTPUT_ROLES = ("product", "vbmeta_system", "super")
    WARNINGS = (
        "LOCAL REBUILT ROM: the reviewed procedure uses your rebuilt super and vbmeta_system, plus 48 unchanged base images verified against the exact build OTA. No protected-source fallback is selected.",
        "This is an experimental installation on an unlocked, critical-unlocked device. Verified image relationships do not prove OEM signing trust, anti-rollback compatibility, a successful physical boot or subsystem health.",
        "Product is already inside the rebuilt super image; it is not flashed separately. The source-declared slot, whole-super and optional erase/reboot sequence remains unchanged.",
        "Installation, image readback, Android boot, stability and subsystem health are separate outcomes. A complete command sequence is not a tested release or a guarantee of data preservation.",
    )

    def __init__(
        self,
        store: RomProjectStore,
        registry: DevicePackRegistry,
        tool_statuses: tuple[ToolStatus, ...],
        runner: CommandRunner,
        *,
        base_service: BaseImageCompatibilityService | None = None,
        avb_service: CandidateAvbService | None = None,
        signing_service: OfflineSigningCeremonyService | None = None,
        release_service: ReleaseForgeService | None = None,
    ) -> None:
        self.store = store
        self.registry = registry
        self.tools = tool_statuses
        self.runner = runner
        self.sources = SourceInstallationService(store)
        self.base = base_service or BaseImageCompatibilityService(store, registry)
        if avb_service is None:
            from romverse.rom.candidate_avb import CandidateAvbService

            avb_service = CandidateAvbService(store, registry, tool_statuses, runner)
        self.avb = avb_service
        self.built = ProjectFlashPreparationService(store, registry)
        if signing_service is None:
            avbtool = next(
                (
                    Path(item.path)
                    for item in self.tools
                    if item.name == "AVBTool" and item.available and item.path
                ),
                None,
            )
            signing_service = (
                OfflineSigningCeremonyService(
                    store,
                    registry,
                    self.tools,
                    avbtool,
                    runner,
                )
                if avbtool is not None
                else None
            )
        self.signing = signing_service
        self.release = release_service or ReleaseForgeService(store, registry, self.tools)

    def import_procedure(self, selected_path: Path) -> str:
        """Protect an explicitly selected package, reusing an exact existing source.

        Called only by the preparation worker after the user selects a file.
        This does not associate it with a build or prove its compatibility; the
        normal prepare path performs those checks before any phone operation.
        """
        path = self.built._contained(Path(selected_path), Path(selected_path).parent)
        if path.suffix.casefold() != ".zip":
            raise ProjectError("Choose a ZIP containing the supported base installation procedure.")
        try:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, "rb") as stream:
                before = os.fstat(stream.fileno())
                if not 0 < before.st_size <= self.sources.MAX_PACKAGE_BYTES:
                    raise ProjectError(
                        "The selected base package is empty or exceeds the supported bound."
                    )
                digest, _ = _hash_stream(
                    stream,
                    before.st_size,
                    image=False,
                    maximum_expanded=self.sources.MAX_PACKAGE_BYTES,
                )
                if self.sources._fingerprint(before) != self.sources._fingerprint(
                    os.fstat(stream.fileno())
                ) or self.sources._fingerprint(before) != self.sources._fingerprint(path.stat()):
                    raise ProjectError("The selected base package changed while it was inspected.")
            for project in self.store.list_projects():
                if (
                    project.original is not None
                    and project.original.sha256 == digest
                    and self.store.verify_original(project.project_id).valid
                ):
                    return project.project_id
            project = self.store.create(f"Installation base · {path.stem}"[:80])
            imported = self.store.import_original(project.project_id, path)
            if imported.original is None or imported.original.sha256 != digest:
                raise ProjectError(
                    "The selected package changed during import. Select the intended file again."
                )
            return imported.project_id
        except ProjectError:
            raise
        except OSError as exc:
            raise ProjectError("The selected base package could not be preserved safely.") from exc

    def prepare(
        self,
        build_project_id: str,
        procedure_project_id: str,
        *,
        wipe: bool = False,
        reboot: bool = True,
    ) -> CandidateInstallationRecipe:
        # The creator chooses a base package once. Its exact understood recipe
        # supplies all roles/order; no shell script from that package is run.
        procedure = self.sources.prepare(procedure_project_id, wipe=wipe, reboot=reboot)
        if build_project_id == procedure_project_id:
            raise ProjectError(
                "Choose the rebuilt OTA project and its separate exact base installation package."
            )
        base = self.base.load(build_project_id)
        if base is not None:
            try:
                self.base.verify(base, procedure)
            except ProjectError:
                base = None
        if base is None:
            base = self.base.prepare(build_project_id, procedure)

        avb = self.avb.load(build_project_id)
        if avb is not None:
            try:
                self.avb.verify(avb, base)
            except ProjectError:
                avb = None
        if avb is None:
            avb = self.avb.prepare(build_project_id, base)
        return self._compose(build_project_id, procedure, base, avb)

    def verify(self, recipe: CandidateInstallationRecipe) -> CandidateInstallationRecipe:
        if type(recipe) is not CandidateInstallationRecipe:
            raise ProjectError("The reviewed rebuilt installation recipe is invalid.")
        try:
            valid_digest = _composition_digest(recipe) == recipe.recipe_digest
        except (TypeError, ValueError, RecursionError) as exc:
            raise ProjectError("The reviewed rebuilt installation recipe is malformed.") from exc
        if recipe.composition_version != self.COMPOSITION_VERSION or not valid_digest:
            raise ProjectError("The rebuilt installation review changed. Prepare a fresh review.")
        procedure = self.sources.prepare(
            recipe.procedure_project_id, wipe=recipe.wipe, reboot=recipe.reboot
        )
        base = self.base.load(recipe.project_id)
        avb = self.avb.load(recipe.project_id)
        if (
            base is None
            or avb is None
            or base.receipt_digest != recipe.base_receipt_digest
            or avb.receipt_digest != recipe.avb_receipt_digest
        ):
            raise ProjectError(
                "The reviewed base or AVB evidence is missing or changed. Prepare a fresh review."
            )
        self.base.verify(base, procedure)
        self.avb.verify(avb, base)
        current = self._compose(recipe.project_id, procedure, base, avb)
        if current != recipe:
            raise ProjectError(
                "The build, base package, image roles or installation choices changed. Prepare a fresh review."
            )
        return current

    def _compose(self, project_id, procedure, base, avb):
        preparation = self.built.prepare(project_id, candidate_choice="built")
        executor = LocalDeviceBuildExecutor(self.store, self.registry, self.tools, self.runner)
        build = executor.load_receipt(project_id)
        execution = executor.contracts.load(project_id)
        plan = RomBuildPlanner(self.store).load(project_id)
        project = self.store.get(project_id)
        packs = tuple(
            pack for pack in self.registry.packs if pack.pack_id == project.device_pack_id
        )
        if build is None or execution is None or plan is None or len(packs) != 1:
            raise ProjectError("The rebuilt ROM needs its current exact build outputs and plan.")
        pack = packs[0]
        contract = pack.build_contract
        signing = self.signing.load_receipt(project_id) if self.signing is not None else None
        assembly = (
            self.release.load_signed_assembly(project_id, build=build, signing=signing)
            if build is not None and signing is not None
            else None
        )
        if (
            contract is None
            or base.build_project_id != project_id
            or avb.project_id != project_id
            or base.source_sha256 != preparation.source_sha256
            or avb.source_sha256 != preparation.source_sha256
            or base.pack_sha256 != pack.sha256
            or base.contract_id != contract.contract_id
            or base.procedure_project_id != procedure.project_id
            or base.procedure_source_sha256 != procedure.source_sha256
            or base.procedure_recipe_digest != procedure.recipe_digest
            or base.script_sha256 != procedure.script_sha256
            or avb.base_receipt_digest != base.receipt_digest
            or avb.pack_sha256 != pack.sha256
            or avb.contract_digest != base.contract_digest
            or avb.build_receipt_digest != build.receipt_digest
            or build.plan_digest != execution.plan_digest
            or execution.source_archive_sha256 != preparation.source_sha256
            or execution.source_payload_sha256 != base.payload_sha256
            or execution.workspace_tree_sha256 != plan.tree_sha256
        ):
            raise ProjectError(
                "The build, AVB and base-image evidence do not describe one exact ROM."
            )
        if (
            type(signing) is not OfflineSigningReceipt
            or type(assembly) is not SignedAssemblyReceipt
            or signing.project_id != project_id
            or signing.pack_id != pack.pack_id
            or signing.pack_sha256 != pack.sha256
            or signing.contract_id != contract.contract_id
            or signing.local_build_receipt_digest != build.receipt_digest
            or assembly.project_id != project_id
            or assembly.build_receipt_digest != build.receipt_digest
            or assembly.signing_receipt_digest != signing.receipt_digest
        ):
            raise ProjectError(
                "The exact offline-signed artifacts and signed final super assembly are required."
            )
        if (
            base.execution_authority != "none"
            or base.phone_changed is not False
            or avb.execution_authority != "none"
            or avb.phone_changed is not False
            or avb.oem_trusted is not False
            or set(contract.allowed_outputs) != {f"{role}.img" for role in self.OUTPUT_ROLES}
            or len(contract.allowed_outputs) != len(self.OUTPUT_ROLES)
            or tuple(rule.name for rule in contract.partitions if rule.mode == "rebuild")
            != ("product",)
        ):
            raise ProjectError(
                "This build contract has no supported complete candidate composition."
            )
        if (
            procedure.expected_product.casefold() not in preparation.expected_products
            or procedure.expected_manufacturer.casefold() not in preparation.expected_manufacturers
        ):
            raise ProjectError("The rebuilt ROM and base procedure identify different devices.")

        outputs = {image.name: image for image in preparation.images}
        if set(outputs) != {f"{role}.img" for role in self.OUTPUT_ROLES} or len(outputs) != len(
            preparation.images
        ):
            raise ProjectError("The rebuilt image roles are missing, unexpected or ambiguous.")
        output_root = self.store.working_root / project_id / "build-candidates" / build.plan_id
        if any(image.path != output_root / name for name, image in outputs.items()):
            raise ProjectError("A rebuilt image is outside its exact versioned build role.")
        if (
            outputs["super.img"].sha256 != avb.candidate_super_sha256
            or outputs["vbmeta_system.img"].sha256 != avb.candidate_vbmeta_system_sha256
            or outputs["product.img"].sha256 != avb.product_sha256
        ):
            raise ProjectError(
                "The rebuilt images differ from the verified AVB/build relationships."
            )

        signed = {artifact.name: artifact for artifact in signing.artifacts}
        if set(signed) != {"product.img", "vbmeta_system.img"} or len(signed) != len(
            signing.artifacts
        ):
            raise ProjectError("The final signed artifact roles are missing or ambiguous.")
        product = signed["product.img"]
        child = signed["vbmeta_system.img"]
        signed_paths = {item.name: PurePosixPath(item.path) for item in signing.artifacts}
        signed_root = (
            "projects",
            project_id,
            "signing-evidence",
            signing.request_digest[:16],
        )
        assembly_path = PurePosixPath(assembly.super_path)
        if any(
            len(path.parts) != 5
            or path.parts[:4] != signed_root
            or path.name != name
            for name, path in signed_paths.items()
        ) or (
            len(assembly_path.parts) != 5
            or assembly_path.parts[:3] != ("working_roms", project_id, "signed-assembly")
            or not assembly_path.parts[3].startswith(signing.receipt_digest[:16])
            or assembly_path.name != "super.img"
        ):
            raise ProjectError("The final signed artifact paths are not their sealed roles.")
        signed_inputs = tuple(item for item in assembly.inputs if item.signed)
        if (
            len(signed_inputs) != 1
            or signed_inputs[0].partition != "product"
            or signed_inputs[0].source_path != product.path
            or signed_inputs[0].sha256 != product.sha256
            or signed_inputs[0].size_bytes != product.size_bytes
            or assembly.super_size_bytes != contract.super_size_bytes
        ):
            raise ProjectError(
                "The signed final super does not contain the exact signed product artifact."
            )
        final_outputs = {
            "product.img": ProjectFlashImage(
                self.store.workspace / product.path,
                product.name,
                product.sha256,
                product.size_bytes,
            ),
            "vbmeta_system.img": ProjectFlashImage(
                self.store.workspace / child.path,
                child.name,
                child.sha256,
                child.size_bytes,
            ),
            "super.img": ProjectFlashImage(
                self.store.workspace / assembly.super_path,
                "super.img",
                assembly.super_sha256,
                assembly.super_size_bytes,
            ),
        }
        for name, output in final_outputs.items():
            self._rebuilt_image(output, f"images/{name}", self.store.workspace)

        comparisons = {row.member: row for row in base.comparisons}
        images: list[SourceInstallImage] = []
        origins: list[CandidateImageOrigin] = []
        seen_roles: set[str] = set()
        for original in procedure.images:
            role = PurePosixPath(original.member).stem
            if role in self.REBUILT_ROLES:
                if role in seen_roles:
                    raise ProjectError("The base procedure duplicates a rebuilt image role.")
                output = final_outputs[f"{role}.img"]
                rebuilt = self._rebuilt_image(output, original.member, self.store.workspace)
                if role == "super" and (
                    rebuilt.expanded_size_bytes != contract.super_size_bytes
                    or original.expanded_size_bytes != contract.super_size_bytes
                ):
                    raise ProjectError(
                        "The rebuilt and base super images have different device geometry."
                    )
                images.append(rebuilt)
                origins.append(
                    CandidateImageOrigin(
                        original.member,
                        "signed-final",
                        output.path.relative_to(self.store.workspace).as_posix(),
                    )
                )
                seen_roles.add(role)
            else:
                comparison = comparisons.pop(original.member, None)
                if (
                    comparison is None
                    or comparison.partition != role
                    or comparison.sha256 != original.sha256
                    or comparison.size_bytes != original.size_bytes
                    or original.expanded_size_bytes != original.size_bytes
                ):
                    raise ProjectError(f"The unchanged {role} image lacks exact OTA base identity.")
                if role == "vbmeta" and (
                    original.sha256 != avb.root_sha256
                    or original.sha256 != contract.top_level_vbmeta_sha256
                ):
                    raise ProjectError(
                        "The original top-level AVB image does not match the exact build base."
                    )
                images.append(original)
                origins.append(CandidateImageOrigin(original.member, "base-package", ""))
        if (
            seen_roles != set(self.REBUILT_ROLES)
            or comparisons
            or len(images) != 50
            or len({image.member for image in images}) != 50
        ):
            raise ProjectError(
                "The complete two-rebuilt/48-base installation mapping is incomplete."
            )
        values = {
            name: getattr(procedure, name) for name in SourceInstallationRecipe.__dataclass_fields__
        }
        values.update(
            project_id=project_id,
            source_sha256=preparation.source_sha256,
            recipe_digest="",
            label="Rebuilt ROM · complete local experimental installation",
            images=tuple(images),
            warnings=tuple(dict.fromkeys((*self.WARNINGS, *avb.warnings, *procedure.warnings))),
        )
        recipe = CandidateInstallationRecipe(
            **values,
            composition_version=self.COMPOSITION_VERSION,
            procedure_project_id=procedure.project_id,
            procedure_source_sha256=procedure.source_sha256,
            procedure_recipe_digest=procedure.recipe_digest,
            base_receipt_digest=base.receipt_digest,
            build_receipt_digest=build.receipt_digest,
            build_plan_digest=execution.plan_digest,
            build_pack_sha256=execution.pack_sha256,
            build_recipe_digest=plan.recipe_digest,
            build_toolchain_digest=build.toolchain_manifest_digest,
            avb_receipt_digest=avb.receipt_digest,
            signing_receipt_digest=signing.receipt_digest,
            signed_assembly_receipt_digest=assembly.receipt_digest,
            origins=tuple(origins),
        )
        return replace(recipe, recipe_digest=_composition_digest(recipe))

    def _rebuilt_image(self, output, member, root):
        path = self.built._contained(output.path, root)
        try:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, "rb") as stream:
                before = os.fstat(stream.fileno())
                if (
                    not stat.S_ISREG(before.st_mode)
                    or not 0 < before.st_size <= self.sources.MAX_MEMBER_BYTES
                    or before.st_size != output.size_bytes
                ):
                    raise ProjectError(
                        "A rebuilt installation image is missing, changed or oversized."
                    )
                digest, expanded = _hash_stream(
                    stream,
                    before.st_size,
                    image=True,
                    maximum_expanded=self.sources.MAX_EXPANDED_BYTES,
                )
                if (
                    digest != output.sha256
                    or self.sources._fingerprint(before)
                    != self.sources._fingerprint(os.fstat(stream.fileno()))
                    or self.sources._fingerprint(before) != self.sources._fingerprint(path.stat())
                    or self.built._contained(path, root) != path
                ):
                    raise ProjectError("A rebuilt installation image changed during verification.")
        except ProjectError:
            raise
        except OSError as exc:
            raise ProjectError("A rebuilt installation image could not be read safely.") from exc
        return SourceInstallImage(member, digest, output.size_bytes, expanded)


def candidate_composition_payload(recipe: CandidateInstallationRecipe) -> dict:
    """Canonical private history payload, without machine-specific absolute paths.

    The procedure archive is bound by its immutable source/project identity.
    Live verification additionally compares the actual contained archive path;
    reopening historical results needs neither that path nor its current bytes.
    """
    payload = asdict(recipe)
    payload.pop("recipe_digest")
    payload.pop("archive_path")
    return payload


def _composition_digest(recipe: CandidateInstallationRecipe) -> str:
    return hashlib.sha256(
        json.dumps(
            candidate_composition_payload(recipe),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
