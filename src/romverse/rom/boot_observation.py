from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum

from romverse.core.privacy import WorkspacePrivacy
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.registry import DevicePackRegistry
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore


class BootObservationStatus(StrEnum):
    WAITING = "waiting"
    SETTLING = "settling"
    STABLE = "stable"
    ATTENTION = "attention"


@dataclass(frozen=True, slots=True)
class BootSample:
    observed_at: str
    device_pseudonym: str
    state: str
    boot_completed: bool | None
    uptime_seconds: int | None
    slot_suffix: str
    build_id: str
    build_fingerprint: str
    battery_percent: int | None
    probe_errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BootObservationReceipt:
    schema_version: int
    project_id: str
    pack_id: str
    contract_id: str
    source_original_sha256: str
    samples: tuple[BootSample, ...]
    status: BootObservationStatus
    stable: bool
    reboot_detected: bool
    flash_linked: bool
    verified_first_boot: bool
    diagnosis: str
    phone_changed: bool
    receipt_digest: str


class BootObservationService:
    """Accumulate read-only boot evidence without claiming that a ROM was flashed."""

    NAME = "boot-observation.romverse"
    MIN_SAMPLE_INTERVAL_SECONDS = 60
    STABILITY_WINDOW_SECONDS = 300
    MAX_SAMPLES = 30

    def __init__(self, store: RomProjectStore, registry: DevicePackRegistry) -> None:
        self.store = store
        self.registry = registry
        self.privacy = WorkspacePrivacy(store.workspace)

    def observe(
        self,
        project_id: str,
        device: AndroidDevice,
        observed_at: datetime | None = None,
    ) -> BootObservationReceipt:
        project = self.store.get(project_id)
        pack = next(
            (item for item in self.registry.packs if item.pack_id == project.device_pack_id), None
        )
        if project.original is None or pack is None or pack.build_contract is None:
            raise ProjectError("Boot observation requires an exact source-bound Device Pack")
        resolution = self.registry.resolve(device)
        if resolution.pack is None or resolution.pack.pack_id != pack.pack_id:
            raise ProjectError("Connected device does not match the project's exact Device Pack")
        now = (observed_at or datetime.now(UTC)).astimezone(UTC)
        pseudonym = self.privacy.pseudonym(device.serial)
        previous = self.load(project_id)
        if previous is not None and previous.samples:
            if previous.samples[0].device_pseudonym != pseudonym:
                raise ProjectError("Boot observation is already bound to another device")
            latest = previous.samples[-1]
            elapsed = (now - datetime.fromisoformat(latest.observed_at)).total_seconds()
            if elapsed < self.MIN_SAMPLE_INTERVAL_SECONDS:
                return previous
        sample = BootSample(
            now.isoformat(),
            pseudonym,
            device.state.value,
            device.boot_completed,
            device.uptime_seconds,
            device.slot_suffix,
            device.build_id[:160],
            device.build_fingerprint[:500],
            device.battery_percent,
            tuple(error[:240] for error in device.errors[:12]),
        )
        samples = ((*previous.samples, sample) if previous is not None else (sample,))[
            -self.MAX_SAMPLES :
        ]
        status, stable, rebooted, diagnosis = self._classify(samples)
        payload = {
            "schema_version": 1,
            "project_id": project_id,
            "pack_id": pack.pack_id,
            "contract_id": pack.build_contract.contract_id,
            "source_original_sha256": project.original.sha256,
            "samples": [asdict(item) for item in samples],
            "status": status.value,
            "stable": stable,
            "reboot_detected": rebooted,
            "flash_linked": False,
            "verified_first_boot": False,
            "diagnosis": diagnosis,
            "phone_changed": False,
        }
        digest = _digest(payload)
        receipt = BootObservationReceipt(
            1,
            project_id,
            pack.pack_id,
            pack.build_contract.contract_id,
            project.original.sha256,
            samples,
            status,
            stable,
            rebooted,
            False,
            False,
            diagnosis,
            False,
            digest,
        )
        _atomic_json(
            self.store.projects_root / project_id / self.NAME,
            {"format": "romverse.boot-observation", **asdict(receipt)},
        )
        return receipt

    def load(self, project_id: str) -> BootObservationReceipt | None:
        path = self.store.projects_root / project_id / self.NAME
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.pop("format") != "romverse.boot-observation":
                return None
            samples = tuple(
                BootSample(
                    str(item["observed_at"]),
                    str(item["device_pseudonym"]),
                    str(item["state"]),
                    item.get("boot_completed"),
                    int(item["uptime_seconds"]) if item.get("uptime_seconds") is not None else None,
                    str(item.get("slot_suffix", "")),
                    str(item.get("build_id", "")),
                    str(item.get("build_fingerprint", "")),
                    int(item["battery_percent"])
                    if item.get("battery_percent") is not None
                    else None,
                    tuple(map(str, item.get("probe_errors", ()))),
                )
                for item in data.pop("samples")
            )
            data["status"] = BootObservationStatus(str(data["status"]))
            receipt = BootObservationReceipt(**data, samples=samples)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None
        project = self.store.get(project_id)
        pack = next(
            (item for item in self.registry.packs if item.pack_id == project.device_pack_id), None
        )
        payload = asdict(receipt)
        digest = str(payload.pop("receipt_digest"))
        if (
            receipt.schema_version != 1
            or receipt.project_id != project_id
            or receipt.phone_changed
            or receipt.flash_linked
            or receipt.verified_first_boot
            or not receipt.samples
            or project.original is None
            or receipt.source_original_sha256 != project.original.sha256
            or pack is None
            or pack.build_contract is None
            or receipt.pack_id != pack.pack_id
            or receipt.contract_id != pack.build_contract.contract_id
            or _digest(payload) != digest
        ):
            return None
        return receipt

    @classmethod
    def next_sample_wait_seconds(
        cls,
        receipt: BootObservationReceipt | None,
        observed_at: datetime | None = None,
    ) -> int:
        if receipt is None or not receipt.samples:
            return 0
        now = (observed_at or datetime.now(UTC)).astimezone(UTC)
        elapsed = (now - datetime.fromisoformat(receipt.samples[-1].observed_at)).total_seconds()
        return max(0, math.ceil(cls.MIN_SAMPLE_INTERVAL_SECONDS - elapsed))

    @staticmethod
    def next_step(receipt: BootObservationReceipt | None) -> str:
        if receipt is None:
            return "Record a read-only baseline only if the exact target phone is connected. This is not proof that ROMVERSE flashed it."
        if receipt.status is BootObservationStatus.SETTLING:
            return "Leave the phone connected and unlocked while Android finishes starting, then record another sample."
        if receipt.status is BootObservationStatus.WAITING:
            return "Keep the phone connected. Record a follow-up after the five-minute stability window."
        if receipt.status is BootObservationStatus.STABLE:
            return "Android looks stable on the same build and slot. A matching signed Guardian write receipt is still required before this can become verified first-boot evidence."
        return "Stop and review the diagnosis before any further device-changing work. ROMVERSE will not call this a successful boot."

    @classmethod
    def _classify(
        cls, samples: tuple[BootSample, ...]
    ) -> tuple[BootObservationStatus, bool, bool, str]:
        latest = samples[-1]
        pairs = tuple(zip(samples, samples[1:], strict=False))
        rebooted = any(
            earlier.uptime_seconds is not None
            and later.uptime_seconds is not None
            and later.uptime_seconds + 30 < earlier.uptime_seconds
            for earlier, later in pairs
        )
        fingerprint_changed = any(
            earlier.build_fingerprint
            and later.build_fingerprint
            and earlier.build_fingerprint != later.build_fingerprint
            for earlier, later in pairs
        )
        if latest.state != DeviceState.DEVICE.value:
            return (
                BootObservationStatus.ATTENTION,
                False,
                rebooted,
                f"ADB reports {latest.state}; stable Android userspace is not observable",
            )
        if fingerprint_changed:
            return (
                BootObservationStatus.ATTENTION,
                False,
                rebooted,
                "Build fingerprint changed inside one observation session",
            )
        if rebooted:
            return (
                BootObservationStatus.ATTENTION,
                False,
                True,
                "Device uptime reset during observation; investigate a reboot or boot loop",
            )
        if latest.boot_completed is not True:
            status = (
                BootObservationStatus.ATTENTION
                if latest.uptime_seconds is not None and latest.uptime_seconds >= 20 * 60
                else BootObservationStatus.SETTLING
            )
            return status, False, False, "Android has not yet reported sys.boot_completed=1"
        if len(samples) >= 2:
            earlier = samples[-2]
            elapsed = (
                datetime.fromisoformat(latest.observed_at)
                - datetime.fromisoformat(earlier.observed_at)
            ).total_seconds()
            uptime_gain = (
                latest.uptime_seconds - earlier.uptime_seconds
                if latest.uptime_seconds is not None and earlier.uptime_seconds is not None
                else -1
            )
            same_identity = (
                latest.build_fingerprint == earlier.build_fingerprint
                and latest.slot_suffix == earlier.slot_suffix
                and latest.device_pseudonym == earlier.device_pseudonym
            )
            if (
                elapsed >= cls.STABILITY_WINDOW_SECONDS
                and uptime_gain >= elapsed - 60
                and same_identity
                and earlier.boot_completed is True
            ):
                return (
                    BootObservationStatus.STABLE,
                    True,
                    False,
                    "Android remained boot-complete on the same build and slot across the stability window",
                )
        return (
            BootObservationStatus.WAITING,
            False,
            False,
            "Boot completion observed; collect another sample after the stability window",
        )


def _digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _atomic_json(path, payload: dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
