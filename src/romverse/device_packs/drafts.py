from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from romverse.device.models import AndroidDevice
from romverse.device_packs.models import DevicePack
from romverse.device_packs.registry import DevicePackRegistry
from romverse.device_packs.requirements import ProjectSourceRequirements
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
    SOURCE_KINDS = frozenset({"ota-payload", "fastboot-super", "partition-bundle"})
    MISSING_FLASH_CONTRACTS = (
        "Exact partition-to-artifact write contract",
        "Exact readback and first-boot verification contract",
        "Exact transition, slot and recovery orchestration contract",
        "Exact AVB execution policy",
        "Exact stock recovery route",
        "Independent physical recovery test",
    )

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

        manufacturer = _identity(
            device.brand or device.manufacturer, "retail brand or manufacturer"
        )
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

    def request_from_project_source(
        self,
        pack: DevicePack,
        device: AndroidDevice,
        source: ProjectSourceRequirements,
    ) -> dict[str, object]:
        """Bind a review draft to one revalidated local project source and phone identity."""

        request = self.request_from_device(pack, device)
        manufacturer = _identity(
            device.brand or device.manufacturer, "retail brand or manufacturer"
        )
        codename = _identity(device.codename or device.product, "codename or product")
        if (
            manufacturer.casefold() != source.manufacturer.casefold()
            or codename.casefold() != source.codename.casefold()
        ):
            raise ValueError("project source does not match the connected phone identity")
        request["source_evidence"] = {
            "project_id": source.project_id,
            "source_sha256": source.source_sha256,
            "source_kind": source.source_kind,
            "blueprint_digest": source.blueprint_digest,
            "plan_digest": source.plan_digest,
            "authority": source.authority,
            "manufacturer": source.manufacturer,
            "codename": source.codename,
            "build_id": source.build_id,
            "partition_count": source.partition_count,
            "required_tools": list(source.required_tools),
        }
        notes = request["notes"]
        assert isinstance(notes, list)
        notes.extend(
            (
                f"Strict local {source.source_kind} evidence binds protected source {source.source_sha256} and build {source.build_id}.",
                f"The local source blueprint reports {source.partition_count} partition records; exact write, readback, AVB, transition, stock-recovery, and physical-test contracts still require review.",
                "This exact-source draft is a development handoff, not a flash authorization or public compatibility claim.",
            )
        )
        return request

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
            "source_evidence",
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
        source_evidence = self._validated_source_evidence(request.get("source_evidence"))
        source_detail = (
            f"Strict project-local {source_evidence['source_kind']} evidence binds build "
            f"{source_evidence['build_id']} and {source_evidence['partition_count']} observed "
            "partition records; an exact reviewed build contract is still required."
            if source_evidence is not None
            else "No immutable firmware build contract has been reviewed or published."
        )
        partition_detail = (
            f"A source blueprint records {source_evidence['partition_count']} partitions, but "
            "their exact writable artifacts, slots, AVB relationships, and recovery behavior "
            "remain locked pending review."
            if source_evidence is not None
            else "No exact partition, slot, filesystem, or AVB contract is available."
        )
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
                    "detail": source_detail,
                },
                {
                    "capability_id": "partition_layout",
                    "label": "Partition layout",
                    "status": "planned",
                    "scope": "locked",
                    "detail": partition_detail,
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
        if source_evidence is not None:
            document["draft_context"] = {
                **source_evidence,
                "status": "review-required",
                "missing_flash_contracts": list(self.MISSING_FLASH_CONTRACTS),
                "execution_authority": "none",
                "phone_action_allowed": False,
                "public_compatibility_claim": False,
            }
        return document

    def _validated_source_evidence(self, value: object) -> dict[str, object] | None:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError("source evidence must be an object")
        expected = {
            "project_id",
            "source_sha256",
            "source_kind",
            "blueprint_digest",
            "plan_digest",
            "authority",
            "manufacturer",
            "codename",
            "build_id",
            "partition_count",
            "required_tools",
        }
        if set(value) != expected:
            raise ValueError("source evidence fields do not match the exact draft contract")
        source_kind = value.get("source_kind")
        expected_authority = {
            "ota-payload": "project-local-build-evidence-only",
            "fastboot-super": "project-local-build-evidence-only",
            "partition-bundle": "project-local-inventory-evidence-only",
        }.get(source_kind)
        required_tools = _nonempty_strings(value.get("required_tools"), "required tools")
        partition_count = value.get("partition_count")
        if (
            not isinstance(value.get("project_id"), str)
            or re.fullmatch(r"[a-z0-9-]{1,64}", str(value["project_id"])) is None
            or not _sha256(value.get("source_sha256"))
            or source_kind not in self.SOURCE_KINDS
            or not _sha256(value.get("blueprint_digest"))
            or not _sha256(value.get("plan_digest"))
            or value.get("authority") != expected_authority
            or not isinstance(partition_count, int)
            or isinstance(partition_count, bool)
            or not 1 <= partition_count <= 1_024
            or len(required_tools) != len(set(required_tools))
        ):
            raise ValueError("source evidence is incomplete or unsafe")
        return {
            "project_id": value["project_id"],
            "source_sha256": value["source_sha256"],
            "source_kind": source_kind,
            "blueprint_digest": value["blueprint_digest"],
            "plan_digest": value["plan_digest"],
            "authority": value["authority"],
            "manufacturer": _identity(str(value.get("manufacturer", "")), "manufacturer"),
            "codename": _identity(str(value.get("codename", "")), "codename"),
            "build_id": _identity(str(value.get("build_id", "")), "build ID"),
            "partition_count": partition_count,
            "required_tools": list(required_tools),
        }

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


def _sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


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
