from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from romverse.ascension.handoff import (
    RootPatchHandoffReceipt,
    RootPatchHandoffService,
    load_root_patch_handoff,
)
from romverse.ascension.models import AscensionMethod, OfficialRootRelease
from romverse.ascension.releases import OfficialRootReleaseService
from romverse.core.privacy import WorkspacePrivacy
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.registry import DevicePackRegistry
from romverse.guardian.approval import ApprovalStore
from romverse.guardian.ascension_manager import (
    installed_manager_path,
    manager_launch_arguments,
    manager_path_arguments,
)
from romverse.guardian.gateway import ExecutionGateway
from romverse.guardian.models import GuardianDeniedError, OperationClass, OperationRequest
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
class RootManagerPathPlan:
    project_id: str
    method: AscensionMethod
    handoff_digest: str
    device_serial: str
    device_key: str
    package_name: str
    expected_signer_sha256: str
    manager_sha256: str
    approval_digest: str


@dataclass(frozen=True, slots=True)
class RootManagerLaunchPlan:
    project_id: str
    method: AscensionMethod
    handoff_digest: str
    device_serial: str
    device_key: str
    package_name: str
    expected_signer_sha256: str
    manager_sha256: str
    installed_apk_path: str
    local_verification_path: str
    path_approval_digest: str
    approval_digest: str


@dataclass(frozen=True, slots=True)
class RootManagerLaunchReceipt:
    schema_version: int
    receipt_id: str
    project_id: str
    method: AscensionMethod
    created_at: str
    handoff_digest: str
    device_key: str
    package_name: str
    signer_sha256: str
    installed_apk_sha256: str
    installed_package_verified: bool
    manager_opened: bool
    operation_scope: str
    execution_authority: str
    root_applied: bool
    image_flashed: bool
    phone_changed: bool
    receipt_digest: str


