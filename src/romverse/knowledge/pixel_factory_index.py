"""Metadata-only acquisition from Google's exact Pixel factory-image index."""

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

PIXEL_FACTORY_INDEX_URL = "https://developers.google.com/android/images"
PIXEL_MANUFACTURER = "Google"
PIXEL_MODEL = "Pixel 6"
PIXEL_CODENAME = "oriole"
PARSER_ID = "romverse.google-pixel-factory-index"
PARSER_VERSION = "1"


class PixelFactoryIndexError(ValueError):
    """The factory-index request, metadata, or receipt violated its boundary."""


class FactoryIndexOutcome(StrEnum):
    SUCCESS = "success"
    HTTP_FAILURE = "http-failure"
    VALIDATION_FAILURE = "validation-failure"
    CACHE_NOT_MODIFIED = "cache-not-modified"


@dataclass(frozen=True, slots=True)
class FactoryIndexRequest:
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
            self.url != PIXEL_FACTORY_INDEX_URL
            or len(headers) != len(self.headers)
            or set(headers) - allowed
            or headers.get("Accept") != "text/html"
            or headers.get("Accept-Encoding") != "identity"
            or headers.get("User-Agent") != PixelFactoryIndexAcquirer.USER_AGENT
            or any(_unsafe_header(value) for value in headers.values())
            or not 0 < self.connect_timeout_seconds <= 15
            or not 0 < self.read_timeout_seconds <= 20
            or not 0 < self.overall_timeout_seconds <= 60
            or not 0 < self.maximum_bytes <= 4 * 1024 * 1024
        ):
            raise PixelFactoryIndexError("Factory-index request violates the fixed contract")


@dataclass(frozen=True, slots=True)
class FactoryIndexResponse:
    status: int
    final_url: str
    headers: Mapping[str, str]
    body: bytes


class FactoryIndexTransport(Protocol):
    def fetch(self, request: FactoryIndexRequest) -> FactoryIndexResponse: ...


@dataclass(frozen=True, slots=True)
class FactoryImageEntry:
    release_label: str
    android_version: str
    build_id: str
    release_date: str
    carrier_region_scope: str
    image_url: str
    sha256: str


@dataclass(frozen=True, slots=True)
class FactoryIndexReceipt:
    schema_version: int
    receipt_id: str
    source_url: str
    manufacturer: str
    model: str
    codename: str
    retrieved_at: str
    published_at: str
    outcome: FactoryIndexOutcome
    reason: str
    http_status: int
    content_bytes: int
    parsed_release_count: int
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
    execution_authority: str = "none"
    phone_action_allowed: bool = False
    guardian_approval: bool = False
    bootloader_relock_allowed: bool = False
    terms_accepted: bool = False
    binary_downloaded: bool = False
    raw_response_retained: bool = False


