"""Exact-page, metadata-only AOSP build-number evidence for explicit Pixel 6 rows."""

from __future__ import annotations

import hashlib
import http.client
import json
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, fields, replace
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from enum import StrEnum
from html.parser import HTMLParser
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
    ClaimKind,
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

AOSP_BUILD_NUMBERS_URL = "https://source.android.com/docs/setup/reference/build-numbers"
PARSER_ID = "romverse.aosp-build-numbers"
PARSER_VERSION = "1"
TARGET_DEVICE = "Pixel 6"


class AOSPBuildNumbersError(ValueError):
    """The AOSP build-reference boundary or sealed receipt failed."""


class AOSPBuildOutcome(StrEnum):
    SUCCESS = "success"
    HTTP_FAILURE = "http-failure"
    VALIDATION_FAILURE = "validation-failure"
    CACHE_NOT_MODIFIED = "cache-not-modified"


@dataclass(frozen=True, slots=True)
class AOSPBuildRequest:
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
            self.url != AOSP_BUILD_NUMBERS_URL
            or len(headers) != len(self.headers)
            or set(headers) - allowed
            or headers.get("Accept") != "text/html"
            or headers.get("Accept-Encoding") != "identity"
            or headers.get("User-Agent") != AOSPBuildNumbersAcquirer.USER_AGENT
            or any(_unsafe_header(value) for value in headers.values())
            or not 0 < self.connect_timeout_seconds <= 15
            or not 0 < self.read_timeout_seconds <= 20
            or not 0 < self.overall_timeout_seconds <= 60
            or not 0 < self.maximum_bytes <= 4 * 1024 * 1024
        ):
            raise AOSPBuildNumbersError("AOSP build request violates the fixed contract")


@dataclass(frozen=True, slots=True)
class AOSPBuildResponse:
    status: int
    final_url: str
    headers: Mapping[str, str]
    body: bytes


class AOSPBuildTransport(Protocol):
    def fetch(self, request: AOSPBuildRequest) -> AOSPBuildResponse: ...


@dataclass(frozen=True, slots=True)
class AOSPBuildEntry:
    build_id: str
    aosp_tag: str
    android_version: str
    supported_devices: tuple[str, ...]
    security_patch_level: str


@dataclass(frozen=True, slots=True)
class AOSPBuildReceipt:
    schema_version: int
    receipt_id: str
    source_url: str
    target_device: str
    retrieved_at: str
    published_at: str
    outcome: AOSPBuildOutcome
    reason: str
    http_status: int
    content_bytes: int
    parsed_matching_row_count: int
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
    evidence_state: str = "officially-documented"
    compatibility_hint: str = "UNCONFIRMED"
    codename_mapping_inferred: bool = False
    package_hash_available: bool = False
    execution_authority: str = "none"
    phone_action_allowed: bool = False
    guardian_approval: bool = False
    bootloader_relock_allowed: bool = False
    raw_response_retained: bool = False


