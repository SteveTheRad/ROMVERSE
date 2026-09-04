from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
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
from romverse.rom.avb_evidence import SourceAvbTopologyReceipt


@dataclass(frozen=True, slots=True)
class DevicePackDraftExport:
    output_path: Path
    sha256: str
    size_bytes: int
    pack_id: str


@dataclass(frozen=True, slots=True)
class DevicePackDraftReview:
    """Strictly reloaded status for one private exact-source development draft."""

    output_path: Path
    sha256: str
    pack_id: str
    display_name: str
    project_id: str
    source_sha256: str
    blueprint_digest: str
    build_id: str
    partition_count: int
    missing_flash_contracts: tuple[str, ...]
    source_avb_attached: bool


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
        source_avb: SourceAvbTopologyReceipt | None = None,
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
        if source_avb is not None:
            receipt_payload = asdict(source_avb)
            receipt_payload.pop("receipt_digest", None)
            expected_receipt_digest = hashlib.sha256(
                json.dumps(
                    receipt_payload,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            top = source_avb.images[0] if len(source_avb.images) == 2 else None
            child = source_avb.images[1] if len(source_avb.images) == 2 else None
            consistent = bool(
                top is not None
                and child is not None
                and top.algorithm != "NONE"
                and child.algorithm != "NONE"
                and top.public_key_sha1
                and top.public_key_sha1 == child.public_key_sha1
                and "vbmeta_system" in source_avb.top_level_chain_partitions
            )
            if (
                source_avb.project_id != source.project_id
                or source_avb.source_original_sha256 != source.source_sha256
                or source_avb.phone_changed
                or source_avb.receipt_digest != expected_receipt_digest
                or top is None
                or child is None
                or (top.role, child.role) != ("source-vbmeta", "source-vbmeta_system")
                or not _sha256(top.sha256)
                or not _sha256(child.sha256)
                or source_avb.signing_identity_consistent != consistent
                or not source_avb.top_level_chain_partitions
                or not set(source_avb.top_level_chain_partitions).issubset(
                    top.descriptor_partitions
                )
                or source_avb.child_descriptor_partitions != child.descriptor_partitions
            ):
                raise ValueError("source AVB receipt does not match the exact project source")
            request["source_avb_evidence"] = {
                "project_id": source_avb.project_id,
                "source_sha256": source_avb.source_original_sha256,
                "receipt_digest": source_avb.receipt_digest,
                "payload_manifest_digest": source_avb.payload_manifest_digest,
                "signing_identity_consistent": source_avb.signing_identity_consistent,
                "algorithm": top.algorithm,
                "public_key_sha1": top.public_key_sha1,
                "vbmeta_sha256": top.sha256,
                "vbmeta_system_algorithm": child.algorithm,
                "vbmeta_system_public_key_sha1": child.public_key_sha1,
                "vbmeta_system_sha256": child.sha256,
                "top_level_chain_partitions": list(source_avb.top_level_chain_partitions),
                "top_level_descriptor_partitions": list(top.descriptor_partitions),
                "child_descriptor_partitions": list(source_avb.child_descriptor_partitions),
                "authority": "source-evidence-only",
                "phone_changed": False,
            }
        notes = request["notes"]
        assert isinstance(notes, list)
        notes.extend(
            (
                f"Strict local {source.source_kind} evidence binds protected source {source.source_sha256} and build {source.build_id}.",
                f"The local source blueprint reports {source.partition_count} partition records; exact write, readback, AVB, transition, stock-recovery, and physical-test contracts still require review.",
                (
                    f"OEM source AVB receipt {source_avb.receipt_digest[:16]}… records "
                    f"{top.algorithm} identity and {len(source_avb.top_level_chain_partitions)} "
                    "top-level chains; this does not provide signing keys or an execution policy."
                    if source_avb is not None
                    else "OEM source AVB topology has not yet been attached to this draft."
                ),
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
            "source_avb_evidence",
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
        source_avb_evidence = self._validated_source_avb_evidence(
            request.get("source_avb_evidence"), source_evidence
        )
        source_detail = (
            f"Strict project-local {source_evidence['source_kind']} evidence binds build "
            f"{source_evidence['build_id']} and {source_evidence['partition_count']} observed "
            "partition records; an exact reviewed build contract is still required."
            if source_evidence is not None
            else "No immutable firmware build contract has been reviewed or published."
        )
        partition_detail = (
            f"A source blueprint records {source_evidence['partition_count']} partitions"
            + (
                f" and verified OEM AVB topology records "
                f"{len(source_avb_evidence['top_level_chain_partitions'])} top-level chains, but "
                if source_avb_evidence is not None
                else ", but "
            )
            + "their exact writable artifacts, slots, AVB execution policy, and recovery behavior remain locked pending review."
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
            if source_avb_evidence is not None:
                document["draft_context"]["source_avb_evidence"] = source_avb_evidence
        return document

    def _validated_source_avb_evidence(
        self,
        value: object,
        source_evidence: dict[str, object] | None,
    ) -> dict[str, object] | None:
        if value is None:
            return None
        if source_evidence is None or not isinstance(value, dict):
            raise ValueError("source AVB evidence requires exact project source evidence")
        expected = {
            "project_id",
            "source_sha256",
            "receipt_digest",
            "payload_manifest_digest",
            "signing_identity_consistent",
            "algorithm",
            "public_key_sha1",
            "vbmeta_sha256",
            "vbmeta_system_algorithm",
            "vbmeta_system_public_key_sha1",
            "vbmeta_system_sha256",
            "top_level_chain_partitions",
            "top_level_descriptor_partitions",
            "child_descriptor_partitions",
            "authority",
            "phone_changed",
        }
        chains = _string_list(value.get("top_level_chain_partitions"), "AVB chains")
        top_descriptors = _string_list(
            value.get("top_level_descriptor_partitions"), "top AVB descriptors"
        )
        child_descriptors = _string_list(
            value.get("child_descriptor_partitions"),
            "child AVB descriptors",
            allow_empty=True,
        )
        algorithm = value.get("algorithm")
        public_key = value.get("public_key_sha1")
        child_algorithm = value.get("vbmeta_system_algorithm")
        child_public_key = value.get("vbmeta_system_public_key_sha1")
        consistent = bool(
            algorithm != "NONE"
            and child_algorithm != "NONE"
            and public_key
            and public_key == child_public_key
            and "vbmeta_system" in chains
        )
        if (
            set(value) != expected
            or value.get("project_id") != source_evidence["project_id"]
            or value.get("source_sha256") != source_evidence["source_sha256"]
            or not _sha256(value.get("receipt_digest"))
            or not _sha256(value.get("payload_manifest_digest"))
            or type(value.get("signing_identity_consistent")) is not bool
            or value.get("signing_identity_consistent") != consistent
            or not isinstance(algorithm, str)
            or not 1 <= len(algorithm) <= 80
            or not isinstance(public_key, str)
            or (
                (algorithm == "NONE" and public_key != "")
                or (algorithm != "NONE" and re.fullmatch(r"[0-9a-f]{40}", public_key) is None)
            )
            or not _sha256(value.get("vbmeta_sha256"))
            or not isinstance(child_algorithm, str)
            or not 1 <= len(child_algorithm) <= 80
            or not isinstance(child_public_key, str)
            or (
                (child_algorithm == "NONE" and child_public_key != "")
                or (
                    child_algorithm != "NONE"
                    and re.fullmatch(r"[0-9a-f]{40}", child_public_key) is None
                )
            )
            or not _sha256(value.get("vbmeta_system_sha256"))
            or not chains
            or "vbmeta_system" not in chains
            or not set(chains).issubset(top_descriptors)
            or len(chains) != len(set(chains))
            or len(top_descriptors) != len(set(top_descriptors))
            or len(child_descriptors) != len(set(child_descriptors))
            or any(
                re.fullmatch(r"[A-Za-z0-9._-]{1,80}", name) is None
                for name in (*chains, *top_descriptors, *child_descriptors)
            )
            or value.get("authority") != "source-evidence-only"
            or value.get("phone_changed") is not False
        ):
            raise ValueError("source AVB evidence is incomplete or unsafe")
        return {
            "project_id": value["project_id"],
            "source_sha256": value["source_sha256"],
            "receipt_digest": value["receipt_digest"],
            "payload_manifest_digest": value["payload_manifest_digest"],
            "signing_identity_consistent": value["signing_identity_consistent"],
            "algorithm": algorithm,
            "public_key_sha1": public_key,
            "vbmeta_sha256": value["vbmeta_sha256"],
            "vbmeta_system_algorithm": child_algorithm,
            "vbmeta_system_public_key_sha1": child_public_key,
            "vbmeta_system_sha256": value["vbmeta_system_sha256"],
            "top_level_chain_partitions": list(chains),
            "top_level_descriptor_partitions": list(top_descriptors),
            "child_descriptor_partitions": list(child_descriptors),
            "authority": "source-evidence-only",
            "phone_changed": False,
        }

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

    def load_project_draft(
        self,
        output_dir: Path,
        *,
        boundary: Path,
        project_id: str,
        source_sha256: str,
        blueprint_digest: str,
    ) -> DevicePackDraftReview | None:
        """Find a current exact-source draft without trusting retained UI state."""

        try:
            if output_dir.is_symlink():
                raise ValueError("Device Pack draft directory is unsafe")
            if not output_dir.exists():
                return None
            if not output_dir.is_dir():
                raise ValueError("Device Pack draft path is not a directory")
            candidates = sorted(
                path for path in output_dir.iterdir() if path.name.endswith(".draft.json")
            )
        except OSError as exc:
            raise ValueError(f"Device Pack draft directory is unavailable: {exc}") from exc
        if len(candidates) > 512:
            raise ValueError("Device Pack draft directory exceeds the review limit")

        reviews: list[DevicePackDraftReview] = []
        for path in candidates:
            try:
                if path.is_symlink() or not path.is_file():
                    continue
                document = read_json_object(
                    path,
                    boundary=boundary,
                    maximum_bytes=self.MAXIMUM_REQUEST_BYTES,
                )
                review = self._review_document(path, document)
            except (LocalStoreError, OSError, ValueError):
                continue
            if (
                review.project_id == project_id
                and review.source_sha256 == source_sha256
                and review.blueprint_digest == blueprint_digest
            ):
                reviews.append(review)
        if not reviews:
            return None
        reviews.sort(
            key=lambda item: (
                item.source_avb_attached,
                item.sha256,
            ),
            reverse=True,
        )
        return reviews[0]

    def _review_document(
        self,
        path: Path,
        document: dict[str, object],
    ) -> DevicePackDraftReview:
        expected = {
            "schema_version",
            "publication_status",
            "pack_id",
            "version",
            "display_name",
            "priority",
            "match",
            "knowledge_sources",
            "capabilities",
            "notes",
            "draft_context",
        }
        if (
            set(document) != expected
            or document.get("schema_version") != 1
            or document.get("publication_status") != "draft"
        ):
            raise ValueError("unsupported exact-source Device Pack draft")
        context = document.get("draft_context")
        if not isinstance(context, dict):
            raise ValueError("Device Pack draft context is unavailable")
        source_keys = {
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
        expected_context = source_keys | {
            "status",
            "missing_flash_contracts",
            "execution_authority",
            "phone_action_allowed",
            "public_compatibility_claim",
        }
        if "source_avb_evidence" in context:
            expected_context.add("source_avb_evidence")
        if set(context) != expected_context:
            raise ValueError("Device Pack draft context fields are invalid")
        source = self._validated_source_evidence({key: context[key] for key in source_keys})
        assert source is not None
        source_avb = self._validated_source_avb_evidence(
            context.get("source_avb_evidence"),
            source,
        )
        missing = _string_list(context.get("missing_flash_contracts"), "missing contracts")
        if (
            missing != self.MISSING_FLASH_CONTRACTS
            or context.get("status") != "review-required"
            or context.get("execution_authority") != "none"
            or context.get("phone_action_allowed") is not False
            or context.get("public_compatibility_claim") is not False
        ):
            raise ValueError("Device Pack draft safety boundary is invalid")

        payload = _canonical(document) + b"\n"
        digest = hashlib.sha256(payload).hexdigest()
        pack_document = dict(document)
        pack_document.pop("publication_status")
        pack_document.pop("draft_context")
        pack = DevicePackRegistry._parse(pack_document, digest)
        if path.name != f"{pack.pack_id}-{digest[:12]}.draft.json":
            raise ValueError("Device Pack draft filename does not match its content")
        return DevicePackDraftReview(
            output_path=path,
            sha256=digest,
            pack_id=pack.pack_id,
            display_name=pack.display_name,
            project_id=str(source["project_id"]),
            source_sha256=str(source["source_sha256"]),
            blueprint_digest=str(source["blueprint_digest"]),
            build_id=str(source["build_id"]),
            partition_count=int(source["partition_count"]),
            missing_flash_contracts=missing,
            source_avb_attached=source_avb is not None,
        )


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