class RootManagerLaunchService:
    """Verify the installed official manager before an open-only ADB handoff."""

    FORMAT = "romverse.root-manager-launch"
    SCHEMA_VERSION = 1
    RECEIPT_NAME = "latest-manager-launch.romverse"
    OPERATION_SCOPE = "verified-manager-open-only"
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

    def plan_path(
        self,
        project_id: str,
        method: AscensionMethod,
        device: AndroidDevice,
    ) -> RootManagerPathPlan:
        if device.state is not DeviceState.DEVICE or not device.serial:
            raise ProjectError("Opening the Ascension Manager requires one authorized ADB device")
        handoff, release = self._context(project_id, method)
        device_key = WorkspacePrivacy(self.store.workspace).pseudonym(device.serial)
        if handoff.device_key != device_key or handoff.device_codename != device.codename:
            raise ProjectError(
                "The connected phone does not match the verified Ascension Manager handoff"
            )
        package_name = self.release_service.OFFICIAL_PACKAGES[method]
        signer = self.release_service.OFFICIAL_SIGNERS[method]
        unsigned = {
            "schema_version": self.SCHEMA_VERSION,
            "operation": "resolve-installed-manager-path",
            "project_id": project_id,
            "method": method.value,
            "handoff_digest": handoff.receipt_digest,
            "device_key": device_key,
            "package_name": package_name,
            "expected_signer_sha256": signer,
            "manager_sha256": release.asset.sha256,
        }
        return RootManagerPathPlan(
            project_id,
            method,
            handoff.receipt_digest,
            device.serial,
            device_key,
            package_name,
            signer,
            release.asset.sha256,
            _digest(unsigned),
        )

    def resolve_path(self, plan: RootManagerPathPlan) -> RootManagerLaunchPlan:
        self._validate_path_plan(plan)
        if not self.approvals.is_approved(plan.approval_digest, plan.device_key):
            raise GuardianDeniedError(
                "Installed Ascension Manager lookup has not been explicitly approved"
            )
        installed_path = self._query_installed_path(plan)
        local = (
            self._launch_root(plan.project_id)
            / f".manager-inspection-{uuid4().hex}"
            / "installed-manager.apk"
        )
        unsigned = {
            "schema_version": self.SCHEMA_VERSION,
            "operation": "verify-and-open-installed-manager",
            "project_id": plan.project_id,
            "method": plan.method.value,
            "handoff_digest": plan.handoff_digest,
            "device_key": plan.device_key,
            "package_name": plan.package_name,
            "expected_signer_sha256": plan.expected_signer_sha256,
            "manager_sha256": plan.manager_sha256,
            "installed_apk_path": installed_path,
            "local_verification_path": local.relative_to(self.store.workspace).as_posix(),
        }
        return RootManagerLaunchPlan(
            plan.project_id,
            plan.method,
            plan.handoff_digest,
            plan.device_serial,
            plan.device_key,
            plan.package_name,
            plan.expected_signer_sha256,
            plan.manager_sha256,
            installed_path,
            str(local),
            plan.approval_digest,
            _digest(unsigned),
        )

    def execute(
        self,
        plan: RootManagerLaunchPlan,
        progress=None,
    ) -> RootManagerLaunchReceipt:
        self._validate_launch_plan(plan)
        if not self.approvals.is_approved(plan.approval_digest, plan.device_key):
            raise GuardianDeniedError(
                "Installed Ascension Manager verification and launch were not explicitly approved"
            )
        path_plan = self._path_plan_from_launch(plan)
        if not self.approvals.is_approved(path_plan.approval_digest, path_plan.device_key):
            raise GuardianDeniedError("The approved Manager path lookup expired before launch")
        current_path = self._query_installed_path(path_plan)
        if current_path != plan.installed_apk_path:
            raise GuardianDeniedError("The installed Ascension Manager path changed after review")
        local = self._verification_path(plan)
        inspection_root = local.parent
        try:
            launch_root = self._launch_root(plan.project_id)
            ensure_private_directory(launch_root, boundary=self.store.workspace)
            if os.path.lexists(inspection_root):
                raise LocalStoreError("Manager inspection directory already exists")
            inspection_root.mkdir(mode=0o700)
            ensure_private_directory(inspection_root, boundary=self.store.workspace)
        except (LocalStoreError, OSError) as exc:
            raise ProjectError(
                "ROMVERSE could not create isolated Manager verification storage"
            ) from exc
        try:
            pull = self.gateway.execute(
                OperationRequest(
                    operation_id="ascension.pull_manager",
                    category=OperationClass.READ_ONLY,
                    executable=str(self.adb_executable),
                    arguments=(
                        "-s",
                        plan.device_serial,
                        "pull",
                        plan.installed_apk_path,
                        str(local),
                    ),
                    purpose="Copy the installed official root Manager for signature verification",
                    target=plan.device_serial,
                    approval_digest=plan.approval_digest,
                    approval_target=plan.device_key,
                ),
                timeout=180,
            )
            if not pull.ok:
                raise ProjectError(
                    _result_error("Installed Manager verification copy failed", pull)
                )
            handoff, release = self._context(plan.project_id, plan.method)
            if handoff.receipt_digest != plan.handoff_digest:
                raise GuardianDeniedError("Ascension Manager handoff changed during verification")
            inspection = self.release_service.verify_artifact(release, local)
            if (
                inspection.sha256 != plan.manager_sha256
                or inspection.signer_sha256 != plan.expected_signer_sha256
                or inspection.package_name not in {"", plan.package_name}
            ):
                raise GuardianDeniedError(
                    "The installed Ascension Manager does not match the approved official package"
                )
            launched = self.gateway.execute(
                OperationRequest(
                    operation_id="ascension.launch_manager",
                    category=OperationClass.STATE_CHANGING,
                    executable=str(self.adb_executable),
                    arguments=manager_launch_arguments(
                        plan.device_serial,
                        plan.package_name,
                    ),
                    purpose="Open the signature-verified official root Manager",
                    target=plan.device_serial,
                    approval_digest=plan.approval_digest,
                    approval_target=plan.device_key,
                ),
                timeout=30,
            )
            launch_output = f"{launched.stdout}\n{launched.stderr}"
            if not launched.ok or "Events injected: 1" not in launch_output:
                raise ProjectError(_result_error("Verified Manager did not open", launched))
        finally:
            shutil.rmtree(inspection_root, ignore_errors=True)
        payload: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "receipt_id": uuid4().hex,
            "project_id": plan.project_id,
            "method": plan.method.value,
            "created_at": datetime.now(UTC).isoformat(),
            "handoff_digest": plan.handoff_digest,
            "device_key": plan.device_key,
            "package_name": plan.package_name,
            "signer_sha256": plan.expected_signer_sha256,
            "installed_apk_sha256": plan.manager_sha256,
            "installed_package_verified": True,
            "manager_opened": True,
            "operation_scope": self.OPERATION_SCOPE,
            "execution_authority": "none",
            "root_applied": False,
            "image_flashed": False,
            "phone_changed": True,
        }
        receipt_fields = dict(payload)
        receipt_fields["method"] = plan.method
        receipt = RootManagerLaunchReceipt(
            **receipt_fields,
            receipt_digest=_digest(payload),
        )
        destination = self._launch_root(plan.project_id) / self.RECEIPT_NAME
        document = {
            "format": self.FORMAT,
            **asdict(receipt),
            "method": receipt.method.value,
        }
        try:
            ensure_private_directory(destination.parent, boundary=self.store.workspace)
            for path in (
                destination,
                destination.parent / f"manager-launch-{receipt.receipt_id[:12]}.romverse",
            ):
                atomic_write_json(
                    path,
                    document,
                    boundary=self.store.workspace,
                    maximum_bytes=self.MAX_RECEIPT_BYTES,
                )
        except LocalStoreError as exc:
            raise ProjectError(
                "The verified Manager opened, but its private evidence could not be stored safely; ROMVERSE will not preserve this stage as complete"
            ) from exc
        return receipt

    def load(
        self,
        project_id: str,
        method: AscensionMethod,
    ) -> RootManagerLaunchReceipt | None:
        try:
            handoff, release = self._context(project_id, method)
        except ProjectError:
            return None
        return _load_root_manager_launch_receipt(
            self.store,
            self.release_service,
            project_id,
            method,
            handoff,
            release,
        )

    def _validate_path_plan(self, plan: RootManagerPathPlan) -> None:
        handoff, release = self._context(plan.project_id, plan.method)
        expected = self.plan_path(
            plan.project_id,
            plan.method,
            AndroidDevice(
                plan.device_serial,
                DeviceState.DEVICE,
                codename=handoff.device_codename,
            ),
        )
        if plan != expected or release.asset.sha256 != plan.manager_sha256:
            raise GuardianDeniedError("Ascension Manager lookup plan changed after review")

    def _validate_launch_plan(self, plan: RootManagerLaunchPlan) -> None:
        handoff, release = self._context(plan.project_id, plan.method)
        local = self._verification_path(plan)
        unsigned = {
            "schema_version": self.SCHEMA_VERSION,
            "operation": "verify-and-open-installed-manager",
            "project_id": plan.project_id,
            "method": plan.method.value,
            "handoff_digest": plan.handoff_digest,
            "device_key": plan.device_key,
            "package_name": plan.package_name,
            "expected_signer_sha256": plan.expected_signer_sha256,
            "manager_sha256": plan.manager_sha256,
            "installed_apk_path": plan.installed_apk_path,
            "local_verification_path": local.relative_to(self.store.workspace).as_posix(),
        }
        if (
            plan.handoff_digest != handoff.receipt_digest
            or plan.device_key != handoff.device_key
            or plan.package_name != self.release_service.OFFICIAL_PACKAGES[plan.method]
            or plan.expected_signer_sha256 != self.release_service.OFFICIAL_SIGNERS[plan.method]
            or plan.manager_sha256 != release.asset.sha256
            or not installed_manager_path(plan.installed_apk_path)
            or plan.approval_digest != _digest(unsigned)
        ):
            raise GuardianDeniedError("Ascension Manager launch plan changed after review")

    def _context(
        self,
        project_id: str,
        method: AscensionMethod,
    ) -> tuple[RootPatchHandoffReceipt, OfficialRootRelease]:
        handoff = RootPatchHandoffService(
            self.store,
            self.adb_executable,
            self.gateway,
            self.approvals,
            self.registry,
            self.release_service,
        ).load(project_id, method)
        if handoff is None:
            raise ProjectError("The verified Ascension phone handoff is unavailable")
        verified = self.release_service.load_verified(method)
        if verified is None:
            raise ProjectError("The official Ascension Manager could not be revalidated")
        release, _manager = verified
        if handoff.manager_sha256 != release.asset.sha256:
            raise ProjectError("The official Ascension Manager changed after phone handoff")
        return handoff, release

    def _query_installed_path(self, plan: RootManagerPathPlan) -> str:
        result = self.gateway.execute(
            OperationRequest(
                operation_id="ascension.manager_path",
                category=OperationClass.READ_ONLY,
                executable=str(self.adb_executable),
                arguments=manager_path_arguments(plan.device_serial, plan.package_name),
                purpose="Resolve the installed official root Manager package",
                target=plan.device_serial,
                approval_digest=plan.approval_digest,
                approval_target=plan.device_key,
            ),
            timeout=20,
        )
        if not result.ok:
            raise ProjectError(_result_error("Installed Ascension Manager was not found", result))
        lines = tuple(line.strip() for line in result.stdout.splitlines() if line.strip())
        paths = tuple(
            line.removeprefix("package:") for line in lines if line.startswith("package:")
        )
        if len(lines) != 1 or len(paths) != 1 or not installed_manager_path(paths[0]):
            raise ProjectError(
                "Android did not report one bounded base APK for the official Ascension Manager"
            )
        return paths[0]

    def _path_plan_from_launch(self, plan: RootManagerLaunchPlan) -> RootManagerPathPlan:
        return RootManagerPathPlan(
            plan.project_id,
            plan.method,
            plan.handoff_digest,
            plan.device_serial,
            plan.device_key,
            plan.package_name,
            plan.expected_signer_sha256,
            plan.manager_sha256,
            plan.path_approval_digest,
        )

    def _verification_path(self, plan: RootManagerLaunchPlan) -> Path:
        candidate = Path(plan.local_verification_path)
        root = self._launch_root(plan.project_id).resolve()
        if (
            not candidate.is_absolute()
            or candidate.is_symlink()
            or candidate.parent.is_symlink()
            or candidate.name != "installed-manager.apk"
            or not candidate.parent.name.startswith(".manager-inspection-")
            or not candidate.parent.resolve().is_relative_to(root)
        ):
            raise GuardianDeniedError("Ascension Manager verification path is unsafe")
        return candidate

    def _launch_root(self, project_id: str) -> Path:
        return self.store.projects_root / project_id / "ascension" / "manager-launch"


