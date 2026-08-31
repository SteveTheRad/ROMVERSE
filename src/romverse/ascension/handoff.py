from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from romverse.ascension.binding import AscensionSourceBindingService
from romverse.ascension.models import AscensionMethod
from romverse.ascension.preparation import RootPatchPreparationService
from romverse.ascension.releases import OfficialRootReleaseService
from romverse.core.privacy import WorkspacePrivacy
from romverse.device.apk_install import (
    ApkInstallPlan,
    ApkInstallRequest,
    ApkInstallService,
    create_install_plan,
    install_succeeded,
)
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.registry import DevicePackRegistry
from romverse.guardian.approval import ApprovalStore
from romverse.guardian.gateway import ExecutionGateway
from romverse.guardian.models import GuardianDeniedError, OperationClass, OperationRequest
from romverse.guardian.planning import (
    CheckStatus,
    GuardianPreflight,
    OperationManifest,
    PlannedStep,
    Precondition,
    PreflightAssessment,
)
from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    ensure_private_directory,
    read_json_object,
)
from romverse.infrastructure.process import CommandResult
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore


@dataclass(frozen=True, slots=True)
class RootPatchHandoffPlan:
    project_id: str
    method: AscensionMethod
    capsule_digest: str
    device_serial: str
    device_key: str
    device_codename: str
    manager_path: str
    input_image_path: str
    input_image_sha256: str
    remote_input_path: str
    apk_plan: ApkInstallPlan
    transfer_manifest: OperationManifest
    transfer_assessment: PreflightAssessment

    @property
    def transfer_digest(self) -> str:
        return self.transfer_assessment.manifest_digest

    @property
    def safety_ready(self) -> bool:
        return self.apk_plan.safety_ready and not self.transfer_assessment.execution_locked


@dataclass(frozen=True, slots=True)
class RootPatchHandoffReceipt:
    schema_version: int
    receipt_id: str
    project_id: str
    method: AscensionMethod
    created_at: str
    capsule_digest: str
    device_key: str
    device_codename: str
    manager_sha256: str
    input_image_sha256: str
    remote_input_path: str
    manager_installed: bool
    input_transferred: bool
    root_applied: bool
    image_flashed: bool
    phone_changed: bool
    receipt_digest: str


