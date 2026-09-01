from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime

from romverse.ascension.models import AscensionMethod
from romverse.ascension.releases import OfficialRootReleaseService
from romverse.core.privacy import WorkspacePrivacy
from romverse.device.models import AndroidDevice, DeviceState
from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    ensure_private_directory,
    read_json_object,
)
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore


@dataclass(frozen=True, slots=True)
class KernelSuSupportEvidence:
    schema_version: int
    project_id: str
    created_at: str
    source_original_sha256: str
    device_key: str
    device_codename: str
    kernel_version: str
    manager_tag: str
    manager_sha256: str
    status: str
    observation: str
    manager_installed: bool
    root_applied: bool
    evidence_digest: str


class KernelSuSupportEvidenceService:
    """Record the exact official KernelSU Manager compatibility result."""

    FORMAT = "romverse.kernelsu-support-evidence"
    SCHEMA_VERSION = 1
    RECEIPT_NAME = "kernelsu-support.romverse"
    MAX_BYTES = 64 * 1024
    STATUSES = frozenset({"supported", "unsupported"})

    def __init__(
        self,
        store: RomProjectStore,
        release_service: OfficialRootReleaseService | None = None,
    ) -> None:
        self.store = store
        self.release_service = release_service or OfficialRootReleaseService(store.workspace)

    def record(
        self,
        project_id: str,
        device: AndroidDevice,
        manager_tag: str,
        manager_sha256: str,
        status: str,
    ) -> KernelSuSupportEvidence:
        project = self.store.get(project_id)
        if project.original is None:
            raise ProjectError("KernelSU support evidence requires a protected source")
        if device.state is not DeviceState.DEVICE or not device.serial or not device.codename:
            raise ProjectError("KernelSU support evidence requires the exact authorized phone")
        if status not in self.STATUSES:
            raise ProjectError("KernelSU support status is invalid")
        if (
            not device.kernel_version
            or len(device.kernel_version) > 160
            or any(ord(character) < 32 for character in device.kernel_version)
        ):
            raise ProjectError("KernelSU support evidence requires the exact live kernel identity")
        if not manager_tag or not _sha256_text(manager_sha256):
            raise ProjectError("Verified KernelSU manager identity is incomplete")
        if not self._manager_is_verified(manager_tag, manager_sha256):
            raise ProjectError(
                "KernelSU support evidence requires the revalidated official Manager from the Ascension vault"
            )
        payload: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "project_id": project_id,
            "created_at": datetime.now(UTC).isoformat(),
            "source_original_sha256": project.original.sha256,
            "device_key": WorkspacePrivacy(self.store.workspace).pseudonym(device.serial),
            "device_codename": device.codename,
            "kernel_version": device.kernel_version,
            "manager_tag": manager_tag,
            "manager_sha256": manager_sha256,
            "status": status,
            "observation": (
                "User confirmed the verified official Manager displayed Not installed"
                if status == "supported"
                else "User confirmed the verified official Manager displayed Unsupported"
            ),
            "manager_installed": True,
            "root_applied": False,
        }
        digest = _digest(payload)
        evidence = KernelSuSupportEvidence(
            self.SCHEMA_VERSION,
            project_id,
            str(payload["created_at"]),
            project.original.sha256,
            str(payload["device_key"]),
            device.codename,
            device.kernel_version,
            manager_tag,
            manager_sha256,
            status,
            str(payload["observation"]),
            True,
            False,
            digest,
        )
        path = self.store.projects_root / project_id / "ascension" / self.RECEIPT_NAME
        try:
            ensure_private_directory(path.parent, boundary=self.store.workspace)
            atomic_write_json(
                path,
                {"format": self.FORMAT, **asdict(evidence)},
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
        except LocalStoreError as exc:
            raise ProjectError(
                "KernelSU compatibility evidence could not be stored safely"
            ) from exc
        return evidence

    def load(self, project_id: str, device: AndroidDevice | None) -> KernelSuSupportEvidence | None:
        if device is None or device.state is not DeviceState.DEVICE or not device.serial:
            return None
        path = self.store.projects_root / project_id / "ascension" / self.RECEIPT_NAME
        try:
            data = read_json_object(
                path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            if (
                set(data) != {"format", *(field.name for field in fields(KernelSuSupportEvidence))}
                or data.pop("format") != self.FORMAT
            ):
                return None
            evidence = KernelSuSupportEvidence(**data)
        except (LocalStoreError, ValueError, TypeError, KeyError):
            return None
        project = self.store.get(project_id)
        unsigned = asdict(evidence)
        unsigned.pop("evidence_digest")
        expected_observation = (
            "User confirmed the verified official Manager displayed Not installed"
            if evidence.status == "supported"
            else "User confirmed the verified official Manager displayed Unsupported"
        )
        if (
            project.original is None
            or not _valid_evidence_shape(evidence)
            or evidence.schema_version != self.SCHEMA_VERSION
            or evidence.project_id != project_id
            or evidence.source_original_sha256 != project.original.sha256
            or evidence.device_key
            != WorkspacePrivacy(self.store.workspace).pseudonym(device.serial)
            or evidence.device_codename.casefold() != device.codename.casefold()
            or evidence.kernel_version != device.kernel_version
            or evidence.status not in self.STATUSES
            or evidence.observation != expected_observation
            or not self._manager_is_verified(evidence.manager_tag, evidence.manager_sha256)
            or not evidence.manager_installed
            or evidence.root_applied
            or evidence.evidence_digest != _digest(unsigned)
        ):
            return None
        return evidence

    def _manager_is_verified(self, tag: str, sha256: str) -> bool:
        loaded = self.release_service.load_verified(AscensionMethod.KERNELSU_LKM)
        if loaded is None:
            return False
        release, _path = loaded
        return release.tag == tag and release.asset.sha256 == sha256


def _sha256_text(value: str) -> bool:
    return bool(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value))


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _valid_evidence_shape(evidence: KernelSuSupportEvidence) -> bool:
    return bool(
        type(evidence.schema_version) is int
        and type(evidence.manager_installed) is bool
        and type(evidence.root_applied) is bool
        and all(
            _safe_text(value, limit)
            for value, limit in (
                (evidence.project_id, 160),
                (evidence.created_at, 80),
                (evidence.device_codename, 160),
                (evidence.kernel_version, 160),
                (evidence.manager_tag, 80),
                (evidence.status, 40),
                (evidence.observation, 512),
            )
        )
        and _sha256_text(evidence.source_original_sha256)
        and bool(re.fullmatch(r"[0-9a-f]{20}", evidence.device_key))
        and _sha256_text(evidence.manager_sha256)
        and _sha256_text(evidence.evidence_digest)
    )


def _safe_text(value: object, maximum: int) -> bool:
    return bool(
        isinstance(value, str)
        and value
        and len(value) <= maximum
        and all(ord(character) >= 32 for character in value)
    )
