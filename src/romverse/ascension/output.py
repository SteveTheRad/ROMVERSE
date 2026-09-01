from __future__ import annotations

import hashlib
import json
import re
from contextlib import suppress
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from romverse.ascension.handoff import RootPatchHandoffReceipt, RootPatchHandoffService
from romverse.ascension.models import AscensionMethod
from romverse.ascension.preparation import PatchedImageReceipt, RootPatchPreparationService
from romverse.core.privacy import WorkspacePrivacy
from romverse.guardian.approval import ApprovalStore
from romverse.guardian.ascension_transfer import (
    ASCENSION_OUTPUT_LIST_COMMAND,
    ASCENSION_OUTPUT_NAME,
    ascension_output_list_digest,
    ascension_output_matches_method,
    ascension_output_pull_digest,
)
from romverse.guardian.gateway import ExecutionGateway
from romverse.guardian.models import OperationClass, OperationRequest
from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    ensure_private_directory,
    read_json_object,
)
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore


@dataclass(frozen=True, slots=True)
class PatchedOutputPlan:
    project_id: str
    method: AscensionMethod
    device_serial: str
    device_key: str
    remote_path: str
    local_path: str
    discovery_digest: str
    approval_digest: str


@dataclass(frozen=True, slots=True)
class PatchedOutputDiscovery:
    schema_version: int
    discovery_id: str
    project_id: str
    method: AscensionMethod
    created_at: str
    handoff_receipt_digest: str
    device_key: str
    state: str
    candidate_count: int
    candidate_refs: tuple[str, ...]
    candidate_set_digest: str
    recommended_name_ref: str
    truncated: bool
    data_scope: str
    source_directory: str
    ordering: str
    phone_changed: bool
    execution_authority: str
    receipt_digest: str


