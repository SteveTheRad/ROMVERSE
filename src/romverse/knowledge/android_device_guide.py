"""Bounded official guidance acquisition for Android Studio device connections."""

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

ANDROID_DEVICE_GUIDE_URL = "https://developer.android.com/studio/run/device"
PARSER_ID = "romverse.android-device-connection-guide"
PARSER_VERSION = "1"


class AndroidGuideError(ValueError):
    """The fixed official guide or its receipt failed a bounded contract."""


class GuideOutcome(StrEnum):
    SUCCESS = "success"
    HTTP_FAILURE = "http-failure"
    VALIDATION_FAILURE = "validation-failure"
    CACHE_NOT_MODIFIED = "cache-not-modified"


@dataclass(frozen=True, slots=True)
class GuideRequest:
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
            self.url != ANDROID_DEVICE_GUIDE_URL
            or len(headers) != len(self.headers)
            or set(headers) - allowed
            or headers.get("Accept") != "text/html"
            or headers.get("Accept-Encoding") != "identity"
            or headers.get("User-Agent") != AndroidDeviceGuideAcquirer.USER_AGENT
            or not 0 < self.connect_timeout_seconds <= 15
            or not 0 < self.read_timeout_seconds <= 20
            or not 0 < self.overall_timeout_seconds <= 60
            or not 0 < self.maximum_bytes <= 2 * 1024 * 1024
        ):
            raise AndroidGuideError("Guide request violates the fixed transport contract")


@dataclass(frozen=True, slots=True)
class GuideResponse:
    status: int
    final_url: str
    headers: Mapping[str, str]
    body: bytes


class GuideTransport(Protocol):
    def fetch(self, request: GuideRequest) -> GuideResponse: ...


@dataclass(frozen=True, slots=True)
class GuideBlock:
    heading: str
    tag: str
    text: str


@dataclass(frozen=True, slots=True)
class ParsedGuide:
    canonical_url: str
    language: str
    page_title: str
    modified_at: str
    blocks: tuple[GuideBlock, ...]


@dataclass(frozen=True, slots=True)
class GuideAcquisitionReceipt:
    schema_version: int
    receipt_id: str
    source_url: str
    retrieved_at: str
    published_at: str
    outcome: GuideOutcome
    reason: str
    http_status: int
    content_bytes: int
    content_digest: str
    etag: str
    last_modified: str
    parser_id: str
    parser_version: str
    matched_claim_ids: tuple[str, ...]
    retained_claim_ids: tuple[str, ...]
    evidence_archive_digest: str
    receipt_digest: str
    evidence_state: str = "officially-documented"
    execution_authority: str = "none"
    phone_action_allowed: bool = False
    guardian_approval: bool = False
    bootloader_relock_allowed: bool = False
    raw_response_retained: bool = False