def load_root_manager_launch(
    store: RomProjectStore,
    release_service: OfficialRootReleaseService,
    project_id: str,
    method: AscensionMethod,
) -> RootManagerLaunchReceipt | None:
    """Read and revalidate an open-only Manager receipt without an ADB gateway."""

    handoff = load_root_patch_handoff(store, project_id, method)
    verified = release_service.load_verified(method)
    if handoff is None or verified is None:
        return None
    release, _manager = verified
    return _load_root_manager_launch_receipt(
        store,
        release_service,
        project_id,
        method,
        handoff,
        release,
    )


def _load_root_manager_launch_receipt(
    store: RomProjectStore,
    release_service: OfficialRootReleaseService,
    project_id: str,
    method: AscensionMethod,
    handoff: RootPatchHandoffReceipt,
    release: OfficialRootRelease,
) -> RootManagerLaunchReceipt | None:
    """Validate one receipt against already revalidated handoff and release evidence."""

    path = (
        store.projects_root
        / project_id
        / "ascension"
        / "manager-launch"
        / RootManagerLaunchService.RECEIPT_NAME
    )
    try:
        data = read_json_object(
            path,
            boundary=store.workspace,
            maximum_bytes=RootManagerLaunchService.MAX_RECEIPT_BYTES,
        )
        if (
            set(data) != {"format", *(field.name for field in fields(RootManagerLaunchReceipt))}
            or data.pop("format") != RootManagerLaunchService.FORMAT
            or not isinstance(data.get("method"), str)
        ):
            return None
        data["method"] = AscensionMethod(data["method"])
        receipt = RootManagerLaunchReceipt(**data)
    except (LocalStoreError, ValueError, TypeError, KeyError):
        return None
    unsigned = asdict(receipt)
    unsigned.pop("receipt_digest")
    unsigned["method"] = receipt.method.value
    if (
        not _valid_receipt_shape(receipt, RootManagerLaunchService.MAX_TEXT)
        or receipt.schema_version != RootManagerLaunchService.SCHEMA_VERSION
        or receipt.project_id != project_id
        or receipt.method is not method
        or receipt.handoff_digest != handoff.receipt_digest
        or receipt.device_key != handoff.device_key
        or receipt.package_name != release_service.OFFICIAL_PACKAGES[method]
        or receipt.signer_sha256 != release_service.OFFICIAL_SIGNERS[method]
        or receipt.installed_apk_sha256 != release.asset.sha256
        or not receipt.installed_package_verified
        or not receipt.manager_opened
        or receipt.operation_scope != RootManagerLaunchService.OPERATION_SCOPE
        or receipt.execution_authority != "none"
        or receipt.root_applied
        or receipt.image_flashed
        or not receipt.phone_changed
        or receipt.receipt_digest != _digest(unsigned)
    ):
        return None
    return receipt


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _safe_text(value: object, maximum: int) -> bool:
    return bool(isinstance(value, str) and value and len(value) <= maximum and "\x00" not in value)


