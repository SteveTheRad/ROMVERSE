"""Query-only evidence acquisition from Google's fixed public device catalog."""

from __future__ import annotations

import csv
import hashlib
import http.client
import io
import json
import re
import time
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, fields, replace
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    ensure_private_directory,
    read_json_object,
)
from romverse.knowledge.online_evidence import (
    EvidenceConsumer,
    EvidenceFreshness,
    EvidenceProjection,
    EvidenceScope,
    EvidenceSourceRegistry,
    EvidenceState,
    OnlineEvidenceError,
    OnlineEvidenceStore,
    SourceCategory,
    create_claim,
    freshness_at,
    project_evidence,
    scrub_private_text,
)

GOOGLE_PLAY_CATALOG_URL = "https://storage.googleapis.com/play_public/supported_devices.csv"
PARSER_ID = "romverse.google-play-supported-devices"
PARSER_VERSION = "1"


class CatalogAcquisitionError(ValueError):
    """The fixed catalog acquisition or its receipt failed a bounded contract."""


class AcquisitionOutcome(StrEnum):
    SUCCESS = "success"
    NO_EXACT_MATCH = "no-exact-match"
    HTTP_FAILURE = "http-failure"
    VALIDATION_FAILURE = "validation-failure"
    CACHE_NOT_MODIFIED = "cache-not-modified"


@dataclass(frozen=True, slots=True)
class CatalogLookup:
    manufacturer: str
    model: str
    codename: str
    lookup_digest: str


@dataclass(frozen=True, slots=True)
class CatalogRequest:
    url: str
    headers: tuple[tuple[str, str], ...]
    connect_timeout_seconds: float
    read_timeout_seconds: float
    overall_timeout_seconds: float
    maximum_bytes: int

    def __post_init__(self) -> None:
        headers = dict(self.headers)
        allowed = {
            "Accept",
            "Accept-Encoding",
            "User-Agent",
            "If-None-Match",
            "If-Modified-Since",
        }
        if (
            self.url != GOOGLE_PLAY_CATALOG_URL
            or len(headers) != len(self.headers)
            or set(headers) - allowed
            or headers.get("Accept") != "text/csv"
            or headers.get("Accept-Encoding") != "identity"
            or headers.get("User-Agent") != GooglePlayEvidenceAcquirer.USER_AGENT
            or any(not _safe_header(value) and value for value in headers.values())
            or not 0 < self.connect_timeout_seconds <= 15
            or not 0 < self.read_timeout_seconds <= 20
            or not 0 < self.overall_timeout_seconds <= 60
            or self.maximum_bytes < 1
            or self.maximum_bytes > 16 * 1024 * 1024
        ):
            raise CatalogAcquisitionError("Catalog request violates the fixed transport contract")


@dataclass(frozen=True, slots=True)
class CatalogResponse:
    status: int
    final_url: str
    headers: Mapping[str, str]
    body: bytes


class CatalogTransport(Protocol):
    def fetch(self, request: CatalogRequest) -> CatalogResponse: ...


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    manufacturer: str
    marketing_name: str
    codename: str
    model: str


@dataclass(frozen=True, slots=True)
class CatalogAcquisitionReceipt:
    schema_version: int
    receipt_id: str
    lookup: CatalogLookup
    source_url: str
    retrieved_at: str
    outcome: AcquisitionOutcome
    reason: str
    http_status: int
    content_bytes: int
    parsed_row_count: int
    content_digest: str
    etag: str
    last_modified: str
    parser_id: str
    parser_version: str
    matched_claim_ids: tuple[str, ...]
    retained_claim_ids: tuple[str, ...]
    evidence_archive_digest: str
    previous_receipt_digest: str
    receipt_digest: str
    compatibility_hint: str = "UNCONFIRMED"
    execution_authority: str = "none"
    phone_action_allowed: bool = False
    guardian_approval: bool = False
    bootloader_relock_allowed: bool = False
    raw_response_retained: bool = False