class FixedAndroidGuideHTTPS:
    CHUNK_BYTES = 64 * 1024

    def __init__(self, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._monotonic = monotonic

    def fetch(self, request: GuideRequest) -> GuideResponse:
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
                    raise TimeoutError("Official Android guide overall timeout expired")
                if connection.sock is not None:
                    connection.sock.settimeout(min(request.read_timeout_seconds, remaining))
                chunk = response.read(self.CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > request.maximum_bytes:
                    raise AndroidGuideError("Official Android guide exceeded its response boundary")
                chunks.append(chunk)
            return GuideResponse(
                response.status,
                request.url,
                {name.casefold(): value for name, value in response.getheaders()},
                b"".join(chunks),
            )
        except TimeoutError as exc:
            raise TimeoutError("Official Android guide request timed out") from exc
        finally:
            connection.close()


class GuideReceiptStore:
    FORMAT = "romverse.android-device-guide-acquisition"
    SCHEMA_VERSION = 1
    MAXIMUM_BYTES = 24 * 1024

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.expanduser().resolve()
        self.path = (
            self.workspace
            / "knowledge/online-device-evidence/acquisitions/android-device-guide.romverse"
        )

    def load(self) -> GuideAcquisitionReceipt | None:
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
            if isinstance(exc, AndroidGuideError):
                raise
            raise AndroidGuideError(f"Android guide receipt is unavailable: {exc}") from exc

    def save(self, receipt: GuideAcquisitionReceipt) -> GuideAcquisitionReceipt:
        sealed = seal_receipt(receipt)
        mapping = receipt_mapping(sealed)
        parse_receipt(json.loads(json.dumps(mapping, allow_nan=False)))
        self.workspace.mkdir(parents=True, exist_ok=True)
        ensure_private_directory(self.workspace, boundary=self.workspace)
        ensure_private_directory(self.workspace / "knowledge", boundary=self.workspace)
        ensure_private_directory(
            self.workspace / "knowledge/online-device-evidence",
            boundary=self.workspace,
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
            raise AndroidGuideError("Android guide receipt could not be stored safely") from exc
        loaded = self.load()
        if loaded != sealed:
            raise AndroidGuideError("Android guide receipt changed during save verification")
        return loaded


class AndroidDeviceGuideAcquirer:
    MAXIMUM_BYTES = 2 * 1024 * 1024
    CONNECT_TIMEOUT_SECONDS = 8.0
    READ_TIMEOUT_SECONDS = 12.0
    OVERALL_TIMEOUT_SECONDS = 30.0
    MINIMUM_INTERVAL_SECONDS = 2.0
    USER_AGENT = "ROMVERSE/0.2 fixed-android-device-guide"

    def __init__(
        self,
        workspace: Path,
        *,
        registry: EvidenceSourceRegistry | None = None,
        transport: GuideTransport | None = None,
    ) -> None:
        self.workspace = workspace.expanduser().resolve()
        self.registry = registry or EvidenceSourceRegistry()
        self.adapter = self.registry.resolve(ANDROID_DEVICE_GUIDE_URL)
        self.transport = transport or FixedAndroidGuideHTTPS()
        self.receipts = GuideReceiptStore(self.workspace)
        self.evidence = OnlineEvidenceStore(self.workspace)

    def acquire(self, *, now: datetime | None = None) -> GuideAcquisitionReceipt:
        retrieved = _aware(now or datetime.now(UTC))
        previous = self.receipts.load()
        if previous is not None:
            elapsed = (retrieved - datetime.fromisoformat(previous.retrieved_at)).total_seconds()
            if elapsed < max(self.MINIMUM_INTERVAL_SECONDS, self.adapter.minimum_interval_seconds):
                return self._record(
                    retrieved,
                    GuideOutcome.VALIDATION_FAILURE,
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
        request = GuideRequest(
            ANDROID_DEVICE_GUIDE_URL,
            tuple(sorted(headers.items())),
            self.CONNECT_TIMEOUT_SECONDS,
            self.READ_TIMEOUT_SECONDS,
            self.OVERALL_TIMEOUT_SECONDS,
            self.MAXIMUM_BYTES,
        )
        try:
            response = self.transport.fetch(request)
        except AndroidGuideError as exc:
            return self._record(
                retrieved,
                GuideOutcome.VALIDATION_FAILURE,
                f"Official guide transport validation failed: {_bounded_failure(exc)}",
                previous=previous,
            )
        except (OSError, TimeoutError, http.client.HTTPException) as exc:
            return self._record(
                retrieved,
                GuideOutcome.HTTP_FAILURE,
                f"Official guide request failed: {type(exc).__name__}.",
                previous=previous,
            )
        try:
            _validate_response(response)
            etag = _header(response.headers, "etag")
            last_modified = _header(response.headers, "last-modified")
        except AndroidGuideError as exc:
            return self._record(
                retrieved,
                GuideOutcome.VALIDATION_FAILURE,
                f"Official guide response validation failed: {_bounded_failure(exc)}",
                previous=previous,
            )
        if response.status == 304:
            if previous is None or not previous.content_digest:
                return self._record(
                    retrieved,
                    GuideOutcome.VALIDATION_FAILURE,
                    "Cache-not-modified response had no prior validated guide evidence.",
                    http_status=304,
                )
            return self._record(
                retrieved,
                GuideOutcome.CACHE_NOT_MODIFIED,
                "The exact official guide reports the retained content is unchanged.",
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
                GuideOutcome.HTTP_FAILURE,
                f"Official guide returned HTTP {response.status}.",
                http_status=response.status,
                previous=previous,
            )
        try:
            if not 0 < len(response.body) <= self.MAXIMUM_BYTES:
                raise AndroidGuideError("Official guide body exceeds its response boundary")
            content_type = _header(response.headers, "content-type")
            content_encoding = _header(response.headers, "content-encoding") or "identity"
            digest = self.adapter.validate_content(
                response.body,
                requested_url=ANDROID_DEVICE_GUIDE_URL,
                final_url=response.final_url,
                status=200,
                content_type=content_type,
                content_encoding=content_encoding,
            )
            declared = _content_length(response.headers)
            if declared is not None and declared != len(response.body):
                raise AndroidGuideError("Official guide response was truncated")
            parsed = parse_android_device_guide(response.body)
            excerpts = reviewed_excerpts(parsed)
        except (AndroidGuideError, OnlineEvidenceError, UnicodeError) as exc:
            return self._record(
                retrieved,
                GuideOutcome.VALIDATION_FAILURE,
                f"Official guide validation failed: {_bounded_failure(exc)}",
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
        claims = self._claims(excerpts, retrieved, published, freshness, digest)
        archive = self.evidence.merge(claims, now=retrieved)
        claim_ids = tuple(sorted(claim.claim_id for claim in claims))
        return self._record(
            retrieved,
            GuideOutcome.SUCCESS,
            "Three reviewed official connection-diagnostic claims were retained as guidance only.",
            published_at=published.isoformat() if published else "",
            http_status=200,
            content_bytes=len(response.body),
            content_digest=digest,
            etag=etag,
            last_modified=last_modified,
            matched_claim_ids=claim_ids,
            retained_claim_ids=claim_ids,
            archive_digest=archive.archive_digest,
            previous=previous,
        )

    def projections(self, receipt: GuideAcquisitionReceipt) -> tuple[EvidenceProjection, ...]:
        if not receipt.retained_claim_ids:
            claims = ()
        else:
            archive = self.evidence.load()
            retained = set(receipt.retained_claim_ids)
            claims = tuple(claim for claim in archive.claims if claim.claim_id in retained)
            if len(claims) != len(retained):
                raise AndroidGuideError("Official guide projection claims are unavailable")
        return tuple(
            project_evidence(claims, consumer)
            for consumer in (
                EvidenceConsumer.KNOWLEDGE_ARCHIVES,
                EvidenceConsumer.DEVICE_DNA,
                EvidenceConsumer.NEXUS,
                EvidenceConsumer.INSIGHT,
            )
        )

    def _claims(
        self,
        excerpts: dict[str, str],
        retrieved: datetime,
        published: datetime | None,
        freshness: EvidenceFreshness,
        digest: str,
    ):
        scope = EvidenceScope(
            scope_note="Android development-device host connection; exact device and build unconfirmed."
        )
        definitions = (
            (
                "diagnostic.connection-assistant",
                excerpts["connection-assistant"],
                ("A development device is not detected over USB.",),
                "Review the official Connection Assistant guidance and current host/device evidence.",
                "Follow the visible Android Studio connection checklist without executing source text.",
                "The intended device becomes available for a fresh read-only identity scan.",
            ),
            (
                "diagnostic.usb-cable",
                excerpts["usb-cable"],
                ("A connected device is not visible to Android Studio.",),
                "Compare the current cable with a known data-capable USB connection.",
                "Use a data-capable cable and gather the connection evidence again.",
                "The host can establish a data connection or the cable remains a focused suspect.",
            ),
            (
                "diagnostic.usb-debugging",
                excerpts["usb-debugging"],
                ("The device is connected but unavailable for development inspection.",),
                "Confirm the device-side development connection setting and authorization state.",
                "Review USB debugging state on the intended unlocked device, then rescan read-only.",
                "The device either becomes visible or remains explicitly unconfirmed for investigation.",
            ),
        )
        return tuple(
            create_claim(
                claim_key=key,
                scope=scope,
                source_id="android.developer-device-guide",
                url=ANDROID_DEVICE_GUIDE_URL,
                publisher="Google Android",
                category=SourceCategory.OFFICIAL_ANDROID,
                retrieved_at=retrieved,
                published_at=published,
                freshness=freshness,
                content_digest=digest,
                parser_id=PARSER_ID,
                parser_version=PARSER_VERSION,
                supporting_excerpt=excerpt,
                state=EvidenceState.OFFICIALLY_DOCUMENTED,
                confidence=80,
                status_reason="Official guidance only; no observed outcome or confirmed fix.",
                knowledge_kind=ClaimKind.GUIDE,
                symptoms=symptoms,
                error_identifiers=("android-device-not-detected",),
                prerequisites=("Use the canonical English Android Developers page.",),
                affected_builds=("Exact Android device and build remain unconfirmed.",),
                diagnostic_description=diagnostic,
                remedy_description=remedy,
                expected_result=expected,
                rollback_recovery_route="Stop and preserve the current device state if evidence conflicts.",
            )
            for key, excerpt, symptoms, diagnostic, remedy, expected in definitions
        )

    def _record(
        self,
        retrieved: datetime,
        outcome: GuideOutcome,
        reason: str,
        *,
        published_at: str = "",
        http_status: int = 0,
        content_bytes: int = 0,
        content_digest: str = "",
        etag: str = "",
        last_modified: str = "",
        matched_claim_ids: tuple[str, ...] = (),
        retained_claim_ids: tuple[str, ...] | None = None,
        archive_digest: str | None = None,
        previous: GuideAcquisitionReceipt | None = None,
    ) -> GuideAcquisitionReceipt:
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
        receipt = GuideAcquisitionReceipt(
            1,
            "0" * 64,
            ANDROID_DEVICE_GUIDE_URL,
            retrieved.isoformat(),
            published_at or (previous.published_at if previous and retained else ""),
            outcome,
            scrub_private_text(reason),
            http_status,
            content_bytes,
            digest,
            _safe_header(etag or (previous.etag if previous else "")),
            _safe_header(last_modified or (previous.last_modified if previous else "")),
            PARSER_ID,
            PARSER_VERSION,
            tuple(sorted(matched_claim_ids)),
            tuple(sorted(retained)),
            archive,
            "",
        )
        return self.receipts.save(receipt)


class _GuideHTMLParser(HTMLParser):
    _CAPTURE = {"h1", "h2", "h3", "h4", "p", "li"}
    _EXCLUDED = {"script", "style", "code", "pre", "nav", "footer", "noscript", "template"}
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
        self.blocks: list[GuideBlock] = []
        self._excluded_depth = 0
        self._content_depth = 0
        self._capture_tag = ""
        self._capture_depth = 0
        self._parts: list[str] = []
        self._heading = ""

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
        if (
            not self._excluded_depth
            and self._content_depth
            and not self._capture_tag
            and tag in self._CAPTURE
        ):
            self._capture_tag = tag
            self._capture_depth = 1
            self._parts = []
        elif self._capture_tag and tag not in self._VOID:
            self._capture_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._EXCLUDED:
            self._excluded_depth = max(0, self._excluded_depth - 1)
            return
        if self._capture_tag:
            self._capture_depth -= 1
            if self._capture_depth == 0:
                text = _visible_text(" ".join(self._parts))
                if text:
                    if self._capture_tag.startswith("h"):
                        self._heading = text
                    self.blocks.append(GuideBlock(self._heading, self._capture_tag, text))
                self._capture_tag = ""
                self._parts = []
        if tag in {"main", "article"}:
            self._content_depth = max(0, self._content_depth - 1)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in self._VOID:
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self._capture_tag and not self._excluded_depth:
            self._parts.append(data)


def parse_android_device_guide(payload: bytes) -> ParsedGuide:
    try:
        decoded = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AndroidGuideError("Official guide is not valid UTF-8") from exc
    parser = _GuideHTMLParser()
    try:
        parser.feed(decoded)
        parser.close()
    except AndroidGuideError:
        raise
    except Exception as exc:
        raise AndroidGuideError(
            f"Official guide HTML parser failed with {type(exc).__name__}"
        ) from exc
    if parser.canonical_url != ANDROID_DEVICE_GUIDE_URL:
        raise AndroidGuideError("Official guide canonical URL is missing or changed")
    if not parser.language.casefold().startswith("en"):
        raise AndroidGuideError("Official guide is not the canonical English page")
    titles = tuple(block.text for block in parser.blocks if block.tag == "h1")
    if len(titles) != 1:
        raise AndroidGuideError("Official guide title is missing or ambiguous")
    if len(parser.blocks) > 2_000:
        raise AndroidGuideError("Official guide exceeds its visible-block boundary")
    return ParsedGuide(
        parser.canonical_url,
        parser.language,
        titles[0],
        parser.modified_at,
        tuple(parser.blocks),
    )


def reviewed_excerpts(parsed: ParsedGuide) -> dict[str, str]:
    headings = {_key(block.text) for block in parsed.blocks if block.tag in {"h2", "h3", "h4"}}
    if (
        not {
            "troubleshoot device connection",
            "resolve usb connection issues",
        }
        <= headings
    ):
        raise AndroidGuideError("Required official troubleshooting headings are missing or changed")
    rules = {
        "connection-assistant": (
            "troubleshoot with the connection assistant",
            "step-by-step instructions",
        ),
        "usb-cable": ("check the usb cable", "faulty usb cable"),
        "usb-debugging": ("set up a device for development", "enable usb debugging"),
    }
    excerpts: dict[str, str] = {}
    for identity, (heading, phrase) in rules.items():
        candidates = {
            block.text
            for block in parsed.blocks
            if _key(block.heading) == heading
            and block.tag in {"p", "li"}
            and phrase in _key(block.text)
        }
        if len(candidates) != 1:
            raise AndroidGuideError(
                f"Reviewed official guide section {identity} is missing, changed, or conflicting"
            )
        candidate = next(iter(candidates))
        if scrub_private_text(candidate) != candidate:
            raise AndroidGuideError("Reviewed official guide excerpt contains privacy-unsafe text")
        excerpt = _exact_phrase(candidate, phrase)
        excerpts[identity] = excerpt
    return excerpts


def receipt_mapping(receipt: GuideAcquisitionReceipt) -> dict[str, object]:
    return {"format": GuideReceiptStore.FORMAT, **asdict(receipt)}


def seal_receipt(receipt: GuideAcquisitionReceipt) -> GuideAcquisitionReceipt:
    normalized = replace(
        receipt,
        receipt_id="0" * 64,
        receipt_digest="",
        evidence_state="officially-documented",
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


def parse_receipt(raw: dict[str, object]) -> GuideAcquisitionReceipt:
    expected = {"format", *(field.name for field in fields(GuideAcquisitionReceipt))}
    if set(raw) != expected or raw["format"] != GuideReceiptStore.FORMAT:
        raise AndroidGuideError("Android guide receipt fields or format are invalid")
    receipt = GuideAcquisitionReceipt(
        _literal(raw["schema_version"], 1, "schema version"),
        _digest(raw["receipt_id"]),
        _literal(raw["source_url"], ANDROID_DEVICE_GUIDE_URL, "source URL"),
        _timestamp(raw["retrieved_at"]),
        _timestamp(raw["published_at"]) if raw["published_at"] else "",
        GuideOutcome(raw["outcome"]),
        _private_text(raw["reason"], 300),
        _integer(raw["http_status"], 0, 599, "HTTP status"),
        _integer(
            raw["content_bytes"], 0, AndroidDeviceGuideAcquirer.MAXIMUM_BYTES, "content bytes"
        ),
        _optional_digest(raw["content_digest"]),
        _safe_header(raw["etag"]),
        _safe_header(raw["last_modified"]),
        _literal(raw["parser_id"], PARSER_ID, "parser identity"),
        _literal(raw["parser_version"], PARSER_VERSION, "parser version"),
        _digests(raw["matched_claim_ids"]),
        _digests(raw["retained_claim_ids"]),
        _optional_digest(raw["evidence_archive_digest"]),
        _digest(raw["receipt_digest"]),
        _literal(raw["evidence_state"], "officially-documented", "evidence state"),
        _literal(raw["execution_authority"], "none", "execution authority"),
        _literal(raw["phone_action_allowed"], False, "phone action authority"),
        _literal(raw["guardian_approval"], False, "Guardian approval"),
        _literal(raw["bootloader_relock_allowed"], False, "relock authority"),
        _literal(raw["raw_response_retained"], False, "raw response retention"),
    )
    if receipt.outcome is GuideOutcome.SUCCESS and not (
        receipt.http_status == 200
        and receipt.content_bytes > 0
        and receipt.content_digest
        and len(receipt.matched_claim_ids) == 3
        and receipt.matched_claim_ids == receipt.retained_claim_ids
        and receipt.evidence_archive_digest
    ):
        raise AndroidGuideError("Successful Android guide receipt evidence is incomplete")
    if receipt.outcome is GuideOutcome.CACHE_NOT_MODIFIED and not (
        receipt.http_status == 304
        and receipt.content_digest
        and not receipt.matched_claim_ids
        and receipt.retained_claim_ids
        and receipt.evidence_archive_digest
    ):
        raise AndroidGuideError("Cache-not-modified guide receipt evidence is invalid")
    if seal_receipt(replace(receipt, receipt_id="0" * 64, receipt_digest="")) != receipt:
        raise AndroidGuideError("Android guide receipt digest or identity is invalid")
    return receipt


def _validate_response(response: object) -> None:
    if (
        not isinstance(response, GuideResponse)
        or isinstance(response.status, bool)
        or not isinstance(response.status, int)
        or not 100 <= response.status <= 599
        or not isinstance(response.headers, Mapping)
        or not isinstance(response.body, bytes)
        or not isinstance(response.final_url, str)
    ):
        raise AndroidGuideError("Official guide response shape is invalid")


def _visible_text(value: str) -> str:
    text = " ".join(value.split())
    if any(ord(character) < 32 for character in text):
        raise AndroidGuideError("Official guide visible block is invalid")
    if len(text) > 2_000:
        return ""
    return text


def _exact_phrase(text: str, phrase: str) -> str:
    if not 0 < len(text) <= 360:
        raise AndroidGuideError("Reviewed official guide excerpt exceeds its boundary")
    position = text.casefold().find(phrase)
    if position < 0:
        raise AndroidGuideError("Reviewed official guide phrase is unavailable")
    return text[position : position + len(phrase)]


def _published_time(page_value: str, header_value: str) -> datetime | None:
    if page_value:
        try:
            value = page_value.replace("Z", "+00:00")
            return _aware(datetime.fromisoformat(value))
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
    if not isinstance(value, str):
        raise AndroidGuideError("Official guide response header is invalid")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise AndroidGuideError("Official guide response header is unsafe")
    normalized = " ".join(value.split())
    if len(normalized) > 200:
        raise AndroidGuideError("Official guide response header is unsafe")
    return normalized


def _content_length(headers: Mapping[str, str]) -> int | None:
    raw = _header(headers, "content-length")
    if not raw:
        return None
    if re.fullmatch(r"[0-9]+", raw) is None:
        raise AndroidGuideError("Official guide content length is invalid")
    length = int(raw)
    if not 0 < length <= AndroidDeviceGuideAcquirer.MAXIMUM_BYTES:
        raise AndroidGuideError("Official guide content length exceeds its boundary")
    return length


def _aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise AndroidGuideError("Android guide time requires a timezone")
    return value.astimezone(UTC)


def _timestamp(value: object) -> str:
    if not isinstance(value, str) or len(value) > 40:
        raise AndroidGuideError("Android guide timestamp is invalid")
    try:
        return _aware(datetime.fromisoformat(value)).isoformat()
    except ValueError as exc:
        raise AndroidGuideError("Android guide timestamp is invalid") from exc


def _private_text(value: object, maximum: int) -> str:
    if not isinstance(value, str):
        raise AndroidGuideError("Android guide receipt text is invalid")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise AndroidGuideError("Android guide receipt text is unsafe")
    text = " ".join(value.split())
    if len(text) > maximum or scrub_private_text(text) != text:
        raise AndroidGuideError("Android guide receipt text is unsafe")
    return text


def _bounded_failure(exc: Exception) -> str:
    detail = scrub_private_text(" ".join(str(exc).split()))
    if not detail or len(detail) > 180:
        detail = type(exc).__name__
    return f"{detail}."


def _integer(value: object, minimum: int, maximum: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise AndroidGuideError(f"Android guide receipt {label} is invalid")
    return value


def _literal(value: object, expected: object, label: str):
    if value != expected or type(value) is not type(expected):
        raise AndroidGuideError(f"Android guide receipt {label} is invalid")
    return expected


def _digest(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise AndroidGuideError("Android guide receipt digest is invalid")
    return value


def _optional_digest(value: object) -> str:
    if value == "":
        return ""
    return _digest(value)


def _digests(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > 8:
        raise AndroidGuideError("Android guide receipt claim references are invalid")
    result = tuple(_digest(item) for item in value)
    if result != tuple(sorted(set(result))):
        raise AndroidGuideError("Android guide claim references must be sorted and unique")
    return result


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