def _sha256_value(value: object) -> bool:
    return bool(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value))


def _valid_receipt_shape(receipt: RootManagerLaunchReceipt, maximum_text: int) -> bool:
    return bool(
        type(receipt.schema_version) is int
        and _safe_text(receipt.receipt_id, maximum_text)
        and _safe_text(receipt.project_id, maximum_text)
        and isinstance(receipt.method, AscensionMethod)
        and _safe_text(receipt.created_at, maximum_text)
        and _sha256_value(receipt.handoff_digest)
        and _safe_text(receipt.device_key, maximum_text)
        and _safe_text(receipt.package_name, maximum_text)
        and _sha256_value(receipt.signer_sha256)
        and _sha256_value(receipt.installed_apk_sha256)
        and type(receipt.installed_package_verified) is bool
        and type(receipt.manager_opened) is bool
        and _safe_text(receipt.operation_scope, maximum_text)
        and _safe_text(receipt.execution_authority, maximum_text)
        and type(receipt.root_applied) is bool
        and type(receipt.image_flashed) is bool
        and type(receipt.phone_changed) is bool
        and _sha256_value(receipt.receipt_digest)
    )


def _result_error(prefix: str, result: CommandResult) -> str:
    detail = (result.stderr or result.stdout).strip().replace("\n", " ")[:300]
    return f"{prefix}: {detail or f'ADB returned {result.returncode}'}"