class FixedAOSPBuildNumbersHTTPS:
    CHUNK_BYTES = 64 * 1024

    def __init__(self, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._monotonic = monotonic

    def fetch(self, request: AOSPBuildRequest) -> AOSPBuildResponse:
        if request.url != AOSP_BUILD_NUMBERS_URL:
            raise AOSPBuildNumbersError("AOSP transport accepts only the exact build page")
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
                    raise TimeoutError("AOSP build-page overall timeout expired")
                if connection.sock is not None:
                    connection.sock.settimeout(min(request.read_timeout_seconds, remaining))
                chunk = response.read(self.CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > request.maximum_bytes:
                    raise AOSPBuildNumbersError("AOSP build page exceeded its byte boundary")
                chunks.append(chunk)
            return AOSPBuildResponse(
                response.status,
                request.url,
                {name.casefold(): value for name, value in response.getheaders()},
                b"".join(chunks),
            )
        except TimeoutError as exc:
            raise TimeoutError("AOSP build-page request timed out") from exc
        finally:
            connection.close()


class AOSPBuildReceiptStore:
    FORMAT = "romverse.aosp-build-numbers-acquisition"
    MAXIMUM_BYTES = 32 * 1024

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.expanduser().resolve()
        self.path = (
            self.workspace
            / "knowledge/online-device-evidence/acquisitions/aosp-build-numbers.romverse"
        )

    def load(self) -> AOSPBuildReceipt | None:
        if not self.path.exists():
            return None
        try:
            return parse_receipt(
                read_json_object(
                    self.path,
                    boundary=self.workspace,
                    maximum_bytes=self.MAXIMUM_BYTES,
                )
            )
        except (LocalStoreError, OSError, TypeError, ValueError, KeyError) as exc:
            if isinstance(exc, AOSPBuildNumbersError):
                raise
            raise AOSPBuildNumbersError(f"AOSP build receipt is unavailable: {exc}") from exc

    def save(self, receipt: AOSPBuildReceipt) -> AOSPBuildReceipt:
        sealed = seal_receipt(receipt)
        mapping = receipt_mapping(sealed)
        parse_receipt(json.loads(json.dumps(mapping, allow_nan=False)))
        self.workspace.mkdir(parents=True, exist_ok=True)
        ensure_private_directory(self.workspace, boundary=self.workspace)
        ensure_private_directory(self.workspace / "knowledge", boundary=self.workspace)
        ensure_private_directory(
            self.workspace / "knowledge/online-device-evidence", boundary=self.workspace
        )
        ensure_private_directory(self.path.parent, boundary=self.workspace)
        try:
            atomic_write_json(
                self.path,
                mapping,
                boundary=self.workspace,
                maximum_bytes=self.MAXIMUM_BYTES,
            )
        except LocalStoreError as exc:
            raise AOSPBuildNumbersError("AOSP build receipt could not be stored safely") from exc
        loaded = self.load()
        if loaded != sealed:
            raise AOSPBuildNumbersError("AOSP build receipt changed during save verification")
        return loaded


class AOSPBuildNumbersAcquirer:
    MAXIMUM_BYTES = 4 * 1024 * 1024
    MAXIMUM_BLOCKS = 2_000
    MAXIMUM_ROWS = 2_000
    MAXIMUM_MATCHES = 256
    MAXIMUM_FIELD_CHARS = 500
    CONNECT_TIMEOUT_SECONDS = 8.0
    READ_TIMEOUT_SECONDS = 12.0
    OVERALL_TIMEOUT_SECONDS = 30.0
    MINIMUM_INTERVAL_SECONDS = 2.0
    USER_AGENT = "ROMVERSE/0.2 aosp-pixel6-build-metadata"

    def __init__(
        self,
        workspace: Path,
        *,
        registry: EvidenceSourceRegistry | None = None,
        transport: AOSPBuildTransport | None = None,
    ) -> None:
        self.workspace = workspace.expanduser().resolve()
        self.registry = registry or EvidenceSourceRegistry()
        self.adapter = self.registry.resolve(AOSP_BUILD_NUMBERS_URL)
        if self.adapter.parser_id != PARSER_ID or self.adapter.parser_version != PARSER_VERSION:
            raise AOSPBuildNumbersError("AOSP build parser registration is invalid")
        self.transport = transport or FixedAOSPBuildNumbersHTTPS()
        self.receipts = AOSPBuildReceiptStore(self.workspace)
        self.evidence = OnlineEvidenceStore(self.workspace)

    def acquire(self, *, now: datetime | None = None) -> AOSPBuildReceipt:
        retrieved = _aware(now or datetime.now(UTC))
        previous = self.receipts.load()
        if previous is not None:
            elapsed = (retrieved - datetime.fromisoformat(previous.retrieved_at)).total_seconds()
            if elapsed < max(self.MINIMUM_INTERVAL_SECONDS, self.adapter.minimum_interval_seconds):
                return self._record(
                    retrieved,
                    AOSPBuildOutcome.VALIDATION_FAILURE,
                    "Minimum request spacing has not elapsed.",
                    previous=previous,
                )
        headers = {
            "Accept": "text/html",
            "Accept-Encoding": "identity",
            "User-Agent": self.USER_AGENT,
        }
        if previous is not None and previous.content_digest and previous.etag:
            headers["If-None-Match"] = previous.etag
        if previous is not None and previous.content_digest and previous.last_modified:
            headers["If-Modified-Since"] = previous.last_modified
        request = AOSPBuildRequest(
            AOSP_BUILD_NUMBERS_URL,
            tuple(sorted(headers.items())),
            self.CONNECT_TIMEOUT_SECONDS,
            self.READ_TIMEOUT_SECONDS,
            self.OVERALL_TIMEOUT_SECONDS,
            self.MAXIMUM_BYTES,
        )
        try:
            response = self.transport.fetch(request)
        except AOSPBuildNumbersError as exc:
            return self._record(
                retrieved,
                AOSPBuildOutcome.VALIDATION_FAILURE,
                f"AOSP build transport validation failed: {_bounded_failure(exc)}",
                previous=previous,
            )
        except (OSError, TimeoutError, http.client.HTTPException) as exc:
            return self._record(
                retrieved,
                AOSPBuildOutcome.HTTP_FAILURE,
                f"AOSP build request failed: {type(exc).__name__}.",
                previous=previous,
            )
        try:
            _validate_response(response)
            etag = _header(response.headers, "etag")
            last_modified = _header(response.headers, "last-modified")
        except AOSPBuildNumbersError as exc:
            return self._record(
                retrieved,
                AOSPBuildOutcome.VALIDATION_FAILURE,
                f"AOSP build response validation failed: {_bounded_failure(exc)}",
                previous=previous,
            )
        if response.status == 304:
            if previous is None or not previous.content_digest:
                return self._record(
                    retrieved,
                    AOSPBuildOutcome.VALIDATION_FAILURE,
                    "Cache-not-modified response had no prior validated evidence.",
                    http_status=304,
                )
            return self._record(
                retrieved,
                AOSPBuildOutcome.CACHE_NOT_MODIFIED,
                "The exact AOSP page reports the retained metadata is unchanged.",
                published_at=previous.published_at,
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
                retrieved,
                AOSPBuildOutcome.HTTP_FAILURE,
                f"AOSP build page returned HTTP {response.status}.",
                http_status=response.status,
                previous=previous,
            )
        try:
            if not 0 < len(response.body) <= self.MAXIMUM_BYTES:
                raise AOSPBuildNumbersError("AOSP build-page body exceeds its boundary")
            digest = self.adapter.validate_content(
                response.body,
                requested_url=AOSP_BUILD_NUMBERS_URL,
                final_url=response.final_url,
                status=200,
                content_type=_header(response.headers, "content-type"),
                content_encoding=_header(response.headers, "content-encoding") or "identity",
            )
            declared = _content_length(response.headers)
            if declared is not None and declared != len(response.body):
                raise AOSPBuildNumbersError("AOSP build-page response was truncated")
            parsed = parse_aosp_build_numbers(response.body)
        except (AOSPBuildNumbersError, OnlineEvidenceError, UnicodeError) as exc:
            return self._record(
                retrieved,
                AOSPBuildOutcome.VALIDATION_FAILURE,
                f"AOSP build-page validation failed: {_bounded_failure(exc)}",
                http_status=200,
                content_bytes=(
                    len(response.body) if len(response.body) <= self.MAXIMUM_BYTES else 0
                ),
                previous=previous,
            )
        published = _published_time(parsed.modified_at, last_modified)
        freshness = (
            freshness_at(published, retrieved, self.adapter.freshness_days)
            if published
            else EvidenceFreshness.UNCONFIRMED
        )
        claims = self._claims(parsed.entries, retrieved, published, freshness, digest)
        archive = self.evidence.merge(claims, now=retrieved)
        claim_ids = tuple(sorted(claim.claim_id for claim in claims))
        return self._record(
            retrieved,
            AOSPBuildOutcome.SUCCESS,
            "Explicit Pixel 6 AOSP build-reference rows retained; compatibility remains unconfirmed.",
            published_at=published.isoformat() if published else "",
            http_status=200,
            content_bytes=len(response.body),
            parsed_matching_row_count=len(parsed.entries),
            content_digest=digest,
            etag=etag,
            last_modified=last_modified,
            matched_claim_ids=claim_ids,
            retained_claim_ids=claim_ids,
            archive_digest=archive.archive_digest,
            previous=previous,
        )

    def projections(self, receipt: AOSPBuildReceipt) -> tuple[EvidenceProjection, ...]:
        claims = ()
        if receipt.retained_claim_ids:
            retained = set(receipt.retained_claim_ids)
            claims = tuple(
                claim for claim in self.evidence.load().claims if claim.claim_id in retained
            )
            if len(claims) != len(retained):
                raise AOSPBuildNumbersError("AOSP build projection claims are unavailable")
        consumers = (
            EvidenceConsumer.DEVICE_DNA,
            EvidenceConsumer.COMPATIBILITY_MATRIX,
            EvidenceConsumer.PATHFINDER,
            EvidenceConsumer.NEXUS,
            EvidenceConsumer.FORESIGHT,
            EvidenceConsumer.KNOWLEDGE_ARCHIVES,
        )
        return tuple(
            replace(
                project_evidence(claims, consumer),
                compatibility_hint="UNCONFIRMED",
                investigation_required=True,
                workflow=("review-build-reference", "compare-exact-evidence", "research-gaps"),
                next_action=(
                    "Compare exact firmware/device evidence; this AOSP reference grants no "
                    "codename, package, download, or installation authority."
                ),
            )
            for consumer in consumers
        )

    def _claims(
        self,
        entries: tuple[AOSPBuildEntry, ...],
        retrieved: datetime,
        published: datetime | None,
        freshness: EvidenceFreshness,
        digest: str,
    ):
        claims = []
        for entry in entries:
            scope = EvidenceScope(
                models=entry.supported_devices,
                build_ids=(entry.build_id,),
                android_versions=(entry.android_version,),
                scope_note=(
                    "AOSP build-reference supported-device list explicitly includes Pixel 6; "
                    "codename and firmware compatibility remain unconfirmed."
                ),
            )
            value = json.dumps(asdict(entry), sort_keys=True, separators=(",", ":"))
            claims.append(
                create_claim(
                    claim_key="firmware.aosp.build-reference",
                    scope=scope,
                    source_id=self.adapter.adapter_id,
                    url=AOSP_BUILD_NUMBERS_URL,
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
                        "Official AOSP build-reference metadata only; no codename, package hash, "
                        "compatibility, flash, outcome, or execution authority."
                    ),
                    knowledge_kind=ClaimKind.IDENTITY,
                    affected_builds=(entry.build_id,),
                )
            )
        return tuple(claims)

    def _record(
        self,
        retrieved: datetime,
        outcome: AOSPBuildOutcome,
        reason: str,
        *,
        published_at: str = "",
        http_status: int = 0,
        content_bytes: int = 0,
        parsed_matching_row_count: int = 0,
        content_digest: str = "",
        etag: str = "",
        last_modified: str = "",
        matched_claim_ids: tuple[str, ...] = (),
        retained_claim_ids: tuple[str, ...] | None = None,
        archive_digest: str | None = None,
        previous: AOSPBuildReceipt | None = None,
    ) -> AOSPBuildReceipt:
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
        digest = content_digest or (
            previous.content_digest if retained and previous is not None else ""
        )
        return self.receipts.save(
            AOSPBuildReceipt(
                1,
                "0" * 64,
                AOSP_BUILD_NUMBERS_URL,
                TARGET_DEVICE,
                retrieved.isoformat(),
                published_at or (previous.published_at if previous and retained else ""),
                outcome,
                scrub_private_text(reason),
                http_status,
                content_bytes,
                parsed_matching_row_count,
                digest,
                _safe_header(etag or (previous.etag if previous else "")),
                _safe_header(last_modified or (previous.last_modified if previous else "")),
                PARSER_ID,
                PARSER_VERSION,
                tuple(sorted(matched_claim_ids)),
                tuple(sorted(retained)),
                archive,
                previous.receipt_digest if previous else "",
                "",
            )
        )


@dataclass(frozen=True, slots=True)
class _Cell:
    text: str
    header: bool


@dataclass(frozen=True, slots=True)
class _Row:
    table_id: int
    cells: tuple[_Cell, ...]


@dataclass(frozen=True, slots=True)
class ParsedAOSPBuilds:
    modified_at: str
    entries: tuple[AOSPBuildEntry, ...]


class _AOSPHTMLParser(HTMLParser):
    _EXCLUDED = {
        "script",
        "style",
        "code",
        "pre",
        "nav",
        "footer",
        "noscript",
        "template",
        "form",
        "button",
    }
    _VOID = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.language = ""
        self.canonical_url = ""
        self.modified_at = ""
        self.title = ""
        self.rows: list[_Row] = []
        self.block_count = 0
        self._content_depth = 0
        self._excluded_depth = 0
        self._heading_tag = ""
        self._heading_parts: list[str] = []
        self._table_id = 0
        self._table_depth = 0
        self._row_depth = 0
        self._cells: list[_Cell] = []
        self._cell_tag = ""
        self._cell_depth = 0
        self._cell_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name.casefold(): value or "" for name, value in attrs}
        if tag == "html":
            self.language = attributes.get("lang", "")
        if tag == "link" and "canonical" in attributes.get("rel", "").casefold().split():
            self.canonical_url = attributes.get("href", "")
        if tag == "meta":
            marker = (
                attributes.get("itemprop")
                or attributes.get("property")
                or attributes.get("name")
                or ""
            ).casefold()
            if marker in {"datemodified", "article:modified_time", "last-modified"}:
                self.modified_at = attributes.get("content", "")
        if tag == "time" and attributes.get("datetime"):
            self.modified_at = self.modified_at or attributes["datetime"]
        if tag in self._EXCLUDED:
            self._excluded_depth += 1
            return
        if tag in {"main", "article"}:
            self._content_depth += 1
        if self._excluded_depth or not self._content_depth:
            return
        if tag == "h1" and not self._heading_tag:
            self._heading_tag = tag
            self._heading_parts = []
        if tag == "table":
            self._table_id += 1
            self._table_depth += 1
        if tag == "tr" and self._table_depth and not self._row_depth:
            self._row_depth = 1
            self._cells = []
        elif self._row_depth and tag not in self._VOID:
            self._row_depth += 1
        if self._row_depth and tag in {"th", "td"} and not self._cell_tag:
            self._cell_tag = tag
            self._cell_depth = 1
            self._cell_parts = []
        elif self._cell_tag and tag not in self._VOID and tag not in {"th", "td"}:
            self._cell_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._EXCLUDED:
            self._excluded_depth = max(0, self._excluded_depth - 1)
            return
        if self._excluded_depth:
            return
        if self._heading_tag and tag == self._heading_tag:
            self.title = _visible_text(" ".join(self._heading_parts))
            self.block_count += 1
            self._heading_tag = ""
            self._heading_parts = []
        if self._cell_tag:
            self._cell_depth -= 1
            if self._cell_depth == 0:
                self._cells.append(
                    _Cell(_visible_text(" ".join(self._cell_parts)), self._cell_tag == "th")
                )
                self._cell_tag = ""
                self._cell_parts = []
        if self._row_depth:
            self._row_depth -= 1
            if self._row_depth == 0:
                self.block_count += 1
                if self._cells:
                    self.rows.append(_Row(self._table_id, tuple(self._cells)))
                self._cells = []
        if tag == "table":
            self._table_depth = max(0, self._table_depth - 1)
        if tag in {"main", "article"}:
            self._content_depth = max(0, self._content_depth - 1)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in self._VOID:
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self._excluded_depth:
            return
        if self._heading_tag:
            self._heading_parts.append(data)
        if self._cell_tag:
            self._cell_parts.append(data)


