"""Strict local persistence and import for ROMVERSE's offline knowledge archive."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlsplit

from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    ensure_private_directory,
    read_json_object,
    read_regular_bytes,
)
from romverse.knowledge.models import (
    DeviceKnowledgeScope,
    KnowledgeArchive,
    KnowledgeConfidence,
    KnowledgeImportResult,
    KnowledgeKind,
    KnowledgeOperation,
    KnowledgeRecord,
    KnowledgeSource,
    KnowledgeSourceTier,
)


class KnowledgeArchiveError(ValueError):
    """A local knowledge bundle failed its bounded evidence contract."""


ARCHIVE_FORMAT = "romverse.offline-knowledge-archive"
ARCHIVE_SCHEMA_VERSION = 1
MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
MAX_SOURCES = 2_048
MAX_RECORDS = 8_192

_ARCHIVE_FIELDS = {
    "format",
    "schema_version",
    "bundle_id",
    "updated_at",
    "sources",
    "records",
    "bundle_digest",
}
_SOURCE_FIELDS = {
    "source_id",
    "label",
    "publisher",
    "url",
    "tier",
    "scope",
    "reviewed_on",
}
_SCOPE_FIELDS = {
    "manufacturers",
    "brands",
    "models",
    "codenames",
    "build_ids",
    "android_versions",
    "bootloader_states",
    "partitions",
    "scope_note",
}
_OPERATION_FIELDS = {
    "operation_id",
    "label",
    "kind",
    "changes_device",
    "target_partitions",
    "verified_input_requirements",
    "rollback_route",
}
_RECORD_FIELDS = {
    "record_id",
    "revision",
    "title",
    "kind",
    "summary",
    "symptoms",
    "error_codes",
    "finding_ids",
    "diagnostic_steps",
    "fix_steps",
    "prerequisites",
    "expected_outcomes",
    "compatibility",
    "known_incompatibility",
    "recovery_routes",
    "tags",
    "scope",
    "source_ids",
    "confidence",
    "corroboration_count",
    "operations",
}


class KnowledgeArchiveStore:
    """Own one expandable, integrity-checked archive under a ROMVERSE workspace."""

    NAME = "archive.romverse"

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.expanduser().resolve()
        self.root = self.workspace / "knowledge"
        self.path = self.root / self.NAME

    def ensure_seeded(self) -> KnowledgeArchive:
        if self.path.exists() or self.path.is_symlink():
            return self.load()
        archive = load_packaged_archive()
        self.save(archive)
        return archive

    def load(self) -> KnowledgeArchive:
        try:
            raw = read_json_object(
                self.path,
                boundary=self.workspace,
                maximum_bytes=MAX_ARCHIVE_BYTES,
            )
            return parse_archive(raw)
        except (LocalStoreError, OSError, TypeError, ValueError, KeyError) as exc:
            if isinstance(exc, KnowledgeArchiveError):
                raise
            raise KnowledgeArchiveError(f"Offline knowledge archive is unavailable: {exc}") from exc

    def save(self, archive: KnowledgeArchive) -> KnowledgeArchive:
        encoded = json.dumps(
            archive_mapping(seal_archive(archive)),
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        sealed = parse_archive(json.loads(encoded))
        self.workspace.mkdir(parents=True, exist_ok=True)
        ensure_private_directory(self.workspace, boundary=self.workspace)
        ensure_private_directory(self.root, boundary=self.workspace)
        try:
            atomic_write_json(
                self.path,
                archive_mapping(sealed),
                boundary=self.workspace,
                maximum_bytes=MAX_ARCHIVE_BYTES,
            )
        except LocalStoreError as exc:
            raise KnowledgeArchiveError(f"Offline knowledge archive could not be saved: {exc}") from exc
        return sealed

    def import_bundle(self, source: Path) -> KnowledgeImportResult:
        """Merge a strict content-digested bundle; never silently replace equal revisions."""

        unresolved = source.expanduser()
        if unresolved.is_symlink():
            raise KnowledgeArchiveError("Knowledge import cannot be a symbolic link")
        resolved = unresolved.resolve()
        try:
            payload = read_regular_bytes(
                resolved,
                boundary=resolved.parent,
                maximum_bytes=MAX_ARCHIVE_BYTES,
            )
            raw = json.loads(payload.decode("utf-8"))
        except (LocalStoreError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise KnowledgeArchiveError(f"Knowledge import is unavailable: {exc}") from exc
        if not isinstance(raw, dict):
            raise KnowledgeArchiveError("Knowledge import must contain one JSON object")
        incoming = parse_archive(raw)
        current = self.ensure_seeded()
        merged, result = merge_archives(current, incoming)
        saved = self.save(merged)
        return KnowledgeImportResult(
            result.added,
            result.updated,
            result.unchanged,
            len(saved.records),
            saved.bundle_digest,
        )


def load_packaged_archive() -> KnowledgeArchive:
    packaged = (
        "knowledge_archive_seed.json",
        "knowledge_archive_oem_recovery_seed.json",
    )
    archives = tuple(_load_packaged_bundle(name) for name in packaged)
    merged = _existing_catalog_archive()
    for archive in archives:
        merged, _result = merge_archives(merged, archive)
    return merged


def _load_packaged_bundle(name: str) -> KnowledgeArchive:
    resource = files("romverse.assets").joinpath(name)
    try:
        payload = resource.read_bytes()
        if not 0 < len(payload) <= MAX_ARCHIVE_BYTES:
            raise KnowledgeArchiveError("Packaged knowledge archive exceeds its size boundary")
        raw = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KnowledgeArchiveError(f"Packaged knowledge archive is unavailable: {exc}") from exc
    if not isinstance(raw, dict):
        raise KnowledgeArchiveError("Packaged knowledge archive must contain one JSON object")
    return parse_archive(raw)


def archive_mapping(archive: KnowledgeArchive) -> dict[str, object]:
    return {"format": ARCHIVE_FORMAT, **asdict(archive)}


def seal_archive(archive: KnowledgeArchive) -> KnowledgeArchive:
    payload = archive_mapping(archive)
    payload["bundle_digest"] = ""
    digest = _digest_payload(payload)
    return KnowledgeArchive(
        schema_version=archive.schema_version,
        bundle_id=archive.bundle_id,
        updated_at=archive.updated_at,
        sources=archive.sources,
        records=archive.records,
        bundle_digest=digest,
    )


def parse_archive(raw: dict[str, object]) -> KnowledgeArchive:
    _exact_fields(raw, _ARCHIVE_FIELDS, "archive")
    if raw["format"] != ARCHIVE_FORMAT or raw["schema_version"] != ARCHIVE_SCHEMA_VERSION:
        raise KnowledgeArchiveError("Unsupported offline knowledge archive format")
    sources_raw = _object_list(raw["sources"], "sources", MAX_SOURCES)
    records_raw = _object_list(raw["records"], "records", MAX_RECORDS)
    sources = tuple(_parse_source(item) for item in sources_raw)
    records = tuple(_parse_record(item) for item in records_raw)
    archive = KnowledgeArchive(
        schema_version=ARCHIVE_SCHEMA_VERSION,
        bundle_id=_identifier(raw["bundle_id"], "bundle id", 96),
        updated_at=_timestamp(raw["updated_at"], "archive update time"),
        sources=sources,
        records=records,
        bundle_digest=_hex_digest(raw["bundle_digest"], "bundle digest"),
    )
    validate_archive(archive)
    unsigned = dict(raw)
    unsigned["bundle_digest"] = ""
    if archive.bundle_digest != _digest_payload(unsigned):
        raise KnowledgeArchiveError("Offline knowledge archive digest mismatch")
    return archive


def validate_archive(archive: KnowledgeArchive) -> None:
    if archive.schema_version != ARCHIVE_SCHEMA_VERSION:
        raise KnowledgeArchiveError("Unsupported offline knowledge schema")
    if not archive.sources or len(archive.sources) > MAX_SOURCES:
        raise KnowledgeArchiveError("Knowledge source collection is invalid")
    if not archive.records or len(archive.records) > MAX_RECORDS:
        raise KnowledgeArchiveError("Knowledge record collection is invalid")
    source_ids = [source.source_id for source in archive.sources]
    record_ids = [record.record_id for record in archive.records]
    if len(source_ids) != len(set(source_ids)):
        raise KnowledgeArchiveError("Knowledge source identities must be unique")
    if len(record_ids) != len(set(record_ids)):
        raise KnowledgeArchiveError("Knowledge record identities must be unique")
    known_sources = set(source_ids)
    source_by_id = {source.source_id: source for source in archive.sources}
    for record in archive.records:
        if not record.source_ids or not set(record.source_ids) <= known_sources:
            raise KnowledgeArchiveError(f"Knowledge record has unknown provenance: {record.record_id}")
        community_only = all(
            source_by_id[source_id].tier is KnowledgeSourceTier.COMMUNITY
            for source_id in record.source_ids
        )
        if community_only and (
            record.corroboration_count < 1 or not record.scope.scope_note
        ):
            raise KnowledgeArchiveError(
                f"Community knowledge lacks scope or corroboration: {record.record_id}"
            )
        for operation in record.operations:
            _validate_operation_authority(record, operation)


def merge_archives(
    current: KnowledgeArchive,
    incoming: KnowledgeArchive,
) -> tuple[KnowledgeArchive, KnowledgeImportResult]:
    validate_archive(current)
    validate_archive(incoming)
    sources = {source.source_id: source for source in current.sources}
    for source in incoming.sources:
        existing = sources.get(source.source_id)
        if existing is not None and existing != source:
            raise KnowledgeArchiveError(
                f"Knowledge source identity conflicts with local provenance: {source.source_id}"
            )
        sources[source.source_id] = source

    records = {record.record_id: record for record in current.records}
    added = updated = unchanged = 0
    for record in incoming.records:
        existing = records.get(record.record_id)
        if existing is None:
            records[record.record_id] = record
            added += 1
        elif record.revision < existing.revision:
            raise KnowledgeArchiveError(
                f"Knowledge import would downgrade record: {record.record_id}"
            )
        elif record.revision == existing.revision:
            if record != existing:
                raise KnowledgeArchiveError(
                    f"Knowledge record revision conflicts with local content: {record.record_id}"
                )
            unchanged += 1
        else:
            records[record.record_id] = record
            updated += 1
    merged = KnowledgeArchive(
        schema_version=ARCHIVE_SCHEMA_VERSION,
        bundle_id="local-offline-archive",
        updated_at=max(current.updated_at, incoming.updated_at),
        sources=tuple(sources[key] for key in sorted(sources)),
        records=tuple(records[key] for key in sorted(records)),
        bundle_digest="",
    )
    merged = seal_archive(merged)
    validate_archive(merged)
    return merged, KnowledgeImportResult(
        added,
        updated,
        unchanged,
        len(merged.records),
        merged.bundle_digest,
    )


def _parse_source(raw: dict[str, object]) -> KnowledgeSource:
    _exact_fields(raw, _SOURCE_FIELDS, "source")
    try:
        tier = KnowledgeSourceTier(raw["tier"])
    except (TypeError, ValueError) as exc:
        raise KnowledgeArchiveError("Knowledge source tier is invalid") from exc
    url = _optional_text(raw["url"], "source URL", 500)
    if url:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise KnowledgeArchiveError("Knowledge source URL must be a public HTTPS document")
    elif tier is not KnowledgeSourceTier.ROMVERSE_VERIFIED:
        raise KnowledgeArchiveError("External knowledge provenance requires an HTTPS source URL")
    reviewed_on = _text(raw["reviewed_on"], "source review date", 10)
    try:
        datetime.strptime(reviewed_on, "%Y-%m-%d")
    except ValueError as exc:
        raise KnowledgeArchiveError("Knowledge source review date is invalid") from exc
    return KnowledgeSource(
        source_id=_identifier(raw["source_id"], "source id", 96),
        label=_text(raw["label"], "source label", 180),
        publisher=_text(raw["publisher"], "source publisher", 120),
        url=url,
        tier=tier,
        scope=_text(raw["scope"], "source scope", 500),
        reviewed_on=reviewed_on,
    )


def _parse_scope(raw: object) -> DeviceKnowledgeScope:
    if not isinstance(raw, dict):
        raise KnowledgeArchiveError("Knowledge device scope must be an object")
    _exact_fields(raw, _SCOPE_FIELDS, "device scope")
    return DeviceKnowledgeScope(
        manufacturers=_strings(raw["manufacturers"], "manufacturers", 64, 120),
        brands=_strings(raw["brands"], "brands", 64, 120),
        models=_strings(raw["models"], "models", 256, 160),
        codenames=_strings(raw["codenames"], "codenames", 256, 120),
        build_ids=_strings(raw["build_ids"], "build ids", 512, 180),
        android_versions=_strings(raw["android_versions"], "Android versions", 64, 80),
        bootloader_states=_strings(raw["bootloader_states"], "bootloader states", 16, 80),
        partitions=_strings(raw["partitions"], "partitions", 256, 120),
        scope_note=_text(raw["scope_note"], "scope note", 600),
    )


def _parse_operation(raw: dict[str, object]) -> KnowledgeOperation:
    _exact_fields(raw, _OPERATION_FIELDS, "operation")
    if type(raw["changes_device"]) is not bool:
        raise KnowledgeArchiveError("Knowledge operation device-change flag is invalid")
    return KnowledgeOperation(
        operation_id=_identifier(raw["operation_id"], "operation id", 96),
        label=_text(raw["label"], "operation label", 180),
        kind=_identifier(raw["kind"], "operation kind", 96),
        changes_device=raw["changes_device"],
        target_partitions=_strings(raw["target_partitions"], "target partitions", 64, 120),
        verified_input_requirements=_strings(
            raw["verified_input_requirements"], "verified input requirements", 32, 120
        ),
        rollback_route=_optional_text(raw["rollback_route"], "rollback route", 240),
    )


def _parse_record(raw: dict[str, object]) -> KnowledgeRecord:
    _exact_fields(raw, _RECORD_FIELDS, "record")
    try:
        kind = KnowledgeKind(raw["kind"])
        confidence = KnowledgeConfidence(raw["confidence"])
    except (TypeError, ValueError) as exc:
        raise KnowledgeArchiveError("Knowledge record classification is invalid") from exc
    revision = raw["revision"]
    corroboration = raw["corroboration_count"]
    if type(revision) is not int or not 1 <= revision <= 1_000_000:
        raise KnowledgeArchiveError("Knowledge record revision is invalid")
    if type(corroboration) is not int or not 0 <= corroboration <= 1_000_000:
        raise KnowledgeArchiveError("Knowledge corroboration count is invalid")
    operations_raw = _object_list(raw["operations"], "operations", 32)
    operations = tuple(_parse_operation(item) for item in operations_raw)
    if len({item.operation_id for item in operations}) != len(operations):
        raise KnowledgeArchiveError("Knowledge operation identities must be unique")
    return KnowledgeRecord(
        record_id=_identifier(raw["record_id"], "record id", 96),
        revision=revision,
        title=_text(raw["title"], "record title", 180),
        kind=kind,
        summary=_text(raw["summary"], "record summary", 2_000),
        symptoms=_strings(raw["symptoms"], "symptoms", 64, 500),
        error_codes=_strings(raw["error_codes"], "error codes", 64, 240),
        finding_ids=_strings(raw["finding_ids"], "finding ids", 64, 120),
        diagnostic_steps=_strings(raw["diagnostic_steps"], "diagnostic steps", 64, 800),
        fix_steps=_strings(raw["fix_steps"], "fix steps", 64, 800),
        prerequisites=_strings(raw["prerequisites"], "prerequisites", 64, 800),
        expected_outcomes=_strings(raw["expected_outcomes"], "expected outcomes", 64, 800),
        compatibility=_strings(raw["compatibility"], "compatibility", 64, 800),
        known_incompatibility=_strings(
            raw["known_incompatibility"], "known incompatibility", 64, 800
        ),
        recovery_routes=_strings(raw["recovery_routes"], "recovery routes", 64, 800),
        tags=_strings(raw["tags"], "tags", 128, 240),
        scope=_parse_scope(raw["scope"]),
        source_ids=_strings(raw["source_ids"], "source ids", 32, 96),
        confidence=confidence,
        corroboration_count=corroboration,
        operations=operations,
    )


def _validate_operation_authority(
    record: KnowledgeRecord,
    operation: KnowledgeOperation,
) -> None:
    if not operation.changes_device:
        if operation.verified_input_requirements or operation.rollback_route:
            raise KnowledgeArchiveError(
                f"Read-only operation claims write authority metadata: {operation.operation_id}"
            )
        return
    exact_target = bool(record.scope.models or record.scope.codenames)
    exact_build = bool(record.scope.build_ids)
    exact_partitions = bool(operation.target_partitions) and set(
        _normalized_values(operation.target_partitions)
    ) <= set(_normalized_values(record.scope.partitions))
    if not (
        exact_target
        and exact_build
        and exact_partitions
        and operation.verified_input_requirements
        and operation.rollback_route
    ):
        raise KnowledgeArchiveError(
            f"Device-changing knowledge lacks exact target/build/partition/input/rollback evidence: "
            f"{operation.operation_id}"
        )


def _exact_fields(raw: dict[str, object], expected: set[str], label: str) -> None:
    if set(raw) != expected:
        raise KnowledgeArchiveError(f"Knowledge {label} fields do not match schema")


def _object_list(value: object, label: str, maximum: int) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list) or len(value) > maximum:
        raise KnowledgeArchiveError(f"Knowledge {label} collection is invalid")
    if any(not isinstance(item, dict) for item in value):
        raise KnowledgeArchiveError(f"Knowledge {label} entries must be objects")
    return tuple(value)  # type: ignore[return-value]


def _strings(value: object, label: str, maximum: int, text_limit: int) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum:
        raise KnowledgeArchiveError(f"Knowledge {label} collection is invalid")
    result = tuple(_text(item, label, text_limit) for item in value)
    normalized = _normalized_values(result)
    if len(normalized) != len(set(normalized)):
        raise KnowledgeArchiveError(f"Knowledge {label} entries must be unique")
    return result


def _normalized_values(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(" ".join(value.casefold().split()) for value in values)


def _identifier(value: object, label: str, maximum: int) -> str:
    text = _text(value, label, maximum)
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", text):
        raise KnowledgeArchiveError(f"Knowledge {label} is invalid")
    return text


def _text(value: object, label: str, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or any(ord(char) < 32 and char not in "\n\t" for char in value)
    ):
        raise KnowledgeArchiveError(f"Knowledge {label} is invalid")
    return value.strip()


def _optional_text(value: object, label: str, maximum: int) -> str:
    if value == "":
        return ""
    return _text(value, label, maximum)


def _timestamp(value: object, label: str) -> str:
    text = _text(value, label, 80)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise KnowledgeArchiveError(f"Knowledge {label} is invalid") from exc
    if parsed.tzinfo is None:
        raise KnowledgeArchiveError(f"Knowledge {label} requires a timezone")
    return text


def _hex_digest(value: object, label: str) -> str:
    text = _text(value, label, 64)
    if not re.fullmatch(r"[0-9a-f]{64}", text):
        raise KnowledgeArchiveError(f"Knowledge {label} is invalid")
    return text


def _digest_payload(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _existing_catalog_archive() -> KnowledgeArchive:
    """Promote the already-curated Archives corpus without granting it new authority."""

    from romverse.knowledge.archives import KNOWN_FIXES, source_lane

    sources: dict[str, KnowledgeSource] = {}
    records: list[KnowledgeRecord] = []
    for article in KNOWN_FIXES:
        source_payload = "\0".join(
            (
                article.source.label,
                article.source.authority,
                article.source.url,
                article.source.reviewed_on,
            )
        )
        source_id = "catalog-source." + hashlib.sha256(source_payload.encode()).hexdigest()[:20]
        lane = source_lane(article.source)
        if lane == "official":
            tier = (
                KnowledgeSourceTier.OFFICIAL_PLATFORM
                if "AOSP" in article.source.authority.upper()
                or "ANDROID" in article.source.authority.upper()
                else KnowledgeSourceTier.OFFICIAL_VENDOR
            )
        elif lane == "community":
            tier = KnowledgeSourceTier.COMMUNITY
        else:
            tier = KnowledgeSourceTier.ROMVERSE_VERIFIED
        sources[source_id] = KnowledgeSource(
            source_id=source_id,
            label=article.source.label,
            publisher=article.source.authority,
            url=article.source.url,
            tier=tier,
            scope=article.evidence,
            reviewed_on=article.source.reviewed_on,
        )
        manufacturer = _manufacturer_scope(article.key)
        partitions = _partition_scope(" ".join((article.title, *article.tags)))
        kind = (
            KnowledgeKind.RECOVERY
            if article.route in {"recovery_bay", "time_machine"}
            else KnowledgeKind.DIAGNOSIS
            if article.route in {"quantum_optimizer", "health_timeline", "command_deck"}
            else KnowledgeKind.GUIDE
        )
        confidence = (
            KnowledgeConfidence.HIGH
            if tier
            in {
                KnowledgeSourceTier.OFFICIAL_PLATFORM,
                KnowledgeSourceTier.OFFICIAL_VENDOR,
                KnowledgeSourceTier.ROMVERSE_VERIFIED,
            }
            else KnowledgeConfidence.LOW
        )
        records.append(
            KnowledgeRecord(
                record_id=f"catalog.{article.key}",
                revision=1,
                title=article.title,
                kind=kind,
                summary=article.meaning,
                symptoms=article.tags,
                error_codes=tuple(
                    tag
                    for tag in article.tags
                    if re.fullmatch(r"[A-Z][A-Z0-9_ -]{3,100}", tag)
                ),
                finding_ids=(),
                diagnostic_steps=article.checks,
                fix_steps=article.fix_steps,
                prerequisites=(),
                expected_outcomes=article.verification,
                compatibility=(),
                known_incompatibility=(),
                recovery_routes=(),
                tags=article.tags,
                scope=DeviceKnowledgeScope(
                    manufacturers=(manufacturer,) if manufacturer else (),
                    partitions=partitions,
                    scope_note=(
                        "Device/build-scoped community report; confirm the exact target and build."
                        if tier is KnowledgeSourceTier.COMMUNITY
                        else "Broad sourced guidance; exact device/build applicability remains required."
                    ),
                ),
                source_ids=(source_id,),
                confidence=confidence,
                corroboration_count=1,
                operations=(),
            )
        )
    archive = KnowledgeArchive(
        schema_version=ARCHIVE_SCHEMA_VERSION,
        bundle_id="romverse-curated-catalog",
        updated_at="2026-09-04T00:00:00+00:00",
        sources=tuple(sources[key] for key in sorted(sources)),
        records=tuple(sorted(records, key=lambda item: item.record_id)),
        bundle_digest="",
    )
    archive = seal_archive(archive)
    validate_archive(archive)
    return archive


def _manufacturer_scope(record_id: str) -> str:
    manufacturers = {
        "asus-": "asus",
        "fairphone-": "fairphone",
        "hmd-": "hmd",
        "honor-": "honor",
        "huawei-": "huawei",
        "infinix-": "infinix",
        "itel-": "itel",
        "motorola-": "motorola",
        "nothing-": "nothing",
        "nubia-": "nubia",
        "oneplus-": "oneplus",
        "oppo-": "oppo",
        "pixel-": "google",
        "realme-": "realme",
        "samsung-": "samsung",
        "sony-": "sony",
        "tecno-": "tecno",
        "vivo-": "vivo",
        "xiaomi-": "xiaomi",
        "zte-": "zte",
    }
    return next(
        (manufacturer for prefix, manufacturer in manufacturers.items() if record_id.startswith(prefix)),
        "",
    )


def _partition_scope(document: str) -> tuple[str, ...]:
    normalized = document.casefold()
    known = (
        "boot",
        "init_boot",
        "vendor_boot",
        "recovery",
        "vbmeta",
        "system",
        "system_ext",
        "product",
        "vendor",
        "odm",
        "super",
        "userdata",
    )
    return tuple(
        partition
        for partition in known
        if re.search(rf"(?<![a-z0-9_]){re.escape(partition)}(?![a-z0-9_])", normalized)
    )
