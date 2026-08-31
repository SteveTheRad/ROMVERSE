from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from romverse.device.models import AndroidDevice
from romverse.device_packs.models import DevicePack
from romverse.device_packs.registry import DevicePackRegistry
from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_bytes,
    read_json_object,
)


@dataclass(frozen=True, slots=True)
class DevicePackDraftExport:
    output_path: Path
    sha256: str
    size_bytes: int
    pack_id: str


class DevicePackDraftService:
    """Create review-only exact-model Pack candidates that cannot enter the live registry."""

    FORMAT = "romverse.device-pack-draft-request"
    MAXIMUM_REQUEST_BYTES = 256 * 1024

    def load_request(self, path: Path) -> dict[str, object]:
        try:
            return read_json_object(
                path,
                boundary=path.parent,
                maximum_bytes=self.MAXIMUM_REQUEST_BYTES,
            )
        except LocalStoreError as exc:
            raise ValueError(f"draft request is unsafe or invalid: {exc}") from exc

    def request_from_device(
        self,
        pack: DevicePack,
        device: AndroidDevice,
    ) -> dict[str, object]:
        """Create a privacy-safe review request without serial or device authority."""

        manufacturer = _identity(device.manufacturer, "manufacturer")
        model = _identity(device.model, "model")
        product = _identity(device.product or device.codename, "product or codename")
        codename = _identity(device.codename or device.product, "codename or product")
        if not pack.knowledge_sources:
            raise ValueError("the matched Pack has no reviewed HTTPS sources to seed a model draft")
        identity_digest = hashlib.sha256(
            "\0".join((manufacturer, model, product, codename)).encode("utf-8")
        ).hexdigest()
        pack_stem = f"{pack.pack_id}.{_identifier_slug(model)}.{_identifier_slug(codename)}"
        pack_id = f"{pack_stem[:67].rstrip('._-')}.{identity_digest[:12]}"
        return {
            "format": self.FORMAT,
            "schema_version": 1,
            "pack_id": pack_id,
            "version": "0.1.0",
            "display_name": f"{manufacturer} {model} / {codename}"[:160],
            "priority": min(max(pack.priority + 1, 200), 999),
            "match": {
                "manufacturers": [manufacturer],
                "model_patterns": [model],
                "product_patterns": list(dict.fromkeys((product, codename))),
            },
            "knowledge_sources": [
                {
                    "source_id": source.source_id,
                    "label": source.label,
                    "url": source.url,
                    "authority": source.authority,
                    "scope": source.scope,
                    "verified_on": source.verified_on,
                }
                for source in pack.knowledge_sources
            ],
            "notes": [
                f"Connected Android properties proposed {model} / {product} / {codename} for maintainer review.",
                f"Starting source context inherited from {pack.pack_id}; these sources do not prove exact-model or firmware compatibility.",
                "No serial number, account, user file, command, approval, credential, or device-write authority is included.",
            ],
        }

    def build_document(self, request: dict[str, object]) -> dict[str, object]:
        if request.get("format") != self.FORMAT or request.get("schema_version") != 1:
            raise ValueError("unsupported Device Pack draft request")
        allowed = {
            "format",
            "schema_version",
            "pack_id",
            "version",
            "display_name",
            "priority",
            "match",
            "knowledge_sources",
            "notes",
        }
        unexpected = sorted(set(request) - allowed)
        if unexpected:
            raise ValueError(f"unsupported draft request fields: {', '.join(unexpected)}")
        match = request.get("match")
        if not isinstance(match, dict):
            raise ValueError("draft match must be an object")
        allowed_match = {"manufacturers", "model_patterns", "product_patterns"}
        unexpected_match = sorted(set(match) - allowed_match)
        if unexpected_match:
            raise ValueError(f"unsupported match fields: {', '.join(unexpected_match)}")
        model_patterns = _nonempty_strings(match.get("model_patterns"), "model patterns")
        product_patterns = _nonempty_strings(match.get("product_patterns"), "product patterns")
        if any(pattern == "*" for pattern in (*model_patterns, *product_patterns)):
            raise ValueError("exact-model drafts cannot use wildcard-only identity")
        document: dict[str, object] = {
            "schema_version": 1,
            "publication_status": "draft",
            "pack_id": request.get("pack_id"),
            "version": request.get("version"),
            "display_name": request.get("display_name"),
            "priority": request.get("priority", 200),
            "match": {
                "manufacturers": list(
                    _nonempty_strings(match.get("manufacturers"), "manufacturers")
                ),
                "model_patterns": list(model_patterns),
                "product_patterns": list(product_patterns),
            },
            "knowledge_sources": request.get("knowledge_sources"),
            "capabilities": [
                {
                    "capability_id": "exact_identity",
                    "label": "Proposed exact model identity",
                    "status": "limited",
                    "scope": "evidence_only",
                    "detail": "Connected Android properties are recorded for maintainer review; direct official-source corroboration is still required.",
                },
                {
                    "capability_id": "firmware_contract",
                    "label": "Firmware build contract",
                    "status": "planned",
                    "scope": "locked",
                    "detail": "No immutable firmware build contract has been reviewed or published.",
                },
                {
                    "capability_id": "partition_layout",
                    "label": "Partition layout",
                    "status": "planned",
                    "scope": "locked",
                    "detail": "No exact partition, slot, filesystem, or AVB contract is available.",
                },
                {
                    "capability_id": "physical_recovery",
                    "label": "Physical recovery validation",
                    "status": "planned",
                    "scope": "locked",
                    "detail": "Signed physical recovery and first-boot evidence is required.",
                },
            ],
            "notes": [
                "DRAFT ONLY: this file cannot activate in Device Atlas.",
                "Execution authority is NONE; no build, unlock, wipe, root, flash, or recovery action is allowed.",
                *list(_string_list(request.get("notes", []), "notes", allow_empty=True)),
            ],
        }
        # Validate ordinary fields with the production parser, then retain the draft marker so
        # the exported file is rejected if someone attempts to index it.
        validation_copy = dict(document)
        validation_copy.pop("publication_status")
        DevicePackRegistry._parse(validation_copy, "0" * 64)
        return document

    def export(
        self,
        request: dict[str, object],
        output_dir: Path,
        *,
        boundary: Path | None = None,
    ) -> DevicePackDraftExport:
        document = self.build_document(request)
        payload = _canonical(document) + b"\n"
        digest = hashlib.sha256(payload).hexdigest()
        pack_id = str(document["pack_id"])
        output_path = output_dir / f"{pack_id}-{digest[:12]}.draft.json"
        try:
            atomic_write_bytes(
                output_path,
                payload,
                boundary=boundary or output_dir.parent,
                maximum_bytes=self.MAXIMUM_REQUEST_BYTES,
            )
        except LocalStoreError as exc:
            raise ValueError(f"Device Pack draft could not be preserved safely: {exc}") from exc
        return DevicePackDraftExport(output_path, digest, len(payload), pack_id)


def _nonempty_strings(value: object, label: str) -> tuple[str, ...]:
    values = _string_list(value, label)
    if not values or any(not item.strip() for item in values):
        raise ValueError(f"{label} must be a non-empty string list")
    return values


def _string_list(
    value: object,
    label: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or (not value and not allow_empty)
        or any(not isinstance(item, str) for item in value)
    ):
        raise ValueError(f"{label} must be a string list")
    return tuple(value)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _identity(value: str, label: str) -> str:
    text = value.strip()
    if (
        not text
        or text.casefold().startswith("unknown")
        or len(text) > 160
        or any(ord(character) < 32 for character in text)
    ):
        raise ValueError(f"connected {label} is unavailable or unsafe")
    return text


def _identifier_slug(value: str) -> str:
    slug = "-".join(
        part
        for part in "".join(
            character.casefold() if character.isascii() and character.isalnum() else "-"
            for character in value
        ).split("-")
        if part
    )
    return slug[:24] or "model"