class FixedPixelFactoryIndexHTTPS:
    """One GET to the exact index; returned image links are identities, never fetched."""

    CHUNK_BYTES = 64 * 1024

    def __init__(self, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._monotonic = monotonic

    def fetch(self, request: FactoryIndexRequest) -> FactoryIndexResponse:
        if request.url != PIXEL_FACTORY_INDEX_URL:
            raise PixelFactoryIndexError("Factory-index transport accepts only the exact URL")
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
                    raise TimeoutError("Factory-index overall timeout expired")
                if connection.sock is not None:
                    connection.sock.settimeout(min(request.read_timeout_seconds, remaining))
                chunk = response.read(self.CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > request.maximum_bytes:
                    raise PixelFactoryIndexError("Factory index exceeded its response boundary")
                chunks.append(chunk)
            return FactoryIndexResponse(
                response.status,
                request.url,
                {name.casefold(): value for name, value in response.getheaders()},
                b"".join(chunks),
            )
        except TimeoutError as exc:
            raise TimeoutError("Factory-index request timed out") from exc
        finally:
            connection.close()


class FactoryIndexReceiptStore:
    FORMAT = "romverse.google-pixel-factory-index-acquisition"
    SCHEMA_VERSION = 1
    MAXIMUM_BYTES = 32 * 1024

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.expanduser().resolve()
        self.path = (
            self.workspace
            / "knowledge/online-device-evidence/acquisitions/google-pixel-factory-index.romverse"
        )

    def load(self) -> FactoryIndexReceipt | None:
        if not self.path.exists():
            return None
        try:
            raw = read_json_object(
                self.path,
                boundary=self.workspace,
                maximum_bytes=self.MAXIMUM_BYTES,
            )
            return parse_receipt(raw)
        except (LocalStoreError, OSError, TypeError, ValueError, KeyError) as exc:
            if isinstance(exc, PixelFactoryIndexError):
                raise
            raise PixelFactoryIndexError(f"Factory-index receipt is unavailable: {exc}") from exc

    def save(self, receipt: FactoryIndexReceipt) -> FactoryIndexReceipt:
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
            raise PixelFactoryIndexError(
                "Factory-index receipt could not be stored safely"
            ) from exc
        loaded = self.load()
        if loaded != sealed:
            raise PixelFactoryIndexError("Factory-index receipt changed during save verification")
        return loaded


class PixelFactoryIndexAcquirer:
    MAXIMUM_BYTES = 4 * 1024 * 1024
    MAXIMUM_BLOCKS = 1_000
    MAXIMUM_RELEASES = 256
    MAXIMUM_FIELD_CHARS = 240
    CONNECT_TIMEOUT_SECONDS = 8.0
    READ_TIMEOUT_SECONDS = 12.0
    OVERALL_TIMEOUT_SECONDS = 30.0
    MINIMUM_INTERVAL_SECONDS = 2.0
    USER_AGENT = "ROMVERSE/0.2 pixel-factory-metadata-only"

    def __init__(
        self,
        workspace: Path,
        *,
        registry: EvidenceSourceRegistry | None = None,
        transport: FactoryIndexTransport | None = None,
    ) -> None:
        self.workspace = workspace.expanduser().resolve()
        self.registry = registry or EvidenceSourceRegistry()
        self.adapter = self.registry.resolve(PIXEL_FACTORY_INDEX_URL)
        if self.adapter.parser_id != PARSER_ID or self.adapter.parser_version != PARSER_VERSION:
            raise PixelFactoryIndexError("Factory-index parser registration is invalid")
        self.transport = transport or FixedPixelFactoryIndexHTTPS()
        self.receipts = FactoryIndexReceiptStore(self.workspace)
        self.evidence = OnlineEvidenceStore(self.workspace)

    def acquire(
        self,
        manufacturer: str = PIXEL_MANUFACTURER,
        model: str = PIXEL_MODEL,
        codename: str = PIXEL_CODENAME,
        *,
        now: datetime | None = None,
    ) -> FactoryIndexReceipt:
        retrieved = _aware(now or datetime.now(UTC))
        if tuple(_identity_key(item) for item in (manufacturer, model, codename)) != (
            "google",
            "pixel 6",
            "oriole",
        ):
            return self._record(
                retrieved,
                FactoryIndexOutcome.VALIDATION_FAILURE,
                "Only the approved public Google / Pixel 6 / oriole identity is accepted.",
            )
        previous = self.receipts.load()
        if previous is not None:
            elapsed = (retrieved - datetime.fromisoformat(previous.retrieved_at)).total_seconds()
            if elapsed < max(self.MINIMUM_INTERVAL_SECONDS, self.adapter.minimum_interval_seconds):
                return self._record(
                    retrieved,
                    FactoryIndexOutcome.VALIDATION_FAILURE,
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
        request = FactoryIndexRequest(
            PIXEL_FACTORY_INDEX_URL,
            tuple(sorted(headers.items())),
            self.CONNECT_TIMEOUT_SECONDS,
            self.READ_TIMEOUT_SECONDS,
            self.OVERALL_TIMEOUT_SECONDS,
            self.MAXIMUM_BYTES,
        )
        try:
            response = self.transport.fetch(request)
        except PixelFactoryIndexError as exc:
            return self._record(
                retrieved,
                FactoryIndexOutcome.VALIDATION_FAILURE,
                f"Factory-index transport validation failed: {_bounded_failure(exc)}",
                previous=previous,
            )
        except (OSError, TimeoutError, http.client.HTTPException) as exc:
            return self._record(
                retrieved,
                FactoryIndexOutcome.HTTP_FAILURE,
                f"Factory-index request failed: {type(exc).__name__}.",
                previous=previous,
            )
        try:
            _validate_response(response)
            etag = _header(response.headers, "etag")
            last_modified = _header(response.headers, "last-modified")
        except PixelFactoryIndexError as exc:
            return self._record(
                retrieved,
                FactoryIndexOutcome.VALIDATION_FAILURE,
                f"Factory-index response validation failed: {_bounded_failure(exc)}",
                previous=previous,
            )
        if response.status == 304:
            if previous is None or not previous.content_digest:
                return self._record(
                    retrieved,
                    FactoryIndexOutcome.VALIDATION_FAILURE,
                    "Cache-not-modified response had no prior validated metadata.",
                    http_status=304,
                )
            return self._record(
                retrieved,
                FactoryIndexOutcome.CACHE_NOT_MODIFIED,
                "The exact official index reports the retained metadata is unchanged.",
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
                FactoryIndexOutcome.HTTP_FAILURE,
                f"Factory index returned HTTP {response.status}.",
                http_status=response.status,
                previous=previous,
            )
        try:
            if not 0 < len(response.body) <= self.MAXIMUM_BYTES:
                raise PixelFactoryIndexError("Factory-index body exceeds its response boundary")
            digest = self.adapter.validate_content(
                response.body,
                requested_url=PIXEL_FACTORY_INDEX_URL,
                final_url=response.final_url,
                status=200,
                content_type=_header(response.headers, "content-type"),
                content_encoding=_header(response.headers, "content-encoding") or "identity",
            )
            declared = _content_length(response.headers)
            if declared is not None and declared != len(response.body):
                raise PixelFactoryIndexError("Factory-index response was truncated")
            parsed = parse_pixel_factory_index(response.body)
        except (PixelFactoryIndexError, OnlineEvidenceError, UnicodeError) as exc:
            return self._record(
                retrieved,
                FactoryIndexOutcome.VALIDATION_FAILURE,
                f"Factory-index validation failed: {_bounded_failure(exc)}",
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
            FactoryIndexOutcome.SUCCESS,
            "Exact Pixel 6/oriole official factory-index metadata retained; compatibility remains unconfirmed.",
            published_at=published.isoformat() if published else "",
            http_status=200,
            content_bytes=len(response.body),
            parsed_release_count=len(parsed.entries),
            content_digest=digest,
            etag=etag,
            last_modified=last_modified,
            matched_claim_ids=claim_ids,
            retained_claim_ids=claim_ids,
            archive_digest=archive.archive_digest,
            previous=previous,
        )

    def projections(self, receipt: FactoryIndexReceipt) -> tuple[EvidenceProjection, ...]:
        claims = ()
        if receipt.retained_claim_ids:
            retained = set(receipt.retained_claim_ids)
            claims = tuple(
                claim for claim in self.evidence.load().claims if claim.claim_id in retained
            )
            if len(claims) != len(retained):
                raise PixelFactoryIndexError("Factory-index projection claims are unavailable")
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
                workflow=(
                    "review-firmware-index-metadata",
                    "compare-exact-device-and-artifact",
                    "research-gaps",
                ),
                next_action=(
                    "Compare exact device/build evidence and a separately supplied artifact; "
                    "the index grants no download or installation authority."
                ),
            )
            for consumer in consumers
        )

    def _claims(
        self,
        entries: tuple[FactoryImageEntry, ...],
        retrieved: datetime,
        published: datetime | None,
        freshness: EvidenceFreshness,
        digest: str,
    ):
        claims = []
        for entry in entries:
            scope = EvidenceScope(
                manufacturers=(PIXEL_MANUFACTURER,),
                brands=("Google",),
                models=(PIXEL_MODEL,),
                codenames=(PIXEL_CODENAME,),
                build_ids=(entry.build_id,),
                firmware_versions=(entry.release_label,),
                android_versions=(entry.android_version,),
                regions=((entry.carrier_region_scope,) if entry.carrier_region_scope else ()),
                scope_note="Official Pixel 6/oriole factory-image index row; fit remains unconfirmed.",
            )
            value = json.dumps(asdict(entry), sort_keys=True, separators=(",", ":"))
            claims.append(
                create_claim(
                    claim_key="firmware.factory.release-metadata",
                    scope=scope,
                    source_id=self.adapter.adapter_id,
                    url=PIXEL_FACTORY_INDEX_URL,
                    publisher=self.adapter.publisher,
                    category=SourceCategory.OFFICIAL_FIRMWARE_INDEX,
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
                        "Official firmware-index metadata only; no compatibility, download, "
                        "installation, outcome, or execution authority."
                    ),
                    knowledge_kind=ClaimKind.IDENTITY,
                    affected_builds=(entry.build_id,),
                )
            )
        return tuple(claims)

    def _record(
        self,
        retrieved: datetime,
        outcome: FactoryIndexOutcome,
        reason: str,
        *,
        published_at: str = "",
        http_status: int = 0,
        content_bytes: int = 0,
        parsed_release_count: int = 0,
        content_digest: str = "",
        etag: str = "",
        last_modified: str = "",
        matched_claim_ids: tuple[str, ...] = (),
        retained_claim_ids: tuple[str, ...] | None = None,
        archive_digest: str | None = None,
        previous: FactoryIndexReceipt | None = None,
    ) -> FactoryIndexReceipt:
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
        receipt = FactoryIndexReceipt(
            1,
            "0" * 64,
            PIXEL_FACTORY_INDEX_URL,
            PIXEL_MANUFACTURER,
            PIXEL_MODEL,
            PIXEL_CODENAME,
            retrieved.isoformat(),
            published_at or (previous.published_at if previous and retained else ""),
            outcome,
            scrub_private_text(reason),
            http_status,
            content_bytes,
            parsed_release_count,
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
        return self.receipts.save(receipt)


@dataclass(frozen=True, slots=True)
class _Cell:
    text: str
    links: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Row:
    heading: str
    cells: tuple[_Cell, ...]


@dataclass(frozen=True, slots=True)
class ParsedFactoryIndex:
    modified_at: str
    entries: tuple[FactoryImageEntry, ...]


class _FactoryHTMLParser(HTMLParser):
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
        self._current_heading = ""
        self._row_depth = 0
        self._cells: list[_Cell] = []
        self._cell_tag = ""
        self._cell_depth = 0
        self._cell_parts: list[str] = []
        self._cell_links: list[str] = []

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
        if tag in {"h1", "h2", "h3"} and not self._heading_tag:
            self._heading_tag = tag
            self._heading_parts = []
        if tag == "tr" and not self._row_depth:
            self._row_depth = 1
            self._cells = []
        elif self._row_depth and tag not in self._VOID:
            self._row_depth += 1
        if self._row_depth and tag in {"th", "td"} and not self._cell_tag:
            self._cell_tag = tag
            self._cell_depth = 1
            self._cell_parts = []
            self._cell_links = []
        elif self._cell_tag and tag not in self._VOID and tag not in {"th", "td"}:
            self._cell_depth += 1
        if self._cell_tag and tag == "a" and attributes.get("href"):
            self._cell_links.append(attributes["href"])

    def handle_endtag(self, tag: str) -> None:
        if tag in self._EXCLUDED:
            self._excluded_depth = max(0, self._excluded_depth - 1)
            return
        if self._excluded_depth:
            return
        if self._heading_tag and tag == self._heading_tag:
            text = _visible_text(" ".join(self._heading_parts))
            self.block_count += 1
            if self._heading_tag == "h1":
                self.title = text
            else:
                self._current_heading = text
            self._heading_tag = ""
            self._heading_parts = []
        if self._cell_tag:
            self._cell_depth -= 1
            if self._cell_depth == 0:
                self._cells.append(
                    _Cell(
                        _visible_text(" ".join(self._cell_parts)),
                        tuple(self._cell_links),
                    )
                )
                self._cell_tag = ""
                self._cell_parts = []
                self._cell_links = []
        if self._row_depth:
            self._row_depth -= 1
            if self._row_depth == 0:
                self.block_count += 1
                if self._cells:
                    self.rows.append(_Row(self._current_heading, tuple(self._cells)))
                self._cells = []
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


def parse_pixel_factory_index(payload: bytes) -> ParsedFactoryIndex:
    try:
        decoded = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PixelFactoryIndexError("Factory index is not valid UTF-8") from exc
    parser = _FactoryHTMLParser()
    try:
        parser.feed(decoded)
        parser.close()
    except PixelFactoryIndexError:
        raise
    except Exception as exc:
        raise PixelFactoryIndexError(
            f"Factory-index HTML parser failed with {type(exc).__name__}"
        ) from exc
    if parser.canonical_url != PIXEL_FACTORY_INDEX_URL:
        raise PixelFactoryIndexError("Factory-index canonical URL is missing or changed")
    if not parser.language.casefold().startswith("en"):
        raise PixelFactoryIndexError("Factory index is not the canonical English page")
    if not parser.title or parser.block_count > PixelFactoryIndexAcquirer.MAXIMUM_BLOCKS:
        raise PixelFactoryIndexError("Factory-index page structure exceeds its boundary")
    target_headings = {row.heading for row in parser.rows if _is_oriole_heading(row.heading)}
    if len(target_headings) != 1:
        raise PixelFactoryIndexError("Exact Pixel 6/oriole section is missing or ambiguous")
    rows = tuple(row for row in parser.rows if row.heading in target_headings)
    entries = _entries_from_rows(rows)
    return ParsedFactoryIndex(parser.modified_at, entries)


def _entries_from_rows(rows: tuple[_Row, ...]) -> tuple[FactoryImageEntry, ...]:
    headers: tuple[str, ...] | None = None
    entries: list[FactoryImageEntry] = []
    for row in rows:
        texts = tuple(_key(cell.text) for cell in row.cells)
        if headers is None:
            if "version" not in texts or "download" not in texts or "sha-256 checksum" not in texts:
                continue
            if set(texts) not in (
                {"version", "download", "sha-256 checksum"},
                {"version", "flash", "download", "sha-256 checksum"},
            ) or len(texts) != len(set(texts)):
                raise PixelFactoryIndexError("Factory-index table headings changed")
            headers = texts
            continue
        if len(row.cells) != len(headers):
            raise PixelFactoryIndexError("Factory-index row shape changed")
        indexed = {name: row.cells[position] for position, name in enumerate(headers)}
        entry = _parse_entry(indexed)
        entries.append(entry)
        if len(entries) > PixelFactoryIndexAcquirer.MAXIMUM_RELEASES:
            raise PixelFactoryIndexError("Factory index exceeds its matching-release boundary")
    if headers is None or not entries:
        raise PixelFactoryIndexError("Factory-index reviewed table is missing or empty")
    if len({entry.build_id.casefold() for entry in entries}) != len(entries):
        raise PixelFactoryIndexError("Factory index contains a duplicate or conflicting build")
    if len({entry.image_url for entry in entries}) != len(entries):
        raise PixelFactoryIndexError("Factory index contains a duplicate image identity")
    return tuple(entries)


def _parse_entry(cells: dict[str, _Cell]) -> FactoryImageEntry:
    release = _metadata_text(cells["version"].text, "release label")
    match = re.fullmatch(
        r"(?P<android>\d+(?:\.\d+){1,2})\s*\((?P<body>[^()]*)\)(?:\s+(?P<suffix>.*))?",
        release,
    )
    if not match:
        raise PixelFactoryIndexError("Factory-index release label is invalid")
    parts = tuple(part.strip() for part in match.group("body").split(","))
    if len(parts) < 2 or any(not part for part in parts):
        raise PixelFactoryIndexError("Factory-index build or release date is missing")
    build_id = _metadata_text(parts[0], "build identifier")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,79}", build_id):
        raise PixelFactoryIndexError("Factory-index build identifier is invalid")
    release_date = _metadata_text(parts[1], "release date")
    if not re.fullmatch(
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+20\d{2}",
        release_date,
        re.IGNORECASE,
    ):
        raise PixelFactoryIndexError("Factory-index release date is missing or invalid")
    scope_parts = [*parts[2:]]
    if match.group("suffix"):
        scope_parts.append(match.group("suffix").strip())
    scope = _metadata_text(", ".join(scope_parts), "carrier or region scope", allow_empty=True)
    download = cells["download"]
    if len(download.links) != 1:
        raise PixelFactoryIndexError("Factory-index image URL is missing or ambiguous")
    image_url = _image_url(download.links[0])
    sha256 = _metadata_text(cells["sha-256 checksum"].text, "SHA-256").casefold()
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise PixelFactoryIndexError("Factory-index SHA-256 is missing or invalid")
    return FactoryImageEntry(
        release,
        match.group("android"),
        build_id,
        release_date,
        scope,
        image_url,
        sha256,
    )