_HEADER_LAYOUTS = {
    ("build id", "tag", "version", "supported devices", "security patch level"),
    ("build", "tag", "android version", "supported devices", "security patch level"),
}


def parse_aosp_build_numbers(payload: bytes) -> ParsedAOSPBuilds:
    try:
        decoded = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AOSPBuildNumbersError("AOSP build page is not valid UTF-8") from exc
    parser = _AOSPHTMLParser()
    try:
        parser.feed(decoded)
        parser.close()
    except AOSPBuildNumbersError:
        raise
    except Exception as exc:
        raise AOSPBuildNumbersError(
            f"AOSP build HTML parser failed with {type(exc).__name__}"
        ) from exc
    if parser.canonical_url != AOSP_BUILD_NUMBERS_URL:
        raise AOSPBuildNumbersError("AOSP build canonical URL is missing or changed")
    if not parser.language.casefold().startswith("en"):
        raise AOSPBuildNumbersError("AOSP build page is not canonical English")
    if not parser.title or parser.block_count > AOSPBuildNumbersAcquirer.MAXIMUM_BLOCKS:
        raise AOSPBuildNumbersError("AOSP build page structure exceeds its boundary")
    by_table: dict[int, list[_Row]] = {}
    for row in parser.rows:
        by_table.setdefault(row.table_id, []).append(row)
    entries: list[AOSPBuildEntry] = []
    reviewed_tables = 0
    total_rows = 0
    for rows in by_table.values():
        header = tuple(_key(cell.text) for cell in rows[0].cells)
        if not all(cell.header for cell in rows[0].cells) or header not in _HEADER_LAYOUTS:
            continue
        reviewed_tables += 1
        names = (
            "build_id",
            "aosp_tag",
            "android_version",
            "supported_devices",
            "security_patch_level",
        )
        for row in rows[1:]:
            total_rows += 1
            if total_rows > AOSPBuildNumbersAcquirer.MAXIMUM_ROWS:
                raise AOSPBuildNumbersError("AOSP build table exceeds its row boundary")
            if len(row.cells) != len(names) or any(cell.header for cell in row.cells):
                raise AOSPBuildNumbersError("AOSP build table row shape changed")
            values = {name: row.cells[index].text for index, name in enumerate(names)}
            entry = _parse_entry(values)
            if entry is not None:
                entries.append(entry)
                if len(entries) > AOSPBuildNumbersAcquirer.MAXIMUM_MATCHES:
                    raise AOSPBuildNumbersError("AOSP Pixel 6 rows exceed their boundary")
    if reviewed_tables != 1:
        raise AOSPBuildNumbersError("Reviewed AOSP build table is missing or ambiguous")
    if not entries:
        raise AOSPBuildNumbersError("No explicit Pixel 6 supported-device rows were found")
    if len({entry.build_id.casefold() for entry in entries}) != len(entries):
        raise AOSPBuildNumbersError("AOSP Pixel 6 build IDs are duplicate or conflicting")
    return ParsedAOSPBuilds(parser.modified_at, tuple(entries))