class RootPatchedOutputService:
    """Retrieve a user-created manager output and bind it to its exact source capsule."""

    DISCOVERY_FORMAT = "romverse.ascension-output-discovery"
    DISCOVERY_SCHEMA_VERSION = 1
    DISCOVERY_NAME = "latest-discovery.romverse"
    DISCOVERY_VALID_FOR = timedelta(minutes=10)
    MAX_SCAN_OUTPUT_BYTES = 256 * 1024
    MAX_CANDIDATES = 64
    MAX_RECEIPT_BYTES = 256 * 1024
    MAX_TEXT = 8192

    def __init__(
        self,
        store: RomProjectStore,
        adb_executable: Path,
        gateway: ExecutionGateway,
        approvals: ApprovalStore,
    ) -> None:
        self.store = store
        self.adb_executable = adb_executable.resolve()
        self.gateway = gateway
        self.approvals = approvals

    def list_digest(self, serial: str) -> str:
        return ascension_output_list_digest(serial)

    def find(self, project_id: str, method: AscensionMethod, serial: str) -> tuple[str, ...]:
        handoff, device_key = self._current_handoff(project_id, method, serial)
        digest = self.list_digest(serial)
        result = self.gateway.execute(
            OperationRequest(
                "ascension.list_outputs",
                OperationClass.READ_ONLY,
                str(self.adb_executable),
                ("-s", serial, *ASCENSION_OUTPUT_LIST_COMMAND),
                "List candidate patched boot images in the phone Downloads folder",
                serial,
                digest,
                device_key,
            ),
            timeout=20,
        )
        if not result.ok:
            raise ProjectError(_result_error("Phone Downloads scan failed", result))
        if len(result.stdout.encode("utf-8")) > self.MAX_SCAN_OUTPUT_BYTES:
            raise ProjectError(
                "Phone Downloads filename response exceeded the bounded Ascension scan limit"
            )
        names: list[str] = []
        seen: set[str] = set()
        truncated = False
        for line in result.stdout.splitlines():
            name = line.strip()
            if (
                name not in seen
                and ASCENSION_OUTPUT_NAME.fullmatch(name)
                and ascension_output_matches_method(name, method.value)
            ):
                seen.add(name)
                if len(names) < self.MAX_CANDIDATES:
                    names.append(name)
                else:
                    truncated = True
        self._record_discovery(
            project_id,
            method,
            handoff,
            device_key,
            tuple(names),
            truncated,
        )
        return tuple(names)

    def load_discovery(
        self,
        project_id: str,
        method: AscensionMethod,
        serial: str,
    ) -> PatchedOutputDiscovery | None:
        path = self._discovery_path(project_id, method)
        try:
            data = read_json_object(
                path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
            if (
                set(data) != {"format", *(field.name for field in fields(PatchedOutputDiscovery))}
                or data.pop("format") != self.DISCOVERY_FORMAT
                or not isinstance(data.get("method"), str)
                or not isinstance(data.get("candidate_refs"), list)
                or len(data["candidate_refs"]) > self.MAX_CANDIDATES
                or any(not _sha256_value(item) for item in data["candidate_refs"])
            ):
                return None
            data["method"] = AscensionMethod(data["method"])
            data["candidate_refs"] = tuple(data["candidate_refs"])
            receipt = PatchedOutputDiscovery(**data)
            handoff, device_key = self._current_handoff(project_id, method, serial)
            created_at = datetime.fromisoformat(receipt.created_at)
        except (
            LocalStoreError,
            ValueError,
            TypeError,
            KeyError,
            ProjectError,
        ):
            return None
        unsigned = asdict(receipt)
        unsigned.pop("receipt_digest")
        unsigned["method"] = receipt.method.value
        found = receipt.candidate_count > 0
        now = datetime.now(UTC)
        if (
            not _valid_discovery_shape(receipt, self.MAX_TEXT)
            or receipt.schema_version != self.DISCOVERY_SCHEMA_VERSION
            or not re.fullmatch(r"[0-9a-f]{32}", receipt.discovery_id)
            or receipt.project_id != project_id
            or receipt.method is not method
            or created_at.tzinfo is None
            or created_at > now + timedelta(minutes=1)
            or receipt.handoff_receipt_digest != handoff.receipt_digest
            or receipt.device_key != device_key
            or receipt.state != ("found" if found else "none")
            or isinstance(receipt.candidate_count, bool)
            or not isinstance(receipt.candidate_count, int)
            or receipt.candidate_count != len(receipt.candidate_refs)
            or not 0 <= receipt.candidate_count <= self.MAX_CANDIDATES
            or len(set(receipt.candidate_refs)) != len(receipt.candidate_refs)
            or any(not _sha256_value(value) for value in receipt.candidate_refs)
            or receipt.candidate_set_digest != _json_digest(receipt.candidate_refs)
            or receipt.recommended_name_ref
            != (receipt.candidate_refs[0] if receipt.candidate_refs else "")
            or not isinstance(receipt.truncated, bool)
            or (receipt.truncated and receipt.candidate_count != self.MAX_CANDIDATES)
            or receipt.data_scope != "filenames-only"
            or receipt.source_directory != "/sdcard/Download"
            or receipt.ordering != "modified-descending"
            or receipt.phone_changed
            or receipt.execution_authority != "none"
            or receipt.receipt_digest != _json_digest(unsigned)
        ):
            return None
        return receipt

    def plan(
        self,
        project_id: str,
        method: AscensionMethod,
        serial: str,
        name: str,
    ) -> PatchedOutputPlan:
        device_key = self._require_handoff(project_id, method, serial)
        if not ASCENSION_OUTPUT_NAME.fullmatch(name):
            raise ProjectError("Patched output name is outside the supported manager format")
        if not ascension_output_matches_method(name, method.value):
            raise ProjectError(
                f"Patched output does not match the selected {method.display_name} route"
            )
        discovery = self._active_discovery(project_id, method, serial)
        if _name_ref(name) not in discovery.candidate_refs:
            raise ProjectError(
                "Selected patched output was not present in the latest approved phone scan"
            )
        root = self.store.projects_root / project_id / "ascension" / "phone-output"
        try:
            ensure_private_directory(root, boundary=self.store.workspace)
        except LocalStoreError as exc:
            raise ProjectError("Patched-image staging could not be prepared safely") from exc
        local = root / name
        if local.exists() or local.is_symlink():
            raise ProjectError("A phone-output staging file already exists; retry after cleanup")
        remote = f"/sdcard/Download/{name}"
        digest = ascension_output_pull_digest(serial, remote, local)
        return PatchedOutputPlan(
            project_id,
            method,
            serial,
            device_key,
            remote,
            str(local),
            discovery.receipt_digest,
            digest,
        )

    def retrieve_and_import(
        self,
        plan: PatchedOutputPlan,
        progress=None,
    ) -> PatchedImageReceipt:
        local, expected = self._validate_plan(plan)
        if not self.approvals.is_approved(expected, plan.device_key):
            raise ProjectError("Patched-image retrieval has not been explicitly approved")
        result = self.gateway.execute(
            OperationRequest(
                "ascension.pull_output",
                OperationClass.READ_ONLY,
                str(self.adb_executable),
                ("-s", plan.device_serial, "pull", plan.remote_path, str(local)),
                "Retrieve the selected manager-patched image for local verification",
                plan.device_serial,
                expected,
                plan.device_key,
            ),
            timeout=300,
        )
        if not result.ok:
            local.unlink(missing_ok=True)
            raise ProjectError(_result_error("Patched-image retrieval failed", result))
        try:
            receipt = RootPatchPreparationService(self.store).import_patched(
                plan.project_id,
                plan.method,
                local,
                progress,
            )
        finally:
            local.unlink(missing_ok=True)
            with suppress(OSError):
                local.parent.rmdir()
        return receipt

    def _validate_plan(self, plan: PatchedOutputPlan) -> tuple[Path, str]:
        device_key = self._require_handoff(
            plan.project_id,
            plan.method,
            plan.device_serial,
        )
        if plan.device_key != device_key:
            raise ProjectError("Patched-image retrieval target changed after planning")
        prefix = "/sdcard/Download/"
        name = plan.remote_path.removeprefix(prefix)
        if (
            not plan.remote_path.startswith(prefix)
            or not ASCENSION_OUTPUT_NAME.fullmatch(name)
            or not ascension_output_matches_method(name, plan.method.value)
        ):
            raise ProjectError(
                f"Patched output does not match the selected {plan.method.display_name} route"
            )
        discovery = self._active_discovery(
            plan.project_id,
            plan.method,
            plan.device_serial,
        )
        if (
            plan.discovery_digest != discovery.receipt_digest
            or _name_ref(name) not in discovery.candidate_refs
        ):
            raise ProjectError("Patched-output discovery evidence changed after planning")
        local = Path(plan.local_path)
        expected_root = self.store.projects_root / plan.project_id / "ascension" / "phone-output"
        try:
            ensure_private_directory(expected_root, boundary=self.store.workspace)
            parent = local.parent.resolve(strict=True)
            verified_root = expected_root.resolve(strict=True)
        except (LocalStoreError, OSError) as exc:
            raise ProjectError("Patched-image verification storage is unavailable") from exc
        if (
            not local.is_absolute()
            or local.name != name
            or parent != verified_root
            or local.is_symlink()
            or local.exists()
        ):
            raise ProjectError("Patched-image retrieval path changed after planning")
        expected = ascension_output_pull_digest(
            plan.device_serial,
            plan.remote_path,
            local,
        )
        if expected != plan.approval_digest:
            raise ProjectError("Patched-image retrieval approval changed after planning")
        return local, expected

    def _active_discovery(
        self,
        project_id: str,
        method: AscensionMethod,
        serial: str,
    ) -> PatchedOutputDiscovery:
        receipt = self.load_discovery(project_id, method, serial)
        if receipt is None:
            raise ProjectError("Scan phone Downloads again before selecting a patched image")
        created_at = datetime.fromisoformat(receipt.created_at)
        now = datetime.now(UTC)
        if not created_at <= now < created_at + self.DISCOVERY_VALID_FOR:
            raise ProjectError("Patched-output discovery expired; scan phone Downloads again")
        return receipt

    def _record_discovery(
        self,
        project_id: str,
        method: AscensionMethod,
        handoff: RootPatchHandoffReceipt,
        device_key: str,
        names: tuple[str, ...],
        truncated: bool,
    ) -> PatchedOutputDiscovery:
        candidate_refs = tuple(_name_ref(name) for name in names)
        payload: dict[str, object] = {
            "schema_version": self.DISCOVERY_SCHEMA_VERSION,
            "discovery_id": uuid4().hex,
            "project_id": project_id,
            "method": method.value,
            "created_at": datetime.now(UTC).isoformat(),
            "handoff_receipt_digest": handoff.receipt_digest,
            "device_key": device_key,
            "state": "found" if names else "none",
            "candidate_count": len(names),
            "candidate_refs": candidate_refs,
            "candidate_set_digest": _json_digest(candidate_refs),
            "recommended_name_ref": candidate_refs[0] if candidate_refs else "",
            "truncated": truncated,
            "data_scope": "filenames-only",
            "source_directory": "/sdcard/Download",
            "ordering": "modified-descending",
            "phone_changed": False,
            "execution_authority": "none",
        }
        receipt = PatchedOutputDiscovery(
            **(payload | {"method": method}),
            receipt_digest=_json_digest(payload),
        )
        path = self._discovery_path(project_id, method)
        document = {
            "format": self.DISCOVERY_FORMAT,
            **asdict(receipt),
            "method": method.value,
        }
        try:
            ensure_private_directory(path.parent, boundary=self.store.workspace)
            for destination in (
                path,
                path.parent / f"discovery-{receipt.discovery_id[:12]}.romverse",
            ):
                atomic_write_json(
                    destination,
                    document,
                    boundary=self.store.workspace,
                    maximum_bytes=self.MAX_RECEIPT_BYTES,
                )
        except LocalStoreError as exc:
            raise ProjectError("Patched-output discovery could not be stored safely") from exc
        return receipt

    def _discovery_path(self, project_id: str, method: AscensionMethod) -> Path:
        return (
            self.store.projects_root
            / project_id
            / "ascension"
            / "phone-output"
            / method.value
            / self.DISCOVERY_NAME
        )

    def _require_handoff(self, project_id: str, method: AscensionMethod, serial: str) -> str:
        _handoff, device_key = self._current_handoff(project_id, method, serial)
        return device_key

    def _current_handoff(
        self,
        project_id: str,
        method: AscensionMethod,
        serial: str,
    ) -> tuple[RootPatchHandoffReceipt, str]:
        device_key = WorkspacePrivacy(self.store.workspace).pseudonym(serial)
        handoff = RootPatchHandoffService(
            self.store, self.adb_executable, self.gateway, self.approvals
        ).load(project_id, method)
        if handoff is None or handoff.device_key != device_key:
            raise ProjectError("The authorized phone does not match the verified Ascension handoff")
        return handoff, device_key


def _result_error(prefix: str, result) -> str:
    detail = (result.stderr or result.stdout).strip().replace("\n", " ")[:300]
    return f"{prefix}: {detail or f'ADB returned {result.returncode}'}"


def _name_ref(name: str) -> str:
    return hashlib.sha256(name.encode("utf-8")).hexdigest()


def _json_digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _sha256_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _safe_text(value: object, maximum: int, *, allow_empty: bool = False) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) <= maximum
        and "\x00" not in value
        and (allow_empty or value)
    )


def _valid_discovery_shape(receipt: PatchedOutputDiscovery, maximum_text: int) -> bool:
    return bool(
        type(receipt.schema_version) is int
        and _safe_text(receipt.discovery_id, maximum_text)
        and _safe_text(receipt.project_id, maximum_text)
        and isinstance(receipt.method, AscensionMethod)
        and _safe_text(receipt.created_at, maximum_text)
        and _sha256_value(receipt.handoff_receipt_digest)
        and _safe_text(receipt.device_key, maximum_text)
        and _safe_text(receipt.state, maximum_text)
        and type(receipt.candidate_count) is int
        and isinstance(receipt.candidate_refs, tuple)
        and _sha256_value(receipt.candidate_set_digest)
        and (receipt.recommended_name_ref == "" or _sha256_value(receipt.recommended_name_ref))
        and type(receipt.truncated) is bool
        and _safe_text(receipt.data_scope, maximum_text)
        and _safe_text(receipt.source_directory, maximum_text)
        and _safe_text(receipt.ordering, maximum_text)
        and type(receipt.phone_changed) is bool
        and _safe_text(receipt.execution_authority, maximum_text)
        and _sha256_value(receipt.receipt_digest)
    )