def receipt_mapping(receipt: FactoryIndexReceipt) -> dict[str, object]:
    return {"format": FactoryIndexReceiptStore.FORMAT, **asdict(receipt)}


def seal_receipt(receipt: FactoryIndexReceipt) -> FactoryIndexReceipt:
    normalized = replace(
        receipt,
        receipt_id="0" * 64,
        receipt_digest="",
        evidence_state="officially-documented",
        compatibility_hint="UNCONFIRMED",
        execution_authority="none",
        phone_action_allowed=False,
        guardian_approval=False,
        bootloader_relock_allowed=False,
        terms_accepted=False,
        binary_downloaded=False,
        raw_response_retained=False,
    )
    identity = hashlib.sha256(_canonical(receipt_mapping(normalized))).hexdigest()
    normalized = replace(normalized, receipt_id=identity)
    mapping = receipt_mapping(normalized)
    mapping["receipt_digest"] = ""
    return replace(normalized, receipt_digest=hashlib.sha256(_canonical(mapping)).hexdigest())


def parse_receipt(raw: dict[str, object]) -> FactoryIndexReceipt:
    expected = {"format", *(field.name for field in fields(FactoryIndexReceipt))}
    if set(raw) != expected or raw["format"] != FactoryIndexReceiptStore.FORMAT:
        raise PixelFactoryIndexError("Factory-index receipt fields or format are invalid")
    receipt = FactoryIndexReceipt(
        _literal(raw["schema_version"], 1, "schema version"),
        _digest(raw["receipt_id"]),
        _literal(raw["source_url"], PIXEL_FACTORY_INDEX_URL, "source URL"),
        _literal(raw["manufacturer"], PIXEL_MANUFACTURER, "manufacturer"),
        _literal(raw["model"], PIXEL_MODEL, "model"),
        _literal(raw["codename"], PIXEL_CODENAME, "codename"),
        _timestamp(raw["retrieved_at"]),
        _timestamp(raw["published_at"]) if raw["published_at"] else "",
        FactoryIndexOutcome(raw["outcome"]),
        _private_text(raw["reason"], 400),
        _integer(raw["http_status"], 0, 599, "HTTP status"),
        _integer(raw["content_bytes"], 0, PixelFactoryIndexAcquirer.MAXIMUM_BYTES, "content bytes"),
        _integer(
            raw["parsed_release_count"],
            0,
            PixelFactoryIndexAcquirer.MAXIMUM_RELEASES,
            "release count",
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
        _literal(raw["execution_authority"], "none", "execution authority"),
        _literal(raw["phone_action_allowed"], False, "phone action authority"),
        _literal(raw["guardian_approval"], False, "Guardian approval"),
        _literal(raw["bootloader_relock_allowed"], False, "relock authority"),
        _literal(raw["terms_accepted"], False, "terms acceptance"),
        _literal(raw["binary_downloaded"], False, "binary download"),
        _literal(raw["raw_response_retained"], False, "raw response retention"),
    )
    if receipt.outcome is FactoryIndexOutcome.SUCCESS and not (
        receipt.http_status == 200
        and receipt.content_bytes > 0
        and receipt.parsed_release_count > 0
        and receipt.parsed_release_count == len(receipt.matched_claim_ids)
        and receipt.content_digest
        and receipt.matched_claim_ids == receipt.retained_claim_ids
        and receipt.evidence_archive_digest
    ):
        raise PixelFactoryIndexError("Successful factory-index receipt evidence is incomplete")
    if receipt.outcome is FactoryIndexOutcome.CACHE_NOT_MODIFIED and not (
        receipt.http_status == 304
        and receipt.content_digest
        and not receipt.matched_claim_ids
        and receipt.retained_claim_ids
        and receipt.evidence_archive_digest
    ):
        raise PixelFactoryIndexError("Cache-not-modified factory-index receipt is invalid")
    if seal_receipt(replace(receipt, receipt_id="0" * 64, receipt_digest="")) != receipt:
        raise PixelFactoryIndexError("Factory-index receipt digest or identity is invalid")
    return receipt


def _validate_response(response: object) -> None:
    if (
        not isinstance(response, FactoryIndexResponse)
        or isinstance(response.status, bool)
        or not isinstance(response.status, int)
        or not 100 <= response.status <= 599
        or not isinstance(response.headers, Mapping)
        or not isinstance(response.body, bytes)
        or not isinstance(response.final_url, str)
    ):
        raise PixelFactoryIndexError("Factory-index response shape is invalid")


def _is_oriole_heading(value: str) -> bool:
    normalized = _key(value).replace('"', "")
    return normalized in {"oriole for pixel 6", "oriole for pixel 6 devices"}


def _image_url(value: str) -> str:
    if not isinstance(value, str) or len(value) > PixelFactoryIndexAcquirer.MAXIMUM_FIELD_CHARS:
        raise PixelFactoryIndexError("Factory-index image URL is invalid")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "dl.google.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
        or not parsed.path.startswith("/dl/android/aosp/oriole-")
        or not parsed.path.endswith(".zip")
        or parsed.query
        or parsed.fragment
    ):
        raise PixelFactoryIndexError("Factory-index image URL is outside the metadata boundary")
    return value