def _parse_entry(values: dict[str, str]) -> AOSPBuildEntry | None:
    supported_text = _metadata_text(values["supported_devices"], "supported devices", empty=True)
    if not supported_text:
        return None
    devices = tuple(_metadata_text(part, "supported device") for part in supported_text.split(","))
    if len(devices) > 32 or len(set(device.casefold() for device in devices)) != len(devices):
        raise AOSPBuildNumbersError("AOSP supported-device list is invalid")
    if TARGET_DEVICE.casefold() not in {device.casefold() for device in devices}:
        return None
    build_id = _metadata_text(values["build_id"], "build ID")
    tag = _metadata_text(values["aosp_tag"], "AOSP tag")
    version = _metadata_text(values["android_version"], "Android version")
    patch = _metadata_text(values["security_patch_level"], "security patch level")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,99}", build_id):
        raise AOSPBuildNumbersError("AOSP build ID is invalid")
    if not re.fullmatch(r"android-[a-z0-9._-]{3,100}", tag.casefold()):
        raise AOSPBuildNumbersError("AOSP tag is invalid")
    if not re.fullmatch(r"(?:Android\s*)?\d+(?:\.\d+){0,2}", version, re.IGNORECASE):
        raise AOSPBuildNumbersError("AOSP Android version is invalid")
    if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", patch):
        raise AOSPBuildNumbersError("AOSP security patch level is invalid")
    value = AOSPBuildEntry(build_id, tag, version, devices, patch)
    if len(json.dumps(asdict(value), sort_keys=True, separators=(",", ":"))) > 500:
        raise AOSPBuildNumbersError("AOSP matching row exceeds the retained-value boundary")
    return value