class FixedGooglePlayHTTPS:
    """No-redirect HTTPS transport for exactly one public source."""

    CHUNK_BYTES = 128 * 1024

    def __init__(self, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._monotonic = monotonic

    def fetch(self, request: CatalogRequest) -> CatalogResponse:
        if request.url != GOOGLE_PLAY_CATALOG_URL:
            raise CatalogAcquisitionError("Catalog transport accepts only the exact official URL")
        parsed = urlsplit(request.url)
        started = self._monotonic()
        connection = http.client.HTTPSConnection(
            parsed.hostname,
            port=443,
            timeout=min(request.connect_timeout_seconds, request.overall_timeout_seconds),
        )
        try:
            connection.request("GET", parsed.path, headers=dict(request.headers))
            response = connection.getresponse()
            chunks: list[bytes] = []
            total = 0
            while True:
                remaining = request.overall_timeout_seconds - (self._monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError("Official catalog overall timeout expired")
                if connection.sock is not None:
                    connection.sock.settimeout(min(request.read_timeout_seconds, remaining))
                chunk = response.read(self.CHUNK_BYTES)
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > request.maximum_bytes:
                    raise CatalogAcquisitionError("Official catalog exceeded its response boundary")
            return CatalogResponse(
                response.status,
                request.url,
                {name.casefold(): value for name, value in response.getheaders()},
                b"".join(chunks),
            )
        except TimeoutError as exc:
            raise TimeoutError("Official catalog request timed out") from exc
        finally:
            connection.close()


class CatalogReceiptStore:
    FORMAT = "romverse.google-play-evidence-acquisition"
    SCHEMA_VERSION = 1
    MAXIMUM_BYTES = 32 * 1024

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.expanduser().resolve()
        self.root = self.workspace / "knowledge" / "online-device-evidence" / "acquisitions"

    def path_for(self, lookup_digest: str) -> Path:
        return self.root / f"google-play-{_digest(lookup_digest)}.romverse"

    def load(self, lookup_digest: str) -> CatalogAcquisitionReceipt | None:
        path = self.path_for(lookup_digest)
        if not path.exists():
            return None
        try:
            raw = read_json_object(
                path,
                boundary=self.workspace,
                maximum_bytes=self.MAXIMUM_BYTES,
            )
            return parse_receipt(raw)
        except (LocalStoreError, OSError, TypeError, ValueError, KeyError) as exc:
            if isinstance(exc, CatalogAcquisitionError):
                raise
            raise CatalogAcquisitionError(
                f"Catalog acquisition receipt is unavailable: {exc}"
            ) from exc

    def save(self, receipt: CatalogAcquisitionReceipt) -> CatalogAcquisitionReceipt:
        sealed = seal_receipt(receipt)
        mapping = receipt_mapping(sealed)
        parse_receipt(json.loads(json.dumps(mapping, allow_nan=False)))
        self.workspace.mkdir(parents=True, exist_ok=True)
        ensure_private_directory(self.workspace, boundary=self.workspace)
        ensure_private_directory(self.workspace / "knowledge", boundary=self.workspace)
        ensure_private_directory(
            self.workspace / "knowledge" / "online-device-evidence",
            boundary=self.workspace,
        )
        ensure_private_directory(self.root, boundary=self.workspace)
        try:
            atomic_write_json(
                self.path_for(sealed.lookup.lookup_digest),
                mapping,
                boundary=self.workspace,
                maximum_bytes=self.MAXIMUM_BYTES,
            )
        except LocalStoreError as exc:
            raise CatalogAcquisitionError("Catalog receipt could not be stored safely") from exc
        loaded = self.load(sealed.lookup.lookup_digest)
        if loaded != sealed:
            raise CatalogAcquisitionError("Catalog receipt changed during save verification")
        return loaded


class GooglePlayEvidenceAcquirer:
    MAXIMUM_BYTES = 16 * 1024 * 1024
    MAXIMUM_ROWS = 100_000
    MAXIMUM_FIELD_CHARS = 160
    CONNECT_TIMEOUT_SECONDS = 8.0
    READ_TIMEOUT_SECONDS = 12.0
    OVERALL_TIMEOUT_SECONDS = 30.0
    MINIMUM_INTERVAL_SECONDS = 2.0
    USER_AGENT = "ROMVERSE/0.2 query-only-device-evidence"
    HEADER = ("Retail Branding", "Marketing Name", "Device", "Model")

    def __init__(
        self,
        workspace: Path,
        *,
        registry: EvidenceSourceRegistry | None = None,
        transport: CatalogTransport | None = None,
    ) -> None:
        self.workspace = workspace.expanduser().resolve()
        self.registry = registry or EvidenceSourceRegistry()
        self.adapter = self.registry.resolve(GOOGLE_PLAY_CATALOG_URL)
        if self.adapter.parser_id != PARSER_ID or self.adapter.parser_version != PARSER_VERSION:
            raise CatalogAcquisitionError("Google Play evidence parser registration is invalid")
        self.transport = transport or FixedGooglePlayHTTPS()
        self.receipts = CatalogReceiptStore(self.workspace)
        self.evidence = OnlineEvidenceStore(self.workspace)

    def acquire(
        self,
        manufacturer: str,
        model: str,
        codename: str,
        *,
        now: datetime | None = None,
    ) -> CatalogAcquisitionReceipt:
        retrieved = _aware(now or datetime.now(UTC))
        try:
            lookup = create_lookup(manufacturer, model, codename)
        except CatalogAcquisitionError:
            lookup = _rejected_lookup()
            return self._record(
                lookup,
                retrieved,
                AcquisitionOutcome.VALIDATION_FAILURE,
                "Lookup input was rejected by the privacy and shape boundary.",
            )

        previous = self.receipts.load(lookup.lookup_digest)
        if previous is not None:
            previous_time = datetime.fromisoformat(previous.retrieved_at)
            elapsed = (retrieved - previous_time).total_seconds()
            if elapsed < max(self.MINIMUM_INTERVAL_SECONDS, self.adapter.minimum_interval_seconds):
                return self._record(
                    lookup,
                    retrieved,
                    AcquisitionOutcome.VALIDATION_FAILURE,
                    "Minimum request spacing has not elapsed.",
                    previous=previous,
                )

        headers = {
            "Accept": "text/csv",
            "Accept-Encoding": "identity",
            "User-Agent": self.USER_AGENT,
        }
        if previous is not None and previous.content_digest and previous.etag:
            headers["If-None-Match"] = previous.etag
        if previous is not None and previous.content_digest and previous.last_modified:
            headers["If-Modified-Since"] = previous.last_modified
        request = CatalogRequest(
            GOOGLE_PLAY_CATALOG_URL,
            tuple(sorted(headers.items())),
            self.CONNECT_TIMEOUT_SECONDS,
            self.READ_TIMEOUT_SECONDS,
            self.OVERALL_TIMEOUT_SECONDS,
            self.MAXIMUM_BYTES,
        )
        try:
            response = self.transport.fetch(request)
        except CatalogAcquisitionError as exc:
            return self._record(
                lookup,
                retrieved,
                AcquisitionOutcome.VALIDATION_FAILURE,
                f"Official catalog transport validation failed: {_bounded_failure(exc)}",
                previous=previous,
            )
        except (OSError, TimeoutError, http.client.HTTPException) as exc:
            return self._record(
                lookup,
                retrieved,
                AcquisitionOutcome.HTTP_FAILURE,
                f"Official catalog request failed: {type(exc).__name__}.",
                previous=previous,
            )

        try:
            if (
                not isinstance(response, CatalogResponse)
                or isinstance(response.status, bool)
                or not isinstance(response.status, int)
                or not 100 <= response.status <= 599
                or not isinstance(response.headers, Mapping)
                or not isinstance(response.body, bytes)
                or not isinstance(response.final_url, str)
            ):
                raise CatalogAcquisitionError("Official catalog response shape is invalid")
            etag = _header(response.headers, "etag")
            last_modified = _header(response.headers, "last-modified")
        except CatalogAcquisitionError as exc:
            return self._record(
                lookup,
                retrieved,
                AcquisitionOutcome.VALIDATION_FAILURE,
                f"Official catalog response validation failed: {_bounded_failure(exc)}",
                previous=previous,
            )
        if response.status == 304:
            if previous is None or not previous.content_digest:
                return self._record(
                    lookup,
                    retrieved,
                    AcquisitionOutcome.VALIDATION_FAILURE,
                    "Cache-not-modified response had no prior validated evidence.",
                    http_status=304,
                )
            return self._record(
                lookup,
                retrieved,
                AcquisitionOutcome.CACHE_NOT_MODIFIED,
                "The exact official source reports the prior validated content is unchanged.",
                http_status=304,
                content_digest=previous.content_digest,
                etag=etag or previous.etag,
                last_modified=last_modified or previous.last_modified,
                retained_claim_ids=previous.retained_claim_ids,
                archive_digest=previous.evidence_archive_digest,
                previous=previous,
            )
        if response.status != 200:
            return self._record(
                lookup,
                retrieved,
                AcquisitionOutcome.HTTP_FAILURE,
                f"Official catalog returned HTTP {response.status}.",
                http_status=response.status,
                etag=etag,
                last_modified=last_modified,
                retained_claim_ids=(),
                archive_digest="",
                previous=previous,
            )

        try:
            content_type = _header(response.headers, "content-type")
            content_encoding = _header(response.headers, "content-encoding") or "identity"
            if not 0 < len(response.body) <= self.MAXIMUM_BYTES:
                raise CatalogAcquisitionError("Official catalog body exceeds its response boundary")
            digest = self.adapter.validate_content(
                response.body,
                requested_url=GOOGLE_PLAY_CATALOG_URL,
                final_url=response.final_url,
                status=response.status,
                content_type=content_type,
                content_encoding=content_encoding,
            )
            declared = _content_length(response.headers)
            if declared is not None and declared != len(response.body):
                raise CatalogAcquisitionError("Official catalog response was truncated")
            entries = self._parse(response.body, lookup)
            matches = self._match(entries, lookup)
        except (CatalogAcquisitionError, OnlineEvidenceError, UnicodeError, csv.Error) as exc:
            return self._record(
                lookup,
                retrieved,
                AcquisitionOutcome.VALIDATION_FAILURE,
                f"Official catalog validation failed: {_bounded_failure(exc)}",
                http_status=200,
                content_bytes=(
                    len(response.body) if len(response.body) <= self.MAXIMUM_BYTES else 0
                ),
                etag=etag,
                last_modified=last_modified,
                previous=previous,
            )

        if len(matches) != 1:
            reason = (
                "No exact official manufacturer/model/codename identity was found."
                if not matches
                else "The exact lookup is ambiguous; ROMVERSE will not choose by row order."
            )
            return self._record(
                lookup,
                retrieved,
                AcquisitionOutcome.NO_EXACT_MATCH,
                reason,
                http_status=200,
                content_bytes=len(response.body),
                parsed_rows=len(entries),
                content_digest=digest,
                etag=etag,
                last_modified=last_modified,
                previous=previous,
            )

        published = _http_date(last_modified)
        freshness = (
            freshness_at(published, retrieved, self.adapter.freshness_days)
            if published
            else EvidenceFreshness.UNCONFIRMED
        )
        claims = self._claims(matches[0], lookup, retrieved, published, freshness, digest)
        archive = self.evidence.merge(claims, now=retrieved)
        claim_ids = tuple(claim.claim_id for claim in claims)
        return self._record(
            lookup,
            retrieved,
            AcquisitionOutcome.SUCCESS,
            "One exact official retail identity matched; compatibility remains unconfirmed.",
            http_status=200,
            content_bytes=len(response.body),
            parsed_rows=len(entries),
            content_digest=digest,
            etag=etag,
            last_modified=last_modified,
            matched_claim_ids=claim_ids,
            retained_claim_ids=claim_ids,
            archive_digest=archive.archive_digest,
            previous=previous,
        )

    def projections(self, receipt: CatalogAcquisitionReceipt) -> tuple[EvidenceProjection, ...]:
        if receipt.lookup.lookup_digest != _lookup_digest(receipt.lookup):
            raise CatalogAcquisitionError("Projection lookup binding is invalid")
        if not receipt.retained_claim_ids:
            return tuple(
                project_evidence((), consumer)
                for consumer in (
                    EvidenceConsumer.DEVICE_DNA,
                    EvidenceConsumer.COMPATIBILITY_MATRIX,
                    EvidenceConsumer.KNOWLEDGE_ARCHIVES,
                )
            )
        archive = self.evidence.load()
        retained = set(receipt.retained_claim_ids)
        claims = tuple(claim for claim in archive.claims if claim.claim_id in retained)
        if len(claims) != len(retained):
            raise CatalogAcquisitionError("Projection claims are no longer available")
        return tuple(
            project_evidence(claims, consumer)
            for consumer in (
                EvidenceConsumer.DEVICE_DNA,
                EvidenceConsumer.COMPATIBILITY_MATRIX,
                EvidenceConsumer.KNOWLEDGE_ARCHIVES,
            )
        )

    def _parse(self, payload: bytes, lookup: CatalogLookup) -> tuple[CatalogEntry, ...]:
        if not payload.startswith(b"\xff\xfe"):
            raise CatalogAcquisitionError("Official catalog encoding marker is invalid")
        decoded = payload.decode("utf-16")
        reader = csv.reader(io.StringIO(decoded, newline=""), strict=True)
        try:
            header = tuple(next(reader))
        except StopIteration as exc:
            raise CatalogAcquisitionError("Official catalog is empty") from exc
        if header != self.HEADER:
            raise CatalogAcquisitionError("Official catalog columns are invalid")
        entries: list[CatalogEntry] = []
        seen: set[CatalogEntry] = set()
        for row in reader:
            if len(row) != len(self.HEADER):
                raise CatalogAcquisitionError("Official catalog row shape is invalid")
            entry = CatalogEntry(*(_catalog_text(value, self.MAXIMUM_FIELD_CHARS) for value in row))
            if not any((entry.manufacturer, entry.marketing_name, entry.codename, entry.model)):
                raise CatalogAcquisitionError("Official catalog contains an empty data row")
            if entry in seen:
                if self._entry_matches(entry, lookup):
                    raise CatalogAcquisitionError(
                        "Official catalog contains a duplicate row for the exact lookup"
                    )
                continue
            seen.add(entry)
            entries.append(entry)
            if len(entries) > self.MAXIMUM_ROWS:
                raise CatalogAcquisitionError("Official catalog exceeds its parsed-row boundary")
        if not entries:
            raise CatalogAcquisitionError("Official catalog contains no data rows")
        return tuple(entries)

    @staticmethod
    def _match(
        entries: tuple[CatalogEntry, ...], lookup: CatalogLookup
    ) -> tuple[CatalogEntry, ...]:
        return tuple(
            entry for entry in entries if GooglePlayEvidenceAcquirer._entry_matches(entry, lookup)
        )

    @staticmethod
    def _entry_matches(entry: CatalogEntry, lookup: CatalogLookup) -> bool:
        return bool(
            _key(entry.manufacturer) == lookup.manufacturer
            and _key(entry.model) == lookup.model
            and _key(entry.codename) == lookup.codename
            and entry.marketing_name
        )

    def _claims(
        self,
        entry: CatalogEntry,
        lookup: CatalogLookup,
        retrieved: datetime,
        published: datetime | None,
        freshness: EvidenceFreshness,
        digest: str,
    ):
        scope = EvidenceScope(
            manufacturers=(lookup.manufacturer,),
            models=(lookup.model,),
            codenames=(lookup.codename,),
            scope_note="Exact Google Play manufacturer/model/device-codename lookup.",
        )
        values = (
            ("device.identity.manufacturer", entry.manufacturer),
            ("device.identity.marketing-name", entry.marketing_name),
            ("device.identity.codename", entry.codename),
            ("device.identity.model", entry.model),
        )
        return tuple(
            create_claim(
                claim_key=key,
                scope=scope,
                source_id=self.adapter.adapter_id,
                url=GOOGLE_PLAY_CATALOG_URL,
                publisher=self.adapter.publisher,
                category=SourceCategory.OFFICIAL_ANDROID,
                retrieved_at=retrieved,
                published_at=published,
                freshness=freshness,
                content_digest=digest,
                parser_id=PARSER_ID,
                parser_version=PARSER_VERSION,
                structured_value=value,
                state=EvidenceState.OFFICIALLY_DOCUMENTED,
                confidence=90,
                status_reason=(
                    "Exact public retail identity only; no firmware, compatibility, or execution authority."
                ),
            )
            for key, value in values
        )

    def _record(
        self,
        lookup: CatalogLookup,
        retrieved: datetime,
        outcome: AcquisitionOutcome,
        reason: str,
        *,
        http_status: int = 0,
        content_bytes: int = 0,
        parsed_rows: int = 0,
        content_digest: str = "",
        etag: str = "",
        last_modified: str = "",
        matched_claim_ids: tuple[str, ...] = (),
        retained_claim_ids: tuple[str, ...] | None = None,
        archive_digest: str | None = None,
        previous: CatalogAcquisitionReceipt | None = None,
    ) -> CatalogAcquisitionReceipt:
        retained = (
            retained_claim_ids
            if retained_claim_ids is not None
            else (previous.retained_claim_ids if previous else ())
        )
        archive = (
            archive_digest
            if archive_digest is not None
            else (previous.evidence_archive_digest if retained and previous else "")
        )
        cached_digest = content_digest or (
            previous.content_digest if retained and previous is not None else ""
        )
        receipt = CatalogAcquisitionReceipt(
            1,
            "0" * 64,
            lookup,
            GOOGLE_PLAY_CATALOG_URL,
            retrieved.isoformat(),
            outcome,
            scrub_private_text(reason),
            http_status,
            content_bytes,
            parsed_rows,
            cached_digest,
            _safe_header(etag or (previous.etag if previous else "")),
            _safe_header(last_modified or (previous.last_modified if previous else "")),
            PARSER_ID,
            PARSER_VERSION,
            tuple(sorted(matched_claim_ids)),
            tuple(sorted(retained)),
            archive,
            "",
            "",
        )
        return self.receipts.save(receipt)


def create_lookup(manufacturer: str, model: str, codename: str) -> CatalogLookup:
    values = tuple(_lookup_text(value) for value in (manufacturer, model, codename))
    if any(not value for value in values):
        raise CatalogAcquisitionError("Exact manufacturer, model and codename are required")
    lookup = CatalogLookup(*values, "")
    return replace(lookup, lookup_digest=_lookup_digest(lookup))


def receipt_mapping(receipt: CatalogAcquisitionReceipt) -> dict[str, object]:
    return {"format": CatalogReceiptStore.FORMAT, **asdict(receipt)}


def seal_receipt(receipt: CatalogAcquisitionReceipt) -> CatalogAcquisitionReceipt:
    normalized = replace(
        receipt,
        receipt_id="0" * 64,
        receipt_digest="",
        compatibility_hint="UNCONFIRMED",
        execution_authority="none",
        phone_action_allowed=False,
        guardian_approval=False,
        bootloader_relock_allowed=False,
        raw_response_retained=False,
    )
    identity = hashlib.sha256(_canonical(receipt_mapping(normalized))).hexdigest()
    normalized = replace(normalized, receipt_id=identity)
    mapping = receipt_mapping(normalized)
    mapping["receipt_digest"] = ""
    return replace(normalized, receipt_digest=hashlib.sha256(_canonical(mapping)).hexdigest())


def parse_receipt(raw: dict[str, object]) -> CatalogAcquisitionReceipt:
    expected = {"format", *(field.name for field in fields(CatalogAcquisitionReceipt))}
    if set(raw) != expected or raw["format"] != CatalogReceiptStore.FORMAT:
        raise CatalogAcquisitionError("Catalog receipt fields or format are invalid")
    lookup_raw = raw["lookup"]
    if not isinstance(lookup_raw, dict) or set(lookup_raw) != {
        "manufacturer",
        "model",
        "codename",
        "lookup_digest",
    }:
        raise CatalogAcquisitionError("Catalog receipt lookup is invalid")
    lookup = CatalogLookup(
        _stored_lookup(lookup_raw["manufacturer"]),
        _stored_lookup(lookup_raw["model"]),
        _stored_lookup(lookup_raw["codename"]),
        _digest(lookup_raw["lookup_digest"]),
    )
    if lookup != _rejected_lookup() and lookup.lookup_digest != _lookup_digest(lookup):
        raise CatalogAcquisitionError("Catalog receipt lookup digest is invalid")
    receipt = CatalogAcquisitionReceipt(
        _literal(raw["schema_version"], 1, "schema version"),
        _digest(raw["receipt_id"]),
        lookup,
        _literal(raw["source_url"], GOOGLE_PLAY_CATALOG_URL, "source URL"),
        _timestamp(raw["retrieved_at"]),
        AcquisitionOutcome(raw["outcome"]),
        _private_text(raw["reason"], 300),
        _integer(raw["http_status"], 0, 599, "HTTP status"),
        _integer(
            raw["content_bytes"], 0, GooglePlayEvidenceAcquirer.MAXIMUM_BYTES, "content bytes"
        ),
        _integer(raw["parsed_row_count"], 0, GooglePlayEvidenceAcquirer.MAXIMUM_ROWS, "row count"),
        _optional_digest(raw["content_digest"]),
        _safe_header(raw["etag"]),
        _safe_header(raw["last_modified"]),
        _literal(raw["parser_id"], PARSER_ID, "parser identity"),
        _literal(raw["parser_version"], PARSER_VERSION, "parser version"),
        _digests(raw["matched_claim_ids"]),
        _digests(raw["retained_claim_ids"]),
        _optional_digest(raw["evidence_archive_digest"]),
        _optional_digest(raw["previous_receipt_digest"]),
        _digest(raw["receipt_digest"]),
        _literal(raw["compatibility_hint"], "UNCONFIRMED", "compatibility hint"),
        _literal(raw["execution_authority"], "none", "execution authority"),
        _literal(raw["phone_action_allowed"], False, "phone action authority"),
        _literal(raw["guardian_approval"], False, "Guardian approval"),
        _literal(raw["bootloader_relock_allowed"], False, "relock authority"),
        _literal(raw["raw_response_retained"], False, "raw response retention"),
    )
    if (
        receipt.lookup == _rejected_lookup()
        and receipt.outcome is not AcquisitionOutcome.VALIDATION_FAILURE
    ):
        raise CatalogAcquisitionError("Rejected lookup receipt outcome is invalid")
    if receipt.outcome is AcquisitionOutcome.SUCCESS and not (
        receipt.http_status == 200
        and receipt.content_bytes > 0
        and receipt.parsed_row_count > 0
        and receipt.content_digest
        and receipt.matched_claim_ids
        and receipt.matched_claim_ids == receipt.retained_claim_ids
        and receipt.evidence_archive_digest
    ):
        raise CatalogAcquisitionError("Successful catalog receipt evidence is incomplete")
    if receipt.outcome is AcquisitionOutcome.NO_EXACT_MATCH and not (
        receipt.http_status == 200
        and receipt.content_digest
        and not receipt.matched_claim_ids
        and not receipt.retained_claim_ids
        and not receipt.evidence_archive_digest
    ):
        raise CatalogAcquisitionError("No-match catalog receipt evidence is invalid")
    if receipt.outcome is AcquisitionOutcome.CACHE_NOT_MODIFIED and not (
        receipt.http_status == 304
        and receipt.content_digest
        and not receipt.matched_claim_ids
        and bool(receipt.retained_claim_ids) == bool(receipt.evidence_archive_digest)
    ):
        raise CatalogAcquisitionError("Cache-not-modified receipt evidence is invalid")
    if seal_receipt(replace(receipt, receipt_id="0" * 64, receipt_digest="")) != receipt:
        raise CatalogAcquisitionError("Catalog receipt digest or identity is invalid")
    return receipt


def _rejected_lookup() -> CatalogLookup:
    digest = hashlib.sha256(b"romverse.rejected-private-catalog-lookup").hexdigest()
    return CatalogLookup("", "", "", digest)


def _lookup_digest(lookup: CatalogLookup) -> str:
    return hashlib.sha256(
        _canonical(
            {
                "manufacturer": lookup.manufacturer,
                "model": lookup.model,
                "codename": lookup.codename,
            }
        )
    ).hexdigest()


def _lookup_text(value: object) -> str:
    if not isinstance(value, str):
        raise CatalogAcquisitionError("Catalog lookup must be text")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise CatalogAcquisitionError("Catalog lookup contains control characters")
    normalized = _key(value)
    if not normalized or len(normalized) > 120 or scrub_private_text(normalized) != normalized:
        raise CatalogAcquisitionError("Catalog lookup contains private or invalid text")
    return normalized


def _stored_lookup(value: object) -> str:
    if not isinstance(value, str):
        raise CatalogAcquisitionError("Stored catalog lookup is invalid")
    if not value:
        return ""
    return _lookup_text(value)


def _catalog_text(value: str, maximum: int) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    if (
        len(normalized) > maximum
        or any(ord(character) < 32 or ord(character) == 127 for character in normalized)
        or normalized.lstrip().startswith(("=", "+", "-", "@"))
    ):
        raise CatalogAcquisitionError("Official catalog contains unsafe field text")
    return " ".join(normalized.split())


def _key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _header(headers: Mapping[str, str], name: str) -> str:
    for key, value in headers.items():
        if str(key).casefold() == name.casefold():
            return _safe_header(value)
    return ""


def _safe_header(value: object) -> str:
    if not isinstance(value, str):
        raise CatalogAcquisitionError("Catalog response header is invalid")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise CatalogAcquisitionError("Catalog response header is unsafe")
    normalized = " ".join(value.split())
    if len(normalized) > 200:
        raise CatalogAcquisitionError("Catalog response header is unsafe")
    return normalized


def _content_length(headers: Mapping[str, str]) -> int | None:
    raw = _header(headers, "content-length")
    if not raw:
        return None
    if re.fullmatch(r"[0-9]+", raw) is None:
        raise CatalogAcquisitionError("Catalog content length is invalid")
    length = int(raw)
    if not 0 < length <= GooglePlayEvidenceAcquirer.MAXIMUM_BYTES:
        raise CatalogAcquisitionError("Catalog content length exceeds its boundary")
    return length


def _http_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return _aware(parsed)


def _aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise CatalogAcquisitionError("Catalog time requires a timezone")
    return value.astimezone(UTC)


def _timestamp(value: object) -> str:
    if not isinstance(value, str) or len(value) > 40:
        raise CatalogAcquisitionError("Catalog timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise CatalogAcquisitionError("Catalog timestamp is invalid") from exc
    return _aware(parsed).isoformat()


def _private_text(value: object, maximum: int) -> str:
    if not isinstance(value, str):
        raise CatalogAcquisitionError("Catalog receipt text is invalid")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise CatalogAcquisitionError("Catalog receipt text is unsafe")
    normalized = " ".join(value.split())
    if len(normalized) > maximum or scrub_private_text(normalized) != normalized:
        raise CatalogAcquisitionError("Catalog receipt text is unsafe")
    return normalized


def _bounded_failure(exc: Exception) -> str:
    detail = scrub_private_text(" ".join(str(exc).split()))
    if not detail or len(detail) > 180:
        detail = type(exc).__name__
    return f"{detail}."


def _integer(value: object, minimum: int, maximum: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise CatalogAcquisitionError(f"Catalog receipt {label} is invalid")
    return value


def _literal(value: object, expected: object, label: str):
    if value != expected or type(value) is not type(expected):
        raise CatalogAcquisitionError(f"Catalog receipt {label} is invalid")
    return expected


def _digest(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise CatalogAcquisitionError("Catalog receipt digest is invalid")
    return value


def _optional_digest(value: object) -> str:
    if value == "":
        return ""
    return _digest(value)


def _digests(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > 16:
        raise CatalogAcquisitionError("Catalog receipt claim references are invalid")
    result = tuple(_digest(item) for item in value)
    if result != tuple(sorted(set(result))):
        raise CatalogAcquisitionError("Catalog receipt claim references must be sorted and unique")
    return result


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