_EXECUTABLE = re.compile(
    r"(?i)(?:\b(?:adb|fastboot|flash-all|relock|unlock|bootloader|sudo|powershell|cmd\.exe)\b|&&|\|\||\$\(|`|[<>])"
)


def _metadata_text(value: object, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise PixelFactoryIndexError(f"Factory-index {label} is invalid")
    text = " ".join(value.split())
    if (not text and not allow_empty) or len(text) > PixelFactoryIndexAcquirer.MAXIMUM_FIELD_CHARS:
        raise PixelFactoryIndexError(f"Factory-index {label} is missing or oversized")
    if text and (scrub_private_text(text) != text or _EXECUTABLE.search(text)):
        raise PixelFactoryIndexError(f"Factory-index {label} is unsafe")
    return text


def _visible_text(value: str) -> str:
    text = " ".join(value.split())
    if any(ord(character) < 32 for character in text):
        raise PixelFactoryIndexError("Factory-index visible text is invalid")
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


def _identity_key(value: object) -> str:
    if not isinstance(value, str) or len(value) > 80 or scrub_private_text(value) != value:
        return ""
    return " ".join(value.casefold().split())


def _key(value: str) -> str:
    return " ".join(value.casefold().split()).rstrip(".:?")


def _header(headers: Mapping[str, str], name: str) -> str:
    for key, value in headers.items():
        if str(key).casefold() == name.casefold():
            return _safe_header(value)
    return ""


def _safe_header(value: object) -> str:
    if not isinstance(value, str):
        raise PixelFactoryIndexError("Factory-index response header is invalid")
    if _unsafe_header(value):
        raise PixelFactoryIndexError("Factory-index response header is unsafe")
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
        raise PixelFactoryIndexError("Factory-index content length is invalid")
    return int(raw)


def _timestamp(value: object) -> str:
    if not isinstance(value, str):
        raise PixelFactoryIndexError("Factory-index timestamp is invalid")
    try:
        return _aware(datetime.fromisoformat(value)).isoformat()
    except ValueError as exc:
        raise PixelFactoryIndexError("Factory-index timestamp is invalid") from exc


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PixelFactoryIndexError("Factory-index time must include an offset")
    return value.astimezone(UTC)


def _digest(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise PixelFactoryIndexError("Factory-index digest is invalid")
    return value


def _optional_digest(value: object) -> str:
    return "" if value == "" else _digest(value)


def _digests(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > PixelFactoryIndexAcquirer.MAXIMUM_RELEASES:
        raise PixelFactoryIndexError("Factory-index claim identifiers are invalid")
    result = tuple(_digest(item) for item in value)
    if result != tuple(sorted(set(result))):
        raise PixelFactoryIndexError("Factory-index claim identifiers are not canonical")
    return result


def _private_text(value: object, maximum: int) -> str:
    if not isinstance(value, str) or len(value) > maximum or scrub_private_text(value) != value:
        raise PixelFactoryIndexError("Factory-index stored text is unsafe")
    return value


def _integer(value: object, minimum: int, maximum: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise PixelFactoryIndexError(f"Factory-index {label} is invalid")
    return value


def _literal(value: object, expected: object, label: str):
    if type(value) is not type(expected) or value != expected:
        raise PixelFactoryIndexError(f"Factory-index {label} is invalid")
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def _bounded_failure(error: Exception) -> str:
    return scrub_private_text(" ".join(str(error).split()))[:240]
