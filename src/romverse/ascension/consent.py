from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Collection
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from romverse.ascension.final_handoff import AscensionFinalHandoff, AscensionFinalHandoffService
from romverse.ascension.models import AscensionMethod
from romverse.device.models import AndroidDevice
from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    ensure_private_directory,
    read_json_object,
)
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore


@dataclass(frozen=True, slots=True)
class AscensionConsentReview:
    """Short-lived acknowledgement record carrying deliberately zero write authority."""

    schema_version: int
    review_id: str
    created_at: str
    expires_at: str
    project_id: str
    method: AscensionMethod
    handoff_id: str
    handoff_digest: str
    device_key: str
    device_name: str
    device_codename: str
    target_partition: str
    target_slot: str
    patched_image_sha256: str
    data_action: str
    acknowledgements: tuple[str, ...]
    execution_authority: str
    command_manifest: tuple[tuple[str, ...], ...]
    bootloader_unlock_allowed: bool
    bootloader_relock_allowed: bool
    user_data_wipe_allowed: bool
    phone_changed: bool
    review_digest: str


class AscensionConsentReviewService:
    """Record informed review without turning it into approval or execution authority."""

    FORMAT = "romverse.ascension-consent-review"
    SCHEMA_VERSION = 1
    RECEIPT_NAME = "final-consent-review.romverse"
    MAX_BYTES = 128 * 1024
    MAX_TEXT = 4096
    VALID_FOR = timedelta(minutes=10)
    REQUIRED_ACKNOWLEDGEMENTS = frozenset(
        {
            "exact-device-reviewed",
            "backup-and-rollback-reviewed",
            "patched-image-reviewed",
            "boot-risk-understood",
            "keep-data-no-wipe",
            "bootloader-relock-prohibited",
            "separate-device-write-approval-required",
        }
    )

    def __init__(
        self,
        store: RomProjectStore,
        handoffs: AscensionFinalHandoffService,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self.handoffs = handoffs
        self._clock = clock or (lambda: datetime.now(UTC))

    def record(
        self,
        handoff: AscensionFinalHandoff,
        device: AndroidDevice,
        acknowledgements: Collection[str],
    ) -> AscensionConsentReview:
        current = self.handoffs.load(handoff.project_id, handoff.method, device)
        if current is None or current.handoff_digest != handoff.handoff_digest:
            raise ProjectError(
                "Ascension consent requires a fresh exact-device Guardian handoff review"
            )
        normalized = tuple(sorted(set(acknowledgements)))
        if set(normalized) != self.REQUIRED_ACKNOWLEDGEMENTS:
            raise ProjectError("Review every required Ascension consequence before continuing")
        created = self._aware_now()
        payload: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "review_id": uuid4().hex,
            "created_at": created.isoformat(),
            "expires_at": (created + self.VALID_FOR).isoformat(),
            "project_id": handoff.project_id,
            "method": handoff.method.value,
            "handoff_id": handoff.handoff_id,
            "handoff_digest": handoff.handoff_digest,
            "device_key": handoff.device_key,
            "device_name": handoff.device_name,
            "device_codename": handoff.device_codename,
            "target_partition": handoff.target_partition,
            "target_slot": handoff.target_slot,
            "patched_image_sha256": handoff.patched_image_sha256,
            "data_action": "keep-data-no-wipe",
            "acknowledgements": normalized,
            "execution_authority": "none",
            "command_manifest": (),
            "bootloader_unlock_allowed": False,
            "bootloader_relock_allowed": False,
            "user_data_wipe_allowed": False,
            "phone_changed": False,
        }
        materialized = dict(payload)
        materialized["method"] = handoff.method
        review = AscensionConsentReview(
            **materialized,
            review_digest=_digest(payload),
        )
        self.validate(review, handoff)
        self._write(review)
        return review

    def load(
        self,
        project_id: str,
        method: AscensionMethod,
        device: AndroidDevice | None = None,
    ) -> AscensionConsentReview | None:
        if device is None:
            return None
        path = self._path(project_id)
        try:
            data = read_json_object(
                path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            if (
                set(data) != {"format", *(field.name for field in fields(AscensionConsentReview))}
                or data.pop("format") != self.FORMAT
            ):
                return None
            raw_acknowledgements = data.get("acknowledgements")
            raw_commands = data.get("command_manifest")
            if (
                not isinstance(raw_acknowledgements, list)
                or len(raw_acknowledgements) != len(self.REQUIRED_ACKNOWLEDGEMENTS)
                or any(not _safe_text(item, self.MAX_TEXT) for item in raw_acknowledgements)
                or raw_commands != []
            ):
                return None
            data["method"] = AscensionMethod(str(data["method"]))
            data["acknowledgements"] = tuple(raw_acknowledgements)
            data["command_manifest"] = ()
            review = AscensionConsentReview(**data)
            handoff = self.handoffs.load(project_id, method, device)
            if handoff is None:
                return None
            self.validate(review, handoff)
            if self._aware_now() >= _timestamp(review.expires_at):
                return None
        except (LocalStoreError, ValueError, TypeError, KeyError, ProjectError):
            return None
        return review

    def validate(
        self,
        review: AscensionConsentReview,
        handoff: AscensionFinalHandoff,
    ) -> None:
        unsigned = asdict(review)
        expected = str(unsigned.pop("review_digest", ""))
        unsigned["method"] = review.method.value
        created = _timestamp(review.created_at)
        expires = _timestamp(review.expires_at)
        if (
            review.schema_version != self.SCHEMA_VERSION
            or not _valid_review_shape(review, self.MAX_TEXT)
            or not review.review_id
            or len(review.review_id) > 80
            or review.project_id != handoff.project_id
            or review.method is not handoff.method
            or review.handoff_id != handoff.handoff_id
            or review.handoff_digest != handoff.handoff_digest
            or review.device_key != handoff.device_key
            or review.device_name != handoff.device_name
            or review.device_codename != handoff.device_codename
            or review.target_partition != handoff.target_partition
            or review.target_slot != handoff.target_slot
            or review.patched_image_sha256 != handoff.patched_image_sha256
            or review.data_action != "keep-data-no-wipe"
            or set(review.acknowledgements) != self.REQUIRED_ACKNOWLEDGEMENTS
            or len(review.acknowledgements) != len(self.REQUIRED_ACKNOWLEDGEMENTS)
            or review.execution_authority != "none"
            or review.command_manifest
            or review.bootloader_unlock_allowed
            or review.bootloader_relock_allowed
            or review.user_data_wipe_allowed
            or review.phone_changed
            or expires <= created
            or expires - created != self.VALID_FOR
            or not _sha256_value(expected)
            or expected != _digest(unsigned)
        ):
            raise ProjectError("Ascension consent review failed integrity or safety validation")

    def _write(self, review: AscensionConsentReview) -> None:
        path = self._path(review.project_id)
        payload = {"format": self.FORMAT, **asdict(review), "method": review.method.value}
        try:
            ensure_private_directory(path.parent, boundary=self.store.workspace)
            atomic_write_json(
                path,
                payload,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
        except LocalStoreError as exc:
            raise ProjectError(
                "Ascension consequence-review evidence could not be stored safely"
            ) from exc

    def _path(self, project_id: str) -> Path:
        return self.store.projects_root / project_id / "ascension" / "guardian" / self.RECEIPT_NAME

    def _aware_now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ProjectError("Ascension consent clock must include a timezone")
        return value.astimezone(UTC)


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(UTC)


def _sha256_value(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _valid_review_shape(review: AscensionConsentReview, maximum_text: int) -> bool:
    return bool(
        type(review.schema_version) is int
        and all(
            type(value) is bool
            for value in (
                review.bootloader_unlock_allowed,
                review.bootloader_relock_allowed,
                review.user_data_wipe_allowed,
                review.phone_changed,
            )
        )
        and not review.command_manifest
        and len(set(review.acknowledgements)) == len(review.acknowledgements)
        and all(_safe_text(item, maximum_text) for item in review.acknowledgements)
        and all(
            _safe_text(value, maximum_text)
            for value in (
                review.review_id,
                review.created_at,
                review.expires_at,
                review.project_id,
                review.handoff_id,
                review.device_key,
                review.device_name,
                review.device_codename,
                review.target_partition,
                review.target_slot,
                review.data_action,
                review.execution_authority,
            )
        )
        and all(
            _sha256_value(value)
            for value in (
                review.handoff_digest,
                review.patched_image_sha256,
                review.review_digest,
            )
        )
    )


def _safe_text(value: object, maximum: int) -> bool:
    return bool(
        isinstance(value, str)
        and value
        and len(value) <= maximum
        and all(ord(character) >= 32 for character in value)
    )