def receipt_mapping(receipt: AOSPBuildReceipt) -> dict[str, object]:
    return {"format": AOSPBuildReceiptStore.FORMAT, **asdict(receipt)}


def seal_receipt(receipt: AOSPBuildReceipt) -> AOSPBuildReceipt:
    normalized = replace(
        receipt,
        receipt_id="0" * 64,
        receipt_digest="",
        evidence_state="officially-documented",
        compatibility_hint="UNCONFIRMED",
        codename_mapping_inferred=False,
        package_hash_available=False,
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


def parse_receipt(raw: dict[str, object]) -> AOSPBuildReceipt:
    expected = {"format", *(field.name for field in fields(AOSPBuildReceipt))}
    if set(raw) != expected or raw["format"] != AOSPBuildReceiptStore.FORMAT:
        raise AOSPBuildNumbersError("AOSP build receipt fields or format are invalid")
    receipt = AOSPBuildReceipt(
        _literal(raw["schema_version"], 1, "schema version"),
        _digest(raw["receipt_id"]),
        _literal(raw["source_url"], AOSP_BUILD_NUMBERS_URL, "source URL"),
        _literal(raw["target_device"], TARGET_DEVICE, "target device"),
        _timestamp(raw["retrieved_at"]),
        _timestamp(raw["published_at"]) if raw["published_at"] else "",
        AOSPBuildOutcome(raw["outcome"]),
        _private_text(raw["reason"], 400),
        _integer(raw["http_status"], 0, 599, "HTTP status"),
        _integer(raw["content_bytes"], 0, AOSPBuildNumbersAcquirer.MAXIMUM_BYTES, "content bytes"),
        _integer(
            raw["parsed_matching_row_count"],
            0,
            AOSPBuildNumbersAcquirer.MAXIMUM_MATCHES,
            "matching row count",
        ),
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
        _literal(raw["evidence_state"], "officially-documented", "evidence state"),
        _literal(raw["compatibility_hint"], "UNCONFIRMED", "compatibility hint"),
        _literal(raw["codename_mapping_inferred"], False, "codename inference"),
        _literal(raw["package_hash_available"], False, "package hash"),
        _literal(raw["execution_authority"], "none", "execution authority"),
        _literal(raw["phone_action_allowed"], False, "phone action authority"),
        _literal(raw["guardian_approval"], False, "Guardian approval"),
        _literal(raw["bootloader_relock_allowed"], False, "relock authority"),
        _literal(raw["raw_response_retained"], False, "raw response retention"),
    )
    if receipt.outcome is AOSPBuildOutcome.SUCCESS and not (
        receipt.http_status == 200
        and receipt.content_bytes > 0
        and receipt.parsed_matching_row_count > 0
        and receipt.parsed_matching_row_count == len(receipt.matched_claim_ids)
        and receipt.content_digest
        and receipt.matched_claim_ids == receipt.retained_claim_ids
        and receipt.evidence_archive_digest
    ):
        raise AOSPBuildNumbersError("Successful AOSP build receipt evidence is incomplete")
    if receipt.outcome is AOSPBuildOutcome.CACHE_NOT_MODIFIED and not (
        receipt.http_status == 304
        and receipt.content_digest
        and not receipt.matched_claim_ids
        and receipt.retained_claim_ids
        and receipt.evidence_archive_digest
    ):
        raise AOSPBuildNumbersError("Cache-not-modified AOSP build receipt is invalid")
    if seal_receipt(replace(receipt, receipt_id="0" * 64, receipt_digest="")) != receipt:
        raise AOSPBuildNumbersError("AOSP build receipt digest or identity is invalid")
    return receipt


def _validate_response(response: object) -> None:
    if (
        not isinstance(response, AOSPBuildResponse)
        or isinstance(response.status, bool)
        or not isinstance(response.status, int)
        or not 100 <= response.status <= 599
        or not isinstance(response.headers, Mapping)
        or not isinstance(response.body, bytes)
        or not isinstance(response.final_url, str)
    ):
        raise AOSPBuildNumbersError("AOSP build response shape is invalid")


_EXECUTABLE = re.compile(
    r"(?i)(?:\b(?:adb|fastboot|flash|relock|unlock|sudo|powershell|cmd\.exe)\b|&&|\|\||\$\(|`|[<>])"
)


def _metadata_text(value: object, label: str, *, empty: bool = False) -> str:
    if not isinstance(value, str):
        raise AOSPBuildNumbersError(f"AOSP {label} is invalid")
    text = " ".join(value.split())
    if (not text and not empty) or len(text) > AOSPBuildNumbersAcquirer.MAXIMUM_FIELD_CHARS:
        raise AOSPBuildNumbersError(f"AOSP {label} is missing or oversized")
    if text and (scrub_private_text(text) != text or _EXECUTABLE.search(text)):
        raise AOSPBuildNumbersError(f"AOSP {label} is unsafe")
    return text


def _visible_text(value: str) -> str:
    text = " ".join(value.split())
    if any(ord(character) < 32 for character in text):
        raise AOSPBuildNumbersError("AOSP visible text is invalid")
    return text if len(text) <= 2_000 else ""


def _published_time(page_value: str, header_value: str) -> datetime | None:
    if page_value:
        try:
            return _aware(datetime.fromisoformat(page_value.replace("Z", "+00:00")))
        except ValueError:
            pass
    if header_value:
        try:
            return _aware(parsedate_to_datetime(header_value))
        except (TypeError, ValueError):
            pass
    return None


def _key(value: str) -> str:
    return " ".join(value.casefold().split()).rstrip(".:?")


def _header(headers: Mapping[str, str], name: str) -> str:
    for key, value in headers.items():
        if str(key).casefold() == name.casefold():
            return _safe_header(value)
    return ""


def _safe_header(value: object) -> str:
    if not isinstance(value, str) or _unsafe_header(value):
        raise AOSPBuildNumbersError("AOSP response header is unsafe")
    return " ".join(value.split())


def _unsafe_header(value: object) -> bool:
    return (
        not isinstance(value, str)
        or len(value) > 200
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    )


def _content_length(headers: Mapping[str, str]) -> int | None:
    raw = _header(headers, "content-length")
    if not raw:
        return None
    if not raw.isdecimal():
        raise AOSPBuildNumbersError("AOSP content length is invalid")
    return int(raw)


def _timestamp(value: object) -> str:
    if not isinstance(value, str):
        raise AOSPBuildNumbersError("AOSP timestamp is invalid")
    try:
        return _aware(datetime.fromisoformat(value)).isoformat()
    except ValueError as exc:
        raise AOSPBuildNumbersError("AOSP timestamp is invalid") from exc


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AOSPBuildNumbersError("AOSP time must include an offset")
    return value.astimezone(UTC)


def _digest(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise AOSPBuildNumbersError("AOSP digest is invalid")
    return value


def _optional_digest(value: object) -> str:
    return "" if value == "" else _digest(value)


def _digests(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > AOSPBuildNumbersAcquirer.MAXIMUM_MATCHES:
        raise AOSPBuildNumbersError("AOSP claim identifiers are invalid")
    result = tuple(_digest(item) for item in value)
    if result != tuple(sorted(set(result))):
        raise AOSPBuildNumbersError("AOSP claim identifiers are not canonical")
    return result


def _private_text(value: object, maximum: int) -> str:
    if not isinstance(value, str) or len(value) > maximum or scrub_private_text(value) != value:
        raise AOSPBuildNumbersError("AOSP stored text is unsafe")
    return value


def _integer(value: object, minimum: int, maximum: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise AOSPBuildNumbersError(f"AOSP {label} is invalid")
    return value


def _literal(value: object, expected: object, label: str):
    if type(value) is not type(expected) or value != expected:
        raise AOSPBuildNumbersError(f"AOSP {label} is invalid")
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def _bounded_failure(error: Exception) -> str:
    return scrub_private_text(" ".join(str(error).split()))[:240]
