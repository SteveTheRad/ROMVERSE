"""Source-bound, manually mapped local image subsets; never a full-ROM installer.

The existing project receipts establish which bytes were selected. They do not
certify a partition mapping, OTA installation, public release, or physical recovery.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import stat
import tarfile
import threading
import zipfile
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from romverse.device.models import AndroidDevice
from romverse.device_packs.registry import DevicePackRegistry
from romverse.guardian.local_flash import LocalFlashError, LocalFlashSelection, LocalFlashService
from romverse.infrastructure.local_store import (
    atomic_write_json,
    exclusive_create_json,
    read_json_object,
)
from romverse.rom.build_execution import LocalDeviceBuildExecutor
from romverse.rom.builds import RomBuildPlanner
from romverse.rom.models import ProjectError
from romverse.rom.payloads import PayloadService
from romverse.rom.projects import RomProjectStore
from romverse.rom.recipes import RecipeStore
from romverse.rom.source_blueprint import FastbootSourceBlueprint
from romverse.rom.source_identity import identify_firmware_source
from romverse.rom.source_intelligence import (
    FirmwareSourceIntelligenceService,
    OtaPayloadBlueprint,
    PartitionBundleBlueprint,
)


@dataclass(frozen=True, slots=True)
class ProjectFlashImage:
    path: Path
    name: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class ProjectFlashPreparation:
    project_id: str
    source_sha256: str
    preparation_digest: str
    candidate_label: str
    images: tuple[ProjectFlashImage, ...]
    warnings: tuple[str, ...]
    expected_products: tuple[str, ...]
    expected_codenames: tuple[str, ...]
    candidate_choice: str
    evidence_digest: str
    expected_manufacturers: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProjectFlashOutcome:
    project_id: str
    source_sha256: str
    state: str
    summary: str
    selected_image_count: int
    receipt_path: Path
    boot_status: str = "unverified"
    historical: bool = True
    current_artifact_bytes_verified: bool = False
    boot_receipt_path: Path | None = None


class _NoCommands:
    def run(self, *_args, **_kwargs):
        raise ProjectError("Project image preparation cannot execute external tools.")


class ProjectFlashPreparationService:
    MAX_ARCHIVE_MEMBERS = 100_000
    WARNINGS = (
        "MANUAL LOCAL SUBSET: you choose every image, partition and write order. No image-to-partition mapping is selected automatically.",
        "This is not a complete ROM/firmware or OTA installer. A successful subset write does not prove a complete upgrade, a bootable ROM, compatible data, AVB compatibility or physical recovery.",
        "Images inside super and separate vbmeta images can depend on one another. This inventory does not prove the required complete sequence, slots or modes.",
        "No automatic slot activation, wipe, AVB-disable flags, bootloader unlock or relock is included. Keep your own user-data backup and recovery route available.",
        "This project-local review is not production Device Pack certification. Image readback and subsystem health remain unverified.",
    )

    def __init__(self, store: RomProjectStore, registry: DevicePackRegistry):
        self.store = store
        self.registry = registry
        self.runner = _NoCommands()

    def prepare(
        self, project_id: str, *, candidate_choice: str = "built"
    ) -> ProjectFlashPreparation:
        if candidate_choice not in {"built", "protected"}:
            raise ProjectError("Choose built images or protected-source images explicitly.")
        project = self.store.get(project_id)
        if project.original is None or not self.store.verify_original(project_id).valid:
            raise ProjectError(
                "The protected source is missing or changed. Verify/import the intended firmware again."
            )
        source = self.store.original_path(project_id)
        self._contained(source, self.store.originals_root)
        blueprint = FirmwareSourceIntelligenceService(self.store, (), self.runner).load(project_id)
        pack = next(
            (item for item in self.registry.packs if item.pack_id == project.device_pack_id), None
        )
        exact_pack = bool(
            pack
            and pack.build_contract
            and pack.build_contract.source.archive_sha256 == project.original.sha256
        )
        identities = tuple(
            dict.fromkeys(
                value.casefold()
                for value in (
                    getattr(blueprint, "codename", ""),
                    identify_firmware_source(project.original.original_name).codename,
                )
                if value
            )
        )
        if len(identities) > 1:
            raise ProjectError(
                "The source filename and saved source identity contradict one another. Re-identify this firmware."
            )
        manufacturers = tuple(
            sorted(
                {
                    _manufacturer(value)
                    for value in (
                        getattr(blueprint, "manufacturer", ""),
                        identify_firmware_source(project.original.original_name).manufacturer,
                    )
                    if value
                }
            )
        )
        if len(manufacturers) > 1:
            raise ProjectError(
                "The recorded source manufacturers contradict one another. Re-identify the firmware."
            )
        if not manufacturers and exact_pack and pack is not None:
            manufacturers = tuple(
                sorted({_manufacturer(value) for value in pack.manufacturers if value})
            )
        products = (
            tuple(
                sorted(
                    value.casefold()
                    for value in pack.product_patterns
                    if LocalFlashService.PARTITION.fullmatch(value)
                )
            )
            if exact_pack and pack is not None
            else ()
        )
        if identities and products and identities[0] not in products:
            raise ProjectError(
                "The source codename contradicts the exact selected build pack. Re-identify the source/pack."
            )
        codenames = identities or products
        if candidate_choice == "built":
            if not exact_pack:
                raise ProjectError(
                    "Built-image selection needs its current exact source-bound build pack. No protected-source fallback was selected."
                )
            receipt = LocalDeviceBuildExecutor(
                self.store, self.registry, (), self.runner
            ).load_receipt(project_id)
            if receipt is None:
                raise ProjectError(
                    "No current verified local build outputs exist. Complete the build, or explicitly choose protected-source images."
                )
            planner = RomBuildPlanner(self.store)
            plan = planner.load(project_id)
            execution = LocalDeviceBuildExecutor(
                self.store, self.registry, (), self.runner
            ).contracts.load(project_id)
            recipe = RecipeStore().load(self.store.projects_root / project_id)
            if (
                plan is None
                or execution is None
                or execution.workspace_tree_sha256 != plan.tree_sha256
                or not planner.verify_tree(project_id).valid
                or plan.recipe_digest != (recipe.digest() if recipe is not None else "")
            ):
                raise ProjectError(
                    "The project tree or recipe changed since this build. Build fresh outputs before selecting them."
                )
            root = self.store.working_root / project_id / "build-candidates" / receipt.plan_id
            images = tuple(
                self._image(item.path, item.sha256, item.size_bytes, root)
                for item in receipt.outputs
                if Path(item.name).suffix.casefold() == ".img"
            )
            evidence = _digest(
                {
                    "build_receipt": receipt.receipt_digest,
                    "plan": execution.plan_digest,
                    "pack": pack.sha256,
                    "recipe": plan.recipe_digest,
                }
            )
            label = "Verified local build images · manual subset"
        else:
            if blueprint is None:
                raise ProjectError(
                    "No current protected-source image inventory exists. Inspect the source and extract its images first."
                )
            tree = self.store.working_root / project_id / "tree"
            member_images: list[ProjectFlashImage] = []
            extra_evidence = ""
            if isinstance(blueprint, PartitionBundleBlueprint):
                images = tuple(
                    self._image(item.path, item.sha256, item.size_bytes, tree)
                    for item in blueprint.images
                )
                member_images.extend(images)
            elif isinstance(blueprint, FastbootSourceBlueprint):
                image = self._image(
                    blueprint.source_super_path,
                    blueprint.source_super_sha256,
                    blueprint.source_super_size_bytes,
                    tree,
                )
                member_images.append(image)
                for name, digest in blueprint.vbmeta_images:
                    path = image.path.parent / name
                    member_images.append(self._image(path, digest, path.stat().st_size, tree))
                images = tuple(member_images)
            elif isinstance(blueprint, OtaPayloadBlueprint):
                payload = PayloadService(
                    self.store, Path("unused-payload-dumper"), self.runner
                ).load(project_id)
                if (
                    payload is None
                    or payload.schema_version != PayloadService.SCHEMA_VERSION
                    or payload.source_original_sha256 != project.original.sha256
                    or payload.payload_sha256 != blueprint.payload_sha256
                ):
                    raise ProjectError(
                        "No current source-bound payload extraction manifest exists. Rescan and extract the desired OTA partition images first."
                    )
                payload_path = self._checked_bytes(
                    payload.payload_path, payload.payload_sha256, payload.payload_size, tree
                )
                member_images.append(
                    ProjectFlashImage(
                        payload_path,
                        payload_path.name,
                        payload.payload_sha256,
                        payload.payload_size,
                    )
                )
                root = self.store.working_root / project_id / "partitions"
                images = tuple(
                    self._image(item.extracted_path, item.sha256, item.actual_bytes, root)
                    for item in payload.partitions
                    if item.extracted_path
                )
                extra_evidence = payload.record_digest
            else:
                raise ProjectError("This source adapter has no supported local image inventory.")
            self._verify_archive_members(source, tree, tuple(member_images))
            evidence = _digest({"blueprint": blueprint.blueprint_digest, "payload": extra_evidence})
            label = "Protected-source images · manual subset"
        if not images:
            raise ProjectError(
                "The selected evidence contains no extracted .img files. Extract images first; a payload or archive itself cannot be flashed as an image."
            )
        if len(images) > 256 or len({item.path for item in images}) != len(images):
            raise ProjectError("The selected image inventory is too large or ambiguous.")
        preparation = ProjectFlashPreparation(
            project_id,
            project.original.sha256,
            "",
            label,
            images,
            self.WARNINGS,
            products or codenames,
            codenames,
            candidate_choice,
            evidence,
            manufacturers,
        )
        return replace(preparation, preparation_digest=self._preparation_digest(preparation))

    def verify(
        self, preparation: ProjectFlashPreparation, device: AndroidDevice, selections=None
    ) -> None:
        if (
            not isinstance(preparation, ProjectFlashPreparation)
            or self._preparation_digest(preparation) != preparation.preparation_digest
        ):
            raise ProjectError("The project image review changed. Prepare it again.")
        current = self.prepare(
            preparation.project_id, candidate_choice=preparation.candidate_choice
        )
        if current != preparation:
            raise ProjectError(
                "The project source, selected receipt, image inventory or source identity changed. Prepare a fresh review."
            )
        self._device(preparation, device)
        if selections is not None:
            if not isinstance(selections, tuple) or not selections:
                raise ProjectError(
                    "Choose an explicit image and partition mapping for this manual subset."
                )
            allowed = {item.path for item in preparation.images}
            for item in selections:
                if not isinstance(
                    item, LocalFlashSelection
                ) or not LocalFlashService.PARTITION.fullmatch(item.partition):
                    raise ProjectError(
                        "Every selected image needs an explicit valid partition name."
                    )
                if self._contained(item.image_path, self.store.workspace) not in allowed:
                    raise ProjectError(
                        "The selected file is not part of this reviewed project image inventory."
                    )

    @staticmethod
    def _device(preparation, device):
        if not isinstance(device, AndroidDevice) or not LocalFlashService.SERIAL.fullmatch(
            device.serial
        ):
            raise ProjectError("Select and identify the exact connected phone first.")
        if (
            device.manufacturer
            and preparation.expected_manufacturers
            and _manufacturer(device.manufacturer) not in preparation.expected_manufacturers
        ):
            raise ProjectError(
                "The connected phone manufacturer conflicts with the protected source."
            )
        expected = set(preparation.expected_codenames) | set(preparation.expected_products)
        if not expected:
            raise ProjectError(
                "The protected source has no exact known device identity. Resolve its codename/product before project-bound flashing."
            )
        if device.codename and preparation.expected_codenames:
            if device.codename.casefold() not in preparation.expected_codenames:
                raise ProjectError(
                    "The connected device codename conflicts with the protected source. Different-device images cannot proceed."
                )
        elif not device.product or device.product.casefold() not in expected:
            raise ProjectError(
                "The connected phone product is unknown or differs from the protected source. Refresh Device DNA."
            )

    def load_latest(self, project_id: str) -> ProjectFlashOutcome | None:
        """Bounded historical display only; never a fresh-byte check or write authority."""
        project = self.store.get(project_id)
        if project.original is None:
            return None
        root = self.store.workspace / "guardian" / "project-local"
        try:
            paths = []
            for index, path in enumerate(root.iterdir()):
                if index >= 1024:
                    return None
                if path.suffix == ".json":
                    if path.is_symlink():
                        return None
                    paths.append(path)
            paths.sort(key=lambda item: item.stat().st_mtime_ns, reverse=True)
        except OSError:
            return None
        for path in paths[:128]:
            try:
                record = read_json_object(
                    path, boundary=self.store.workspace, maximum_bytes=256 * 1024
                )
                if (
                    record.get("project_id") != project_id
                    or record.get("source_sha256") != project.original.sha256
                    or record.get("operation_kind") != "image-subset"
                ):
                    continue
                if (
                    record.get("format") != "romverse.project-local-operation"
                    or record.get("project_id") != project_id
                    or record.get("source_sha256") != project.original.sha256
                    or record.get("operation_kind") != "image-subset"
                    or record.get("state") not in {"completed", "failed", "cancelled", "rejected"}
                    or record.get("record_digest")
                    != _digest(
                        {key: value for key, value in record.items() if key != "record_digest"}
                    )
                    or any(
                        record.get(key) is not False
                        for key in (
                            "full_firmware_install",
                            "production_certified",
                            "boot_verified",
                            "readback_verified",
                        )
                    )
                    or type(record.get("selected_image_count")) is not int
                    or not 1 <= record["selected_image_count"] <= LocalFlashService.MAX_WRITES
                ):
                    return None
                current = self._recorded_evidence(project_id, record.get("candidate_choice"))
                if current is None or record.get("evidence_digest") != current:
                    return None
                relative = Path(record["child_receipt_path"])
                if (
                    relative.is_absolute()
                    or ".." in relative.parts
                    or relative.parts[:2] != ("guardian", "local-flash")
                ):
                    return None
                child = read_json_object(
                    self.store.workspace / relative,
                    boundary=self.store.workspace,
                    maximum_bytes=1024 * 1024,
                )
                if (
                    child.get("record_digest") != record.get("child_record_digest")
                    or child.get("record_digest")
                    != _digest(
                        {key: value for key, value in child.items() if key != "record_digest"}
                    )
                    or child.get("plan_digest") != record.get("local_plan_digest")
                    or child.get("device_key") != record.get("device_key")
                    or child.get("state") != record.get("state")
                    or len(child.get("writes", ())) != record["selected_image_count"]
                ):
                    return None
                boot_status, boot_path = self._linked_boot_history(record)
                return ProjectFlashOutcome(
                    project_id,
                    project.original.sha256,
                    record["state"],
                    "Previous manual image subset: " + str(child.get("summary", ""))[:600],
                    record["selected_image_count"],
                    path,
                    boot_status=boot_status,
                    boot_receipt_path=boot_path,
                )
            except (OSError, ValueError, TypeError, KeyError, ProjectError):
                return None
        return None

    def _linked_boot_history(self, parent):
        """A linked historical report, not fresh boot verification or write authority."""
        root = self.store.workspace / "guardian" / "local-boot"
        try:
            paths = []
            for index, path in enumerate(root.iterdir()):
                if index >= 1024:
                    return "See separate boot-check record", None
                if path.suffix == ".json":
                    if path.is_symlink():
                        return "See separate boot-check record", None
                    paths.append(path)
            paths.sort(key=lambda item: item.stat().st_mtime_ns, reverse=True)
        except OSError:
            return "No linked boot-check record", None
        binding = {
            "relative_path": parent["child_receipt_path"],
            "record_digest": parent["child_record_digest"],
            "plan_digest": parent["local_plan_digest"],
            "device_key": parent["device_key"],
        }
        fields = {
            "format",
            "schema_version",
            "session_id",
            "device_key",
            "started_at",
            "updated_at",
            "adb_sha256",
            "flash_binding",
            "status",
            "summary",
            "sample_count",
            "elapsed_seconds",
            "boot_observed",
            "terminal",
            "failure_kind",
            "stable_window_required_seconds",
            "minimum_sample_spacing_seconds",
            "restarts_observed",
            "samples",
            "execution_authority",
            "phone_changed",
            "readback_verified",
            "subsystems_verified",
            "guardian_execution_certified",
            "production_certified",
            "record_digest",
        }
        labels = {
            "stable": "Historical Android boot observed · subsystem tests pending",
            "waiting": "Historical boot check: waiting",
            "settling": "Historical boot check: settling",
            "attention": "Historical boot check: needs attention",
            "cancelled": "Historical boot check: stopped",
        }
        for path in paths[:128]:
            try:
                record = read_json_object(
                    path, boundary=self.store.workspace, maximum_bytes=512 * 1024
                )
                if (
                    record.get("device_key") != parent["device_key"]
                    or record.get("flash_binding") != binding
                ):
                    continue
                if (
                    set(record) != fields
                    or record["format"] != "romverse.local-boot-observation"
                    or type(record["schema_version"]) is not int
                    or record["schema_version"] != 1
                    or record["session_id"] != path.stem
                    or record["status"] not in labels
                    or record["record_digest"]
                    != _digest(
                        {key: value for key, value in record.items() if key != "record_digest"}
                    )
                    or record["execution_authority"] != "none"
                    or any(
                        record[key] is not False
                        for key in (
                            "phone_changed",
                            "readback_verified",
                            "subsystems_verified",
                            "guardian_execution_certified",
                            "production_certified",
                        )
                    )
                    or type(record["sample_count"]) is not int
                    or not isinstance(record["samples"], list)
                    or record["sample_count"] != len(record["samples"])
                    or not 0 <= record["sample_count"] <= 256
                    or type(record["boot_observed"]) is not bool
                    or type(record["terminal"]) is not bool
                    or (
                        record["status"] == "stable"
                        and (
                            record["terminal"] is not True
                            or record["boot_observed"] is not True
                            or record["failure_kind"]
                            or record["sample_count"] < 3
                        )
                    )
                ):
                    return "See separate boot-check record", path
                return labels[record["status"]], path
            except (OSError, ValueError, TypeError, KeyError, ProjectError):
                return "See separate boot-check record", None
        return "No linked boot-check record", None

    def _recorded_evidence(self, project_id, choice):
        if choice == "built":
            executor = LocalDeviceBuildExecutor(self.store, self.registry, (), self.runner)
            receipt = executor.load_receipt(project_id)
            execution = executor.contracts.load(project_id)
            plan = RomBuildPlanner(self.store).load(project_id)
            project = self.store.get(project_id)
            pack = next(
                (item for item in self.registry.packs if item.pack_id == project.device_pack_id),
                None,
            )
            if receipt is None or execution is None or plan is None or pack is None:
                return None
            return _digest(
                {
                    "build_receipt": receipt.receipt_digest,
                    "plan": execution.plan_digest,
                    "pack": pack.sha256,
                    "recipe": plan.recipe_digest,
                }
            )
        if choice == "protected":
            blueprint = FirmwareSourceIntelligenceService(self.store, (), self.runner).load(
                project_id
            )
            if blueprint is None:
                return None
            payload_digest = ""
            if isinstance(blueprint, OtaPayloadBlueprint):
                payload = PayloadService(
                    self.store, Path("unused-payload-dumper"), self.runner
                ).load(project_id)
                if payload is None or payload.payload_sha256 != blueprint.payload_sha256:
                    return None
                payload_digest = payload.record_digest
            return _digest({"blueprint": blueprint.blueprint_digest, "payload": payload_digest})
        return None

    def _image(self, path, digest, size, root):
        actual = self._checked_bytes(path, digest, size, root)
        if actual.suffix.casefold() != ".img":
            raise ProjectError(
                "Only extracted .img artifacts may enter the project image workflow."
            )
        return ProjectFlashImage(actual, actual.name, digest, size)

    def _checked_bytes(self, path, digest, size, root):
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(value not in "0123456789abcdef" for value in digest)
            or type(size) is not int
            or size <= 0
        ):
            raise ProjectError("The selected artifact has invalid saved hash or size evidence.")
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.store.workspace / candidate
        actual = self._contained(candidate, root)
        current_hash, current_size, _ = LocalFlashService._hash_file(actual)
        if current_size != size or not hmac.compare_digest(current_hash, digest):
            raise ProjectError(
                f"{actual.name} bytes differ from the selected source/build receipt. Prepare fresh verified evidence."
            )
        return actual

    @staticmethod
    def _contained(path, root):
        if not isinstance(path, Path):
            raise ProjectError("A selected artifact needs a contained regular file path.")
        try:
            actual = LocalFlashService._regular_path(path)
            boundary = root.resolve(strict=True)
        except (OSError, LocalFlashError) as exc:
            raise ProjectError("A selected artifact is missing, linked or unsafe.") from exc
        if not actual.is_relative_to(boundary):
            raise ProjectError(
                "A selected artifact is outside its exact project source/output directory."
            )
        return actual

    @staticmethod
    def _preparation_digest(preparation):
        content = asdict(preparation)
        content.pop("preparation_digest")
        return _digest(content)

    def _verify_archive_members(self, archive_path, tree, images):
        wanted = {item.path.relative_to(tree.resolve()).as_posix(): item for item in images}
        found = set()

        def check(name, size, stream):
            if name in found:
                raise ProjectError(
                    "The protected archive contains duplicate selected image members."
                )
            found.add(name)
            item = wanted[name]
            if size != item.size_bytes or stream is None:
                raise ProjectError("A selected image differs from its protected archive member.")
            digest = hashlib.sha256()
            count = 0
            while chunk := stream.read(min(4 * 1024 * 1024, size - count + 1)):
                count += len(chunk)
                if count > size:
                    raise ProjectError("The protected archive member exceeds its declared size.")
                digest.update(chunk)
            if count != size or digest.hexdigest() != item.sha256:
                raise ProjectError(
                    "A selected image does not match the original protected archive bytes."
                )

        try:
            if zipfile.is_zipfile(archive_path):
                with zipfile.ZipFile(archive_path) as archive:
                    members = archive.infolist()
                    if len(members) > self.MAX_ARCHIVE_MEMBERS:
                        raise ProjectError(
                            "The protected archive has too many members to verify safely."
                        )
                    for member in members:
                        name = str(PurePosixPath(member.filename))
                        if name not in wanted:
                            continue
                        if member.is_dir() or stat.S_ISLNK(member.external_attr >> 16):
                            raise ProjectError(
                                "A selected protected image member is not a regular file."
                            )
                        with archive.open(member) as stream:
                            check(name, member.file_size, stream)
            else:
                with tarfile.open(archive_path, "r:*") as archive:
                    for count, member in enumerate(archive, 1):
                        if count > self.MAX_ARCHIVE_MEMBERS:
                            raise ProjectError(
                                "The protected archive has too many members to verify safely."
                            )
                        name = str(PurePosixPath(member.name))
                        if name not in wanted:
                            continue
                        if not member.isfile():
                            raise ProjectError(
                                "A selected protected image member is not a regular file."
                            )
                        stream = archive.extractfile(member)
                        if stream is None:
                            raise ProjectError("The protected image member could not be read.")
                        with stream:
                            check(name, member.size, stream)
        except (OSError, ValueError, zipfile.BadZipFile, tarfile.TarError) as exc:
            raise ProjectError(
                "Protected image membership could not be verified. Use a supported intact ZIP/TAR firmware source."
            ) from exc
        if found != set(wanted):
            raise ProjectError(
                "A selected image is not an exact member of the protected archive. Re-extract the original source."
            )


class _BoundProjectService:
    KIND = "image-subset"

    def __init__(self, preparer, preparation, local_service):
        flash = getattr(local_service, "flash_service", local_service)
        if getattr(flash, "workspace", None) != preparer.store.workspace:
            raise ProjectError(
                "The local operation service belongs to a different project workspace."
            )
        self.preparer = preparer
        self.preparation = preparation
        self.local_service = local_service
        self._reviews = {}
        self._review_lock = threading.Lock()
        self.project_receipt_path: Path | None = None

    def __getattr__(self, name):
        return getattr(self.local_service, name)

    def _bind(self, plan, device, selections=None):
        digest = _digest(
            {
                "preparation": self.preparation.preparation_digest,
                "operation": plan.plan_digest,
                "kind": self.KIND,
            }
        )
        bound = replace(
            plan,
            plan_digest=digest,
            warnings=tuple(dict.fromkeys((*self.preparation.warnings, *plan.warnings))),
        )
        with self._review_lock:
            if len(self._reviews) >= 128:
                self._reviews.pop(next(iter(self._reviews)))
            self._reviews[digest] = (bound, plan, device, selections)
        return bound

    def execute(self, plan, *, accepted_digest, risk_accepted, should_cancel=None, progress=None):
        if risk_accepted is not True or accepted_digest != plan.plan_digest:
            raise LocalFlashError(
                "Confirm the exact project-bound manual operation and accept its risks first."
            )
        with self._review_lock:
            stored = self._reviews.get(plan.plan_digest)
            if stored is None or stored[0] is not plan:
                raise LocalFlashError(
                    "The project-bound review changed, belongs to another service or was already used."
                )
            self._reviews.pop(plan.plan_digest)
        _, original, device, selections = stored
        self.preparer.verify(self.preparation, device, selections)
        workspace = self.preparer.store.workspace
        path = workspace / "guardian" / "project-local" / f"{original.plan_id}.json"
        self.project_receipt_path = path
        record = {
            "format": "romverse.project-local-operation",
            "schema_version": 1,
            "project_id": self.preparation.project_id,
            "source_sha256": self.preparation.source_sha256,
            "preparation_digest": self.preparation.preparation_digest,
            "evidence_digest": self.preparation.evidence_digest,
            "candidate_choice": self.preparation.candidate_choice,
            "operation_kind": self.KIND,
            "reviewed_plan_digest": plan.plan_digest,
            "local_plan_digest": original.plan_digest,
            "device_key": original.device_key,
            "created_at": _now(),
            "state": "delegation-pending",
            "consent": "explicit-project-bound-manual-subset",
            "full_firmware_install": False,
            "production_certified": False,
            "boot_verified": False,
            "readback_verified": False,
            "child_receipt_path": "",
            "child_record_digest": "",
            "selected_image_count": len(original.writes) if self.KIND == "image-subset" else 0,
        }
        self._save(path, record, exclusive=True)
        try:
            result = self.local_service.execute(
                original,
                accepted_digest=original.plan_digest,
                risk_accepted=True,
                should_cancel=should_cancel,
                progress=progress,
            )
        except BaseException:
            record.update(state="delegation-interrupted", completed_at=_now())
            self._save(path, record)
            raise
        child = read_json_object(result.receipt_path, boundary=workspace, maximum_bytes=1024 * 1024)
        child_digest = child.get("record_digest")
        if child_digest != _digest(
            {key: value for key, value in child.items() if key != "record_digest"}
        ):
            raise ProjectError(
                "The underlying operation receipt could not be verified; the phone outcome remains unconfirmed."
            )
        record.update(
            state=result.state.value,
            completed_at=_now(),
            phone_change_attempted=result.phone_change_attempted,
            child_receipt_path=result.receipt_path.relative_to(workspace).as_posix(),
            child_record_digest=child_digest,
        )
        self._save(path, record)
        return result

    def _save(self, path, record, *, exclusive=False):
        payload = {**record, "record_digest": _digest(record)}
        writer = exclusive_create_json if exclusive else atomic_write_json
        writer(path, payload, boundary=self.preparer.store.workspace, maximum_bytes=256 * 1024)


class BoundProjectFlashService(_BoundProjectService):
    def inspect(self, device, selections):
        self.preparer.verify(self.preparation, device, selections)
        plan = self.local_service.inspect(device, selections)
        expected = {item.path: item for item in self.preparation.images}
        for write in plan.writes:
            image = expected.get(write.image_path)
            if image is None or (write.sha256, write.size_bytes) != (
                image.sha256,
                image.size_bytes,
            ):
                raise ProjectError(
                    "An image changed while the project-bound review was being prepared."
                )
        return self._bind(plan, device, selections)


class BoundProjectTransitionService(_BoundProjectService):
    KIND = "manual-mode-transition"

    def inspect(self, device, target):
        self.preparer.verify(self.preparation, device)
        return self._bind(self.local_service.inspect(device, target), device)


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _now():
    return datetime.now(UTC).isoformat()


def _manufacturer(value):
    name = value.strip().casefold()
    return {"redmi": "xiaomi", "poco": "xiaomi", "samsung electronics": "samsung"}.get(name, name)