class RootPatchHandoffService:
    """Install and stage verified patch inputs after explicit Guardian approval.

    This service cannot patch, root, reboot, unlock, or flash a device. It performs only
    two reversible preparation actions: installing the verified manager APK and copying
    the pristine source-bound image into Downloads.
    """

    FORMAT = "romverse.root-patch-handoff"
    SCHEMA_VERSION = 1
    RECEIPT_NAME = "latest-phone-handoff.romverse"
    REMOTE_PATTERN = re.compile(r"/sdcard/Download/ROMVERSE-[0-9a-f]{8}-[A-Za-z0-9_.-]{1,96}\.img")
    MAX_RECEIPT_BYTES = 256 * 1024
    MAX_TEXT = 8192

    def __init__(
        self,
        store: RomProjectStore,
        adb_executable: Path,
        gateway: ExecutionGateway,
        approvals: ApprovalStore,
        registry: DevicePackRegistry | None = None,
        release_service: OfficialRootReleaseService | None = None,
    ) -> None:
        self.store = store
        self.adb_executable = adb_executable.resolve()
        self.gateway = gateway
        self.approvals = approvals
        self.registry = registry or DevicePackRegistry(())
        self.release_service = release_service or OfficialRootReleaseService(store.workspace)

    def plan(
        self,
        project_id: str,
        method: AscensionMethod,
        device: AndroidDevice,
    ) -> RootPatchHandoffPlan:
        if device.state is not DeviceState.DEVICE or not device.serial:
            raise ProjectError("Ascension handoff requires one authorized ADB device")
        project = self.store.get(project_id)
        if project.original is None:
            raise ProjectError("Ascension handoff requires a protected firmware source")
        binding = AscensionSourceBindingService(self.store, self.registry).resolve(project_id)
        if not binding.matches(device):
            raise ProjectError(
                "Connected device codename does not exactly match the authoritative protected-firmware binding"
            )
        capsule = RootPatchPreparationService(self.store).load(project_id, method)
        if capsule is None:
            raise ProjectError("The verified source-bound patch capsule is unavailable")
        manager = self._workspace_file(capsule.manager_path)
        image = self._workspace_file(capsule.input_image_path)
        verified = self.release_service.load_verified(method)
        if verified is None:
            raise ProjectError(
                "Ascension handoff requires a freshly signature-verified official Manager"
            )
        release, _vault_path = verified
        if not RootPatchPreparationService.matches_release(capsule, release):
            raise ProjectError(
                "Ascension capsule does not match the current verified official Manager"
            )
        self.release_service.verify_artifact(release, manager)
        device_key = WorkspacePrivacy(self.store.workspace).pseudonym(device.serial)
        apk_plan = create_install_plan(
            ApkInstallRequest(
                str(manager),
                device.serial,
                battery_percent=device.battery_percent,
                device_free_bytes=device.storage.available_bytes,
            ),
            device_key,
        )
        safe_name = self._safe_image_name(Path(capsule.input_image_path).stem)
        remote = f"/sdcard/Download/ROMVERSE-{capsule.input_image_sha256[:8]}-{safe_name}.img"
        manifest = OperationManifest(
            1,
            uuid4().hex,
            datetime.now(UTC).isoformat(),
            "Ascension phone patch handoff",
            "ascension_patch_input_transfer",
            device_key,
            (
                Precondition(
                    "capsule",
                    "Source-bound patch capsule verified",
                    CheckStatus.PASS,
                    f"Capsule {capsule.capsule_digest}; image SHA-256 {capsule.input_image_sha256}",
                ),
                Precondition(
                    "device",
                    "Protected source matches the authorized phone",
                    CheckStatus.PASS,
                    f"Exact codename {device.codename}",
                ),
                Precondition(
                    "battery",
                    "Battery is at least 20%",
                    CheckStatus.PASS
                    if device.battery_percent is not None and device.battery_percent >= 20
                    else CheckStatus.FAIL,
                    f"Observed {device.battery_percent}%"
                    if device.battery_percent is not None
                    else "Battery evidence unavailable",
                ),
            ),
            (
                PlannedStep(
                    "transfer",
                    "Copy pristine patch image to Downloads",
                    "Stage the exact source-bound image for user-controlled manager patching",
                    OperationClass.STATE_CHANGING,
                    f"Creates {remote}; does not patch or flash a partition",
                    True,
                ),
            ),
        )
        assessment = GuardianPreflight().assess(manifest, execution_supported=True)
        return RootPatchHandoffPlan(
            project_id,
            method,
            capsule.capsule_digest,
            device.serial,
            device_key,
            device.codename,
            str(manager),
            str(image),
            capsule.input_image_sha256,
            remote,
            apk_plan,
            manifest,
            assessment,
        )

    def execute(
        self,
        plan: RootPatchHandoffPlan,
        progress=None,
    ) -> RootPatchHandoffReceipt:
        if not plan.safety_ready:
            raise GuardianDeniedError("Ascension handoff failed required safety evidence")
        capsule = RootPatchPreparationService(self.store).load(plan.project_id, plan.method)
        if capsule is None or capsule.capsule_digest != plan.capsule_digest:
            raise GuardianDeniedError("Ascension capsule changed after review")
        manager = self._workspace_file(capsule.manager_path)
        try:
            planned_manager = self._workspace_file(plan.manager_path)
            requested_manager = self._workspace_file(plan.apk_plan.request.apk_path)
        except ProjectError as exc:
            raise GuardianDeniedError("Official Manager plan changed after review") from exc
        if manager != planned_manager or manager != requested_manager:
            raise GuardianDeniedError("Official Manager plan changed after review")
        verified = self.release_service.load_verified(plan.method)
        if verified is None:
            raise GuardianDeniedError(
                "Official Manager signature could not be revalidated before phone handoff"
            )
        release, _vault_path = verified
        if (
            not RootPatchPreparationService.matches_release(capsule, release)
            or plan.apk_plan.inspection.sha256 != release.asset.sha256
        ):
            raise GuardianDeniedError("Official Manager identity changed after review")
        try:
            self.release_service.verify_artifact(release, manager)
        except ProjectError as exc:
            raise GuardianDeniedError(
                "Official Manager signature could not be revalidated before phone handoff"
            ) from exc
        image = self._workspace_file(capsule.input_image_path)
        if _sha256(image) != plan.input_image_sha256:
            raise GuardianDeniedError("Ascension input image changed after review")
        if not self.approvals.is_approved(plan.apk_plan.digest, plan.device_key):
            raise GuardianDeniedError("Manager installation has not been explicitly approved")
        if not self.approvals.is_approved(plan.transfer_digest, plan.device_key):
            raise GuardianDeniedError("Patch-image transfer has not been explicitly approved")
        install = ApkInstallService(
            self.adb_executable,
            self.gateway,
            self.approvals,
        ).install(plan.apk_plan)
        if not install_succeeded(install):
            raise ProjectError(_result_error("Official manager installation failed", install))
        transfer_request = OperationRequest(
            operation_id="ascension.transfer_input",
            category=OperationClass.STATE_CHANGING,
            executable=str(self.adb_executable),
            arguments=(
                "-s",
                plan.device_serial,
                "push",
                str(image),
                plan.remote_input_path,
            ),
            purpose="Transfer the reviewed pristine Ascension patch image",
            target=plan.device_serial,
            approval_digest=plan.transfer_digest,
            approval_target=plan.device_key,
        )
        transfer = self.gateway.execute(transfer_request, timeout=300)
        if not transfer.ok:
            raise ProjectError(_result_error("Patch-image transfer failed", transfer))
        payload: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "receipt_id": uuid4().hex,
            "project_id": plan.project_id,
            "method": plan.method.value,
            "created_at": datetime.now(UTC).isoformat(),
            "capsule_digest": plan.capsule_digest,
            "device_key": plan.device_key,
            "device_codename": plan.device_codename,
            "manager_sha256": plan.apk_plan.inspection.sha256,
            "input_image_sha256": plan.input_image_sha256,
            "remote_input_path": plan.remote_input_path,
            "manager_installed": True,
            "input_transferred": True,
            "root_applied": False,
            "image_flashed": False,
            "phone_changed": True,
        }
        digest = _digest(payload)
        receipt = RootPatchHandoffReceipt(
            self.SCHEMA_VERSION,
            str(payload["receipt_id"]),
            plan.project_id,
            plan.method,
            str(payload["created_at"]),
            plan.capsule_digest,
            plan.device_key,
            plan.device_codename,
            str(payload["manager_sha256"]),
            plan.input_image_sha256,
            plan.remote_input_path,
            True,
            True,
            False,
            False,
            True,
            digest,
        )
        root = self.store.projects_root / plan.project_id / "ascension" / "handoff"
        document = {"format": self.FORMAT, **asdict(receipt), "method": plan.method.value}
        try:
            ensure_private_directory(root, boundary=self.store.workspace)
            for path in (
                root / self.RECEIPT_NAME,
                root / f"phone-handoff-{receipt.receipt_id[:12]}.romverse",
            ):
                atomic_write_json(
                    path,
                    document,
                    boundary=self.store.workspace,
                    maximum_bytes=self.MAX_RECEIPT_BYTES,
                )
        except LocalStoreError as exc:
            raise ProjectError(
                "Phone preparation finished, but its private Ascension evidence could not be stored safely; ROMVERSE will not claim the handoff is verified"
            ) from exc
        return receipt

    def load(
        self,
        project_id: str,
        method: AscensionMethod,
    ) -> RootPatchHandoffReceipt | None:
        return load_root_patch_handoff(self.store, project_id, method)

    def _workspace_file(self, relative: str) -> Path:
        candidate = Path(relative)
        unresolved = candidate if candidate.is_absolute() else self.store.workspace / candidate
        if unresolved.is_symlink():
            raise ProjectError("Ascension handoff artifact cannot be a symbolic link")
        try:
            resolved = unresolved.resolve(strict=True)
        except OSError as exc:
            raise ProjectError("Ascension handoff artifact is unavailable") from exc
        if not resolved.is_file() or not resolved.is_relative_to(self.store.workspace.resolve()):
            raise ProjectError("Ascension handoff artifact escaped the workspace")
        return resolved

    @staticmethod
    def _safe_image_name(value: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-.")[:96]
        return cleaned or "boot"


def load_root_patch_handoff(
    store: RomProjectStore,
    project_id: str,
    method: AscensionMethod,
) -> RootPatchHandoffReceipt | None:
    """Read and revalidate handoff evidence without constructing an execution service."""

    path = (
        store.projects_root
        / project_id
        / "ascension"
        / "handoff"
        / RootPatchHandoffService.RECEIPT_NAME
    )
    try:
        data = read_json_object(
            path,
            boundary=store.workspace,
            maximum_bytes=RootPatchHandoffService.MAX_RECEIPT_BYTES,
        )
        if (
            set(data) != {"format", *(field.name for field in fields(RootPatchHandoffReceipt))}
            or data.pop("format") != RootPatchHandoffService.FORMAT
            or not isinstance(data.get("method"), str)
        ):
            return None
        data["method"] = AscensionMethod(data["method"])
        receipt = RootPatchHandoffReceipt(**data)
    except (LocalStoreError, ValueError, TypeError, KeyError):
        return None
    unsigned = asdict(receipt)
    unsigned.pop("receipt_digest")
    unsigned["method"] = receipt.method.value
    capsule = RootPatchPreparationService(store).load(project_id, method)
    if (
        not _valid_receipt_shape(receipt, RootPatchHandoffService.MAX_TEXT)
        or receipt.schema_version != RootPatchHandoffService.SCHEMA_VERSION
        or receipt.project_id != project_id
        or receipt.method is not method
        or capsule is None
        or receipt.capsule_digest != capsule.capsule_digest
        or receipt.manager_sha256 != capsule.manager_sha256
        or receipt.input_image_sha256 != capsule.input_image_sha256
        or not receipt.manager_installed
        or not receipt.input_transferred
        or receipt.root_applied
        or receipt.image_flashed
        or not receipt.phone_changed
        or not RootPatchHandoffService.REMOTE_PATTERN.fullmatch(receipt.remote_input_path)
        or receipt.receipt_digest != _digest(unsigned)
    ):
        return None
    return receipt


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _safe_text(value: object, maximum: int) -> bool:
    return bool(isinstance(value, str) and value and len(value) <= maximum and "\x00" not in value)


def _sha256_value(value: object) -> bool:
    return bool(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value))


def _valid_receipt_shape(receipt: RootPatchHandoffReceipt, maximum_text: int) -> bool:
    return bool(
        type(receipt.schema_version) is int
        and _safe_text(receipt.receipt_id, maximum_text)
        and _safe_text(receipt.project_id, maximum_text)
        and isinstance(receipt.method, AscensionMethod)
        and _safe_text(receipt.created_at, maximum_text)
        and _sha256_value(receipt.capsule_digest)
        and _safe_text(receipt.device_key, maximum_text)
        and _safe_text(receipt.device_codename, maximum_text)
        and _sha256_value(receipt.manager_sha256)
        and _sha256_value(receipt.input_image_sha256)
        and _safe_text(receipt.remote_input_path, maximum_text)
        and type(receipt.manager_installed) is bool
        and type(receipt.input_transferred) is bool
        and type(receipt.root_applied) is bool
        and type(receipt.image_flashed) is bool
        and type(receipt.phone_changed) is bool
        and _sha256_value(receipt.receipt_digest)
    )


def _result_error(prefix: str, result: CommandResult) -> str:
    detail = (result.stderr or result.stdout).strip().replace("\n", " ")[:300]
    return f"{prefix}: {detail or f'ADB returned {result.returncode}'}"
