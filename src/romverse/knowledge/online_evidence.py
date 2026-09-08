"""Bounded, claim-level online evidence for unfamiliar Android devices.

This module is intentionally acquisition- and execution-inert.  It validates content already
retrieved by a caller, retains exact provenance, and projects conservative evidence summaries.
It neither opens a network connection nor turns source text into a command or Guardian approval.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, fields, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    ensure_private_directory,
    read_json_object,
)


class OnlineEvidenceError(ValueError):
    """Online evidence failed a strict boundary or integrity check."""


class EvidenceState(StrEnum):
    SOURCE_REPORTED = "source-reported"
    OFFICIALLY_DOCUMENTED = "officially-documented"
    INDEPENDENTLY_CORROBORATED = "independently-corroborated"
    FIRMWARE_DERIVED = "firmware-derived"
    LIVE_CONFIRMED = "live-confirmed"
    CONFLICTING = "conflicting"
    UNCONFIRMED = "unconfirmed"
    OUTDATED = "outdated"
    RETIRED = "retired"


class SourceCategory(StrEnum):
    OFFICIAL_OEM = "official-oem"
    OFFICIAL_ANDROID = "official-android"
    OFFICIAL_FIRMWARE_INDEX = "official-firmware-index"
    PUBLIC_DEVICE_TREE = "public-device-tree"
    PUBLIC_KERNEL_TREE = "public-kernel-tree"
    MAINTAINED_TECHNICAL = "maintained-technical"
    MAINTAINER_DOCUMENTATION = "maintainer-documentation"
    TECHNICAL_COMMUNITY = "technical-community"
    FIRMWARE = "firmware"
    LIVE_DEVICE = "live-device"


class EvidenceFreshness(StrEnum):
    CURRENT = "current"
    AGED = "aged"
    STALE = "stale"
    UNCONFIRMED = "unconfirmed"


class EvidenceConsumer(StrEnum):
    DEVICE_DNA = "device-dna"
    COMPATIBILITY_MATRIX = "compatibility-matrix"
    NEXUS = "nexus"
    PATHFINDER = "pathfinder"
    FORESIGHT = "foresight"
    INSIGHT = "insight"
    KNOWLEDGE_ARCHIVES = "knowledge-archives"
    DEVICE_ATLAS = "device-atlas"
    SIMULATION_LAB = "simulation-lab"


class ClaimKind(StrEnum):
    IDENTITY = "identity"
    DIAGNOSTIC = "diagnostic"
    GUIDE = "guide"
    FIX_CLAIM = "fix-claim"
    OUTCOME = "outcome"


@dataclass(frozen=True, slots=True)
class EvidenceScope:
    manufacturers: tuple[str, ...] = ()
    brands: tuple[str, ...] = ()
    models: tuple[str, ...] = ()
    codenames: tuple[str, ...] = ()
    build_ids: tuple[str, ...] = ()
    firmware_versions: tuple[str, ...] = ()
    android_versions: tuple[str, ...] = ()
    regions: tuple[str, ...] = ()
    scope_note: str = ""


@dataclass(frozen=True, slots=True)
class EvidenceSource:
    source_id: str
    url: str
    publisher: str
    category: SourceCategory
    retrieved_at: str
    published_at: str
    freshness: EvidenceFreshness
    content_digest: str
    parser_id: str
    parser_version: str


@dataclass(frozen=True, slots=True)
class OnlineEvidenceClaim:
    claim_id: str
    claim_key: str
    structured_value: str
    supporting_excerpt: str
    scope: EvidenceScope
    source: EvidenceSource
    state: EvidenceState
    confidence: int
    corroborating_claim_ids: tuple[str, ...] = ()
    conflicting_claim_ids: tuple[str, ...] = ()
    status_reason: str = ""
    knowledge_kind: ClaimKind = ClaimKind.IDENTITY
    symptoms: tuple[str, ...] = ()
    error_identifiers: tuple[str, ...] = ()
    prerequisites: tuple[str, ...] = ()
    affected_builds: tuple[str, ...] = ()
    diagnostic_description: str = ""
    remedy_description: str = ""
    expected_result: str = ""
    rollback_recovery_route: str = ""
    outcome_provenance: str = ""
    execution_authority: str = "none"
    phone_action_allowed: bool = False
    guardian_approval: bool = False


_TYPED_CLAIM_FIELDS = {
    "knowledge_kind",
    "symptoms",
    "error_identifiers",
    "prerequisites",
    "affected_builds",
    "diagnostic_description",
    "remedy_description",
    "expected_result",
    "rollback_recovery_route",
    "outcome_provenance",
}


@dataclass(frozen=True, slots=True)
class OnlineEvidenceArchive:
    schema_version: int
    updated_at: str
    claims: tuple[OnlineEvidenceClaim, ...]
    archive_digest: str
    execution_authority: str = "none"
    phone_action_allowed: bool = False
    bootloader_relock_allowed: bool = False


@dataclass(frozen=True, slots=True)
class MergedEvidenceClaim:
    claim_key: str
    scope: EvidenceScope
    state: EvidenceState
    confidence: int
    values: tuple[str, ...]
    claim_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    conflict: bool
    investigation_required: bool


@dataclass(frozen=True, slots=True)
class EvidenceProjection:
    consumer: EvidenceConsumer
    claims: tuple[MergedEvidenceClaim, ...]
    identity_confidence: int
    compatibility_hint: str
    investigation_required: bool
    workflow: tuple[str, ...]
    next_action: str
    execution_authority: str = "none"
    phone_action_allowed: bool = False
    guardian_approval: bool = False
    bootloader_relock_allowed: bool = False


@dataclass(frozen=True, slots=True)
class EvidenceSourceAdapter:
    adapter_id: str
    publisher: str
    category: SourceCategory
    allowed_host: str
    allowed_path_prefix: str
    parser_id: str
    parser_version: str
    content_types: tuple[str, ...]
    maximum_bytes: int
    maximum_claims: int
    freshness_days: int
    minimum_interval_seconds: int
    access_note: str
    exact_url: str = ""
    allow_redirects: bool = False
    requires_authentication: bool = False

    def accepts(self, url: str) -> bool:
        parsed = _safe_url(url)
        if self.exact_url:
            return url == self.exact_url
        return parsed.hostname == self.allowed_host and parsed.path.startswith(
            self.allowed_path_prefix
        )

    def validate_content(
        self,
        content: bytes,
        *,
        requested_url: str,
        final_url: str,
        status: int,
        content_type: str,
        content_encoding: str = "identity",
    ) -> str:
        if status != 200:
            raise OnlineEvidenceError("Evidence source returned a non-success status")
        if not self.accepts(requested_url):
            raise OnlineEvidenceError("Evidence URL is outside the registered source scope")
        if final_url != requested_url and not self.allow_redirects:
            raise OnlineEvidenceError("Evidence source redirected outside the exact request")
        if final_url != requested_url and not self.accepts(final_url):
            raise OnlineEvidenceError("Evidence redirect is outside the registered source scope")
        if content_encoding.casefold() not in {"", "identity"}:
            raise OnlineEvidenceError("Compressed evidence responses are not accepted")
        normalized_type = content_type.partition(";")[0].strip().casefold()
        if normalized_type not in self.content_types:
            raise OnlineEvidenceError("Evidence source content type is not registered")
        if not isinstance(content, bytes) or not 0 < len(content) <= self.maximum_bytes:
            raise OnlineEvidenceError("Evidence source content exceeds its byte boundary")
        return hashlib.sha256(content).hexdigest()


class EvidenceSourceRegistry:
    """Closed-by-default registry; callers may supply an explicit reviewed registry."""

    def __init__(self, adapters: tuple[EvidenceSourceAdapter, ...] | None = None) -> None:
        self._adapters = adapters if adapters is not None else default_source_adapters()
        identities = [adapter.adapter_id for adapter in self._adapters]
        if len(identities) != len(set(identities)):
            raise OnlineEvidenceError("Evidence adapter identities must be unique")
        self._adapters = tuple(sorted(self._adapters, key=lambda item: item.adapter_id))

    @property
    def adapters(self) -> tuple[EvidenceSourceAdapter, ...]:
        return self._adapters

    def resolve(self, url: str) -> EvidenceSourceAdapter:
        matches = tuple(adapter for adapter in self._adapters if adapter.accepts(url))
        if len(matches) != 1:
            raise OnlineEvidenceError("Evidence URL must match exactly one registered adapter")
        return matches[0]


def default_source_adapters() -> tuple[EvidenceSourceAdapter, ...]:
    """Small initial set already represented by repository product evidence."""

    common = {
        "maximum_claims": 128,
        "minimum_interval_seconds": 2,
        "allow_redirects": False,
        "requires_authentication": False,
    }
    return (
        EvidenceSourceAdapter(
            "android.developer-docs",
            "Google Android",
            SourceCategory.OFFICIAL_ANDROID,
            "developer.android.com",
            "/",
            "romverse.android-docs-text",
            "1",
            ("text/html", "text/plain"),
            2 * 1024 * 1024,
            freshness_days=180,
            access_note="Public official documentation; obey published terms and rate limits.",
            **common,
        ),
        EvidenceSourceAdapter(
            "android.google-play-device-catalog",
            "Google Play",
            SourceCategory.OFFICIAL_ANDROID,
            "storage.googleapis.com",
            "/play_public/supported_devices.csv",
            "romverse.google-play-supported-devices",
            "1",
            ("text/csv", "application/octet-stream"),
            16 * 1024 * 1024,
            freshness_days=30,
            access_note="Public official catalog; fixed URL and no authentication or redirects.",
            exact_url="https://storage.googleapis.com/play_public/supported_devices.csv",
            **common,
        ),
        EvidenceSourceAdapter(
            "android.aosp-build-numbers",
            "Android Open Source Project",
            SourceCategory.OFFICIAL_ANDROID,
            "source.android.com",
            "/docs/setup/reference/build-numbers",
            "romverse.aosp-build-numbers",
            "1",
            ("text/html",),
            4 * 1024 * 1024,
            maximum_claims=256,
            freshness_days=30,
            minimum_interval_seconds=2,
            access_note="Public official AOSP build-reference metadata only; follow no links.",
            exact_url="https://source.android.com/docs/setup/reference/build-numbers",
            allow_redirects=False,
            requires_authentication=False,
        ),
        EvidenceSourceAdapter(
            "google.pixel-factory-index",
            "Google Pixel",
            SourceCategory.OFFICIAL_FIRMWARE_INDEX,
            "developers.google.com",
            "/android/images",
            "romverse.google-pixel-factory-index",
            "1",
            ("text/html",),
            4 * 1024 * 1024,
            maximum_claims=256,
            freshness_days=30,
            minimum_interval_seconds=2,
            access_note=(
                "Public official metadata only; do not accept terms, follow links, or download images."
            ),
            exact_url="https://developers.google.com/android/images",
            allow_redirects=False,
            requires_authentication=False,
        ),
        EvidenceSourceAdapter(
            "aosp.source-tree",
            "Android Open Source Project",
            SourceCategory.PUBLIC_DEVICE_TREE,
            "android.googlesource.com",
            "/platform/",
            "romverse.aosp-gitiles",
            "1",
            ("text/plain", "text/html", "application/json"),
            4 * 1024 * 1024,
            freshness_days=90,
            access_note="Public AOSP Gitiles content; preserve license provenance and rate limits.",
            **common,
        ),
        EvidenceSourceAdapter(
            "aosp.kernel-tree",
            "Android Open Source Project",
            SourceCategory.PUBLIC_KERNEL_TREE,
            "android.googlesource.com",
            "/kernel/",
            "romverse.aosp-kernel-gitiles",
            "1",
            ("text/plain", "text/html", "application/json"),
            4 * 1024 * 1024,
            freshness_days=90,
            access_note="Public Android kernel Gitiles content; preserve licensing and rate limits.",
            **common,
        ),
    )


class OnlineEvidenceStore:
    FORMAT = "romverse.online-device-evidence"
    SCHEMA_VERSION = 1
    MAXIMUM_BYTES = 2 * 1024 * 1024
    MAXIMUM_CLAIMS = 512
    NAME = "claims.romverse"

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.expanduser().resolve()
        self.root = self.workspace / "knowledge" / "online-device-evidence"
        self.path = self.root / self.NAME

    def load(self) -> OnlineEvidenceArchive:
        try:
            raw = read_json_object(
                self.path,
                boundary=self.workspace,
                maximum_bytes=self.MAXIMUM_BYTES,
            )
            return parse_archive(raw)
        except (LocalStoreError, OSError, TypeError, ValueError, KeyError) as exc:
            if isinstance(exc, OnlineEvidenceError):
                raise
            raise OnlineEvidenceError(f"Online evidence archive is unavailable: {exc}") from exc

    def save(self, archive: OnlineEvidenceArchive) -> OnlineEvidenceArchive:
        sealed = seal_archive(archive)
        mapping = archive_mapping(sealed)
        parse_archive(json.loads(json.dumps(mapping, allow_nan=False)))
        self.workspace.mkdir(parents=True, exist_ok=True)
        ensure_private_directory(self.workspace, boundary=self.workspace)
        ensure_private_directory(self.workspace / "knowledge", boundary=self.workspace)
        ensure_private_directory(self.root, boundary=self.workspace)
        try:
            atomic_write_json(
                self.path,
                mapping,
                boundary=self.workspace,
                maximum_bytes=self.MAXIMUM_BYTES,
            )
        except LocalStoreError as exc:
            raise OnlineEvidenceError(f"Online evidence could not be saved: {exc}") from exc
        saved = self.load()
        if saved != sealed:
            raise OnlineEvidenceError("Online evidence changed during save verification")
        return saved

    def merge(
        self, incoming: tuple[OnlineEvidenceClaim, ...], *, now: datetime
    ) -> OnlineEvidenceArchive:
        current = self.load() if self.path.exists() else empty_archive(now)
        combined = {claim.claim_id: claim for claim in (*current.claims, *incoming)}
        claims = tuple(sorted(combined.values(), key=lambda item: item.claim_id))
        if len(claims) > self.MAXIMUM_CLAIMS:
            raise OnlineEvidenceError("Online evidence archive exceeds its claim boundary")
        linked = _link_claims(claims)
        return self.save(
            OnlineEvidenceArchive(
                self.SCHEMA_VERSION,
                _time(now),
                linked,
                "",
            )
        )


def create_claim(
    *,
    claim_key: str,
    scope: EvidenceScope,
    source_id: str,
    url: str,
    publisher: str,
    category: SourceCategory,
    retrieved_at: datetime,
    content_digest: str,
    parser_id: str,
    parser_version: str,
    structured_value: str = "",
    supporting_excerpt: str = "",
    published_at: datetime | None = None,
    freshness: EvidenceFreshness = EvidenceFreshness.UNCONFIRMED,
    state: EvidenceState = EvidenceState.SOURCE_REPORTED,
    confidence: int = 0,
    status_reason: str = "",
    knowledge_kind: ClaimKind = ClaimKind.IDENTITY,
    symptoms: tuple[str, ...] = (),
    error_identifiers: tuple[str, ...] = (),
    prerequisites: tuple[str, ...] = (),
    affected_builds: tuple[str, ...] = (),
    diagnostic_description: str = "",
    remedy_description: str = "",
    expected_result: str = "",
    rollback_recovery_route: str = "",
    outcome_provenance: str = "",
) -> OnlineEvidenceClaim:
    key = _token(claim_key, 100)
    source_token = _token(source_id, 100)
    parser_token = _token(parser_id, 100)
    parser_version = _bounded_text(parser_version, 40)
    safe_value = scrub_private_text(_bounded_text(structured_value, 500))
    safe_excerpt = scrub_private_text(_bounded_text(supporting_excerpt, 800))
    if bool(safe_value) == bool(safe_excerpt):
        raise OnlineEvidenceError("A claim requires exactly one structured value or excerpt")
    safe_scope = sanitize_scope(scope)
    source = EvidenceSource(
        source_token,
        _clean_source_url(url),
        scrub_private_text(_bounded_text(publisher, 120)),
        category,
        _time(retrieved_at),
        _time(published_at) if published_at else "",
        freshness,
        _digest(content_digest),
        parser_token,
        parser_version,
    )
    confidence = _integer(confidence, minimum=0, maximum=100, label="claim confidence")
    reason = scrub_private_text(_bounded_text(status_reason, 500))
    typed = {
        "knowledge_kind": ClaimKind(knowledge_kind),
        "symptoms": _guidance_items(symptoms, "symptoms"),
        "error_identifiers": _guidance_items(error_identifiers, "error identifiers"),
        "prerequisites": _guidance_items(prerequisites, "prerequisites"),
        "affected_builds": _guidance_items(affected_builds, "affected builds"),
        "diagnostic_description": _guidance_text(diagnostic_description, 500),
        "remedy_description": _guidance_text(remedy_description, 500),
        "expected_result": _guidance_text(expected_result, 300),
        "rollback_recovery_route": _guidance_text(rollback_recovery_route, 300),
        "outcome_provenance": _guidance_text(outcome_provenance, 500),
    }
    claim_id = _claim_identity(
        key,
        safe_value,
        safe_excerpt,
        safe_scope,
        source,
        **typed,
    )
    return OnlineEvidenceClaim(
        claim_id,
        key,
        safe_value,
        safe_excerpt,
        safe_scope,
        source,
        state,
        confidence,
        status_reason=reason,
        **typed,
    )


def claim_from_registered_content(
    registry: EvidenceSourceRegistry,
    content: bytes,
    *,
    requested_url: str,
    final_url: str,
    status: int,
    content_type: str,
    retrieved_at: datetime,
    claim_key: str,
    scope: EvidenceScope,
    structured_value: str = "",
    supporting_excerpt: str = "",
    published_at: datetime | None = None,
    confidence: int = 0,
    content_encoding: str = "identity",
) -> OnlineEvidenceClaim:
    adapter = registry.resolve(requested_url)
    digest = adapter.validate_content(
        content,
        requested_url=requested_url,
        final_url=final_url,
        status=status,
        content_type=content_type,
        content_encoding=content_encoding,
    )
    if supporting_excerpt:
        try:
            decoded = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise OnlineEvidenceError("Evidence excerpt requires UTF-8 source content") from exc
        if supporting_excerpt not in decoded:
            raise OnlineEvidenceError("Supporting excerpt is not present in the source content")
    freshness = (
        freshness_at(published_at, retrieved_at, adapter.freshness_days)
        if published_at
        else EvidenceFreshness.UNCONFIRMED
    )
    return create_claim(
        claim_key=claim_key,
        scope=scope,
        source_id=adapter.adapter_id,
        url=requested_url,
        publisher=adapter.publisher,
        category=adapter.category,
        retrieved_at=retrieved_at,
        published_at=published_at,
        freshness=freshness,
        content_digest=digest,
        parser_id=adapter.parser_id,
        parser_version=adapter.parser_version,
        structured_value=structured_value,
        supporting_excerpt=supporting_excerpt,
        state=EvidenceState.OFFICIALLY_DOCUMENTED,
        confidence=confidence,
        status_reason="Registered public source; exact applicability still requires comparison.",
    )


def merge_claims(claims: tuple[OnlineEvidenceClaim, ...]) -> tuple[MergedEvidenceClaim, ...]:
    groups: dict[tuple[str, str], list[OnlineEvidenceClaim]] = {}
    for claim in claims:
        scope_key = _canonical(asdict(claim.scope)).decode()
        groups.setdefault((claim.claim_key, scope_key), []).append(claim)
    merged: list[MergedEvidenceClaim] = []
    for (claim_key, _scope_key), items in sorted(groups.items()):
        ordered = sorted(items, key=lambda item: item.claim_id)
        values = tuple(sorted({_claim_value(item) for item in ordered}))
        source_ids = tuple(sorted({item.source.source_id for item in ordered}))
        publishers = {item.source.publisher.casefold() for item in ordered}
        conflict = len(values) > 1 or any(
            item.state is EvidenceState.CONFLICTING for item in ordered
        )
        states = {item.state for item in ordered}
        freshness = {item.source.freshness for item in ordered}
        if conflict:
            state = EvidenceState.CONFLICTING
        elif states == {EvidenceState.RETIRED}:
            state = EvidenceState.RETIRED
        elif states <= {EvidenceState.OUTDATED, EvidenceState.RETIRED} or freshness == {
            EvidenceFreshness.STALE
        }:
            state = EvidenceState.OUTDATED
        elif EvidenceState.LIVE_CONFIRMED in states:
            state = EvidenceState.LIVE_CONFIRMED
        elif EvidenceState.FIRMWARE_DERIVED in states:
            state = EvidenceState.FIRMWARE_DERIVED
        elif len(publishers) > 1:
            state = EvidenceState.INDEPENDENTLY_CORROBORATED
        elif any(
            item.source.category
            in {
                SourceCategory.OFFICIAL_ANDROID,
                SourceCategory.OFFICIAL_OEM,
                SourceCategory.OFFICIAL_FIRMWARE_INDEX,
            }
            for item in ordered
        ):
            state = EvidenceState.OFFICIALLY_DOCUMENTED
        elif EvidenceState.UNCONFIRMED in states:
            state = EvidenceState.UNCONFIRMED
        else:
            state = EvidenceState.SOURCE_REPORTED
        confidence = (
            min(item.confidence for item in ordered)
            if conflict
            else max(item.confidence for item in ordered)
        )
        merged.append(
            MergedEvidenceClaim(
                claim_key,
                ordered[0].scope,
                state,
                confidence,
                values,
                tuple(item.claim_id for item in ordered),
                source_ids,
                conflict,
                conflict
                or state in {EvidenceState.UNCONFIRMED, EvidenceState.OUTDATED}
                or EvidenceFreshness.UNCONFIRMED in freshness,
            )
        )
    return tuple(merged)


def project_evidence(
    claims: tuple[OnlineEvidenceClaim, ...], consumer: EvidenceConsumer
) -> EvidenceProjection:
    merged = merge_claims(claims)
    investigation = not merged or any(item.investigation_required for item in merged)
    confidence = min((item.confidence for item in merged), default=0)
    if not merged:
        next_action = "Gather bounded read-only identity evidence, then research the exact gaps."
    elif any(item.conflict for item in merged):
        next_action = (
            "Compare the conflicting claims with exact firmware and read-only live evidence."
        )
    elif investigation:
        next_action = "Research the remaining exact device and firmware evidence gaps."
    else:
        next_action = (
            "Review the identity and confidence, then continue to Guardian-gated planning."
        )
    return EvidenceProjection(
        consumer,
        merged,
        confidence,
        "UNCONFIRMED" if investigation else "EVIDENCE_AVAILABLE",
        investigation,
        (
            "connect-device-read-only",
            "gather-evidence",
            "research-gaps",
            "show-identity-and-confidence",
            "present-one-next-action",
        ),
        next_action,
    )


def compare_with_later_evidence(
    retained: tuple[OnlineEvidenceClaim, ...], later: tuple[OnlineEvidenceClaim, ...]
) -> tuple[MergedEvidenceClaim, ...]:
    """Retain both sides; a match strengthens a group and a mismatch stays conflicting."""

    return merge_claims((*retained, *later))


def freshness_at(retrieved_at: datetime, now: datetime, freshness_days: int) -> EvidenceFreshness:
    retrieved = _aware(retrieved_at)
    current = _aware(now)
    if current < retrieved:
        return EvidenceFreshness.UNCONFIRMED
    age = current - retrieved
    if age <= timedelta(days=freshness_days):
        return EvidenceFreshness.CURRENT
    if age <= timedelta(days=freshness_days * 2):
        return EvidenceFreshness.AGED
    return EvidenceFreshness.STALE


_PRIVATE_PATTERNS = (
    re.compile(r"(?i)\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b"),
    re.compile(r"(?i)\b(?:imei|serial(?:\s+number)?|account(?:\s+id)?)\s*[:=]\s*[^\s,;]+"),
    re.compile(
        r"(?i)\b(?:api[_ -]?key|access[_ -]?token|refresh[_ -]?token|password|secret)\s*[:=]\s*[^\s,;]+"
    ),
    re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/-]+=*"),
    re.compile(r"(?<!\d)\d{15}(?!\d)"),
    re.compile(r"(?i)(?:/home/[^/\s]+|/Users/[^/\s]+|[A-Z]:\\Users\\[^\\\s]+)(?:[/\\][^\s,;]+)*"),
)


def scrub_private_text(value: str) -> str:
    scrubbed = value
    for pattern in _PRIVATE_PATTERNS:
        scrubbed = pattern.sub("[private]", scrubbed)
    return scrubbed


def sanitize_scope(scope: EvidenceScope) -> EvidenceScope:
    values: dict[str, Any] = {}
    for field in fields(EvidenceScope):
        raw = getattr(scope, field.name)
        if isinstance(raw, tuple):
            cleaned = tuple(
                sorted(
                    {
                        scrub_private_text(_bounded_text(item, 120))
                        for item in raw
                        if scrub_private_text(_bounded_text(item, 120))
                    }
                )
            )
            if len(cleaned) > 32:
                raise OnlineEvidenceError("Evidence scope exceeds its item boundary")
            values[field.name] = cleaned
        else:
            values[field.name] = scrub_private_text(_bounded_text(raw, 300))
    return EvidenceScope(**values)


def empty_archive(now: datetime) -> OnlineEvidenceArchive:
    return OnlineEvidenceArchive(OnlineEvidenceStore.SCHEMA_VERSION, _time(now), (), "")


def archive_mapping(archive: OnlineEvidenceArchive) -> dict[str, object]:
    return {"format": OnlineEvidenceStore.FORMAT, **asdict(archive)}


def seal_archive(archive: OnlineEvidenceArchive) -> OnlineEvidenceArchive:
    upgraded = tuple(_upgrade_claim_identity(claim) for claim in archive.claims)
    normalized = replace(
        archive,
        schema_version=OnlineEvidenceStore.SCHEMA_VERSION,
        claims=_link_claims(upgraded),
        archive_digest="",
        execution_authority="none",
        phone_action_allowed=False,
        bootloader_relock_allowed=False,
    )
    payload = archive_mapping(normalized)
    payload["archive_digest"] = ""
    return replace(normalized, archive_digest=hashlib.sha256(_canonical(payload)).hexdigest())


def parse_archive(raw: dict[str, object]) -> OnlineEvidenceArchive:
    _exact_fields(
        raw,
        {
            "format",
            "schema_version",
            "updated_at",
            "claims",
            "archive_digest",
            "execution_authority",
            "phone_action_allowed",
            "bootloader_relock_allowed",
        },
        "archive",
    )
    if raw["format"] != OnlineEvidenceStore.FORMAT:
        raise OnlineEvidenceError("Online evidence format is invalid")
    if raw["schema_version"] != OnlineEvidenceStore.SCHEMA_VERSION:
        raise OnlineEvidenceError("Online evidence schema version is invalid")
    claims_raw = raw["claims"]
    if not isinstance(claims_raw, list) or len(claims_raw) > OnlineEvidenceStore.MAXIMUM_CLAIMS:
        raise OnlineEvidenceError("Online evidence claims are invalid")
    claims = tuple(_parse_claim(item) for item in claims_raw)
    archive = OnlineEvidenceArchive(
        1,
        _timestamp(raw["updated_at"]),
        claims,
        _digest(raw["archive_digest"]),
        _literal(raw["execution_authority"], "none", "execution authority"),
        _literal(raw["phone_action_allowed"], False, "phone action authority"),
        _literal(raw["bootloader_relock_allowed"], False, "bootloader relock authority"),
    )
    if len({claim.claim_id for claim in claims}) != len(claims):
        raise OnlineEvidenceError("Online evidence claim identities must be unique")
    if _link_claims(claims) != tuple(sorted(claims, key=lambda item: item.claim_id)):
        raise OnlineEvidenceError("Online evidence claim relationships are invalid")
    unsigned = dict(raw)
    supplied_digest = unsigned["archive_digest"]
    unsigned["archive_digest"] = ""
    if _digest(supplied_digest) != hashlib.sha256(_canonical(unsigned)).hexdigest():
        raise OnlineEvidenceError("Online evidence archive digest is invalid")
    return archive


def _parse_claim(raw: object) -> OnlineEvidenceClaim:
    if not isinstance(raw, dict):
        raise OnlineEvidenceError("Online evidence claim must be an object")
    current_fields = {field.name for field in fields(OnlineEvidenceClaim)}
    legacy_fields = current_fields - _TYPED_CLAIM_FIELDS
    raw_fields = frozenset(raw)
    if raw_fields not in {frozenset(current_fields), frozenset(legacy_fields)}:
        raise OnlineEvidenceError("Online evidence claim fields are invalid")
    legacy = raw_fields == frozenset(legacy_fields)
    scope = _parse_scope(raw["scope"])
    source = _parse_source(raw["source"])
    claim = OnlineEvidenceClaim(
        claim_id=_digest(raw["claim_id"]),
        claim_key=_token(raw["claim_key"], 100),
        structured_value=_private_text(raw["structured_value"], 500),
        supporting_excerpt=_private_text(raw["supporting_excerpt"], 800),
        scope=scope,
        source=source,
        state=EvidenceState(raw["state"]),
        confidence=_integer(raw["confidence"], minimum=0, maximum=100, label="claim confidence"),
        corroborating_claim_ids=_tokens(raw["corroborating_claim_ids"], maximum=511, digest=True),
        conflicting_claim_ids=_tokens(raw["conflicting_claim_ids"], maximum=511, digest=True),
        status_reason=_private_text(raw["status_reason"], 500),
        knowledge_kind=(ClaimKind.IDENTITY if legacy else ClaimKind(raw["knowledge_kind"])),
        symptoms=(() if legacy else _guidance_list(raw["symptoms"], "symptoms")),
        error_identifiers=(
            () if legacy else _guidance_list(raw["error_identifiers"], "error identifiers")
        ),
        prerequisites=(() if legacy else _guidance_list(raw["prerequisites"], "prerequisites")),
        affected_builds=(
            () if legacy else _guidance_list(raw["affected_builds"], "affected builds")
        ),
        diagnostic_description=(
            "" if legacy else _guidance_text(raw["diagnostic_description"], 500)
        ),
        remedy_description=("" if legacy else _guidance_text(raw["remedy_description"], 500)),
        expected_result=("" if legacy else _guidance_text(raw["expected_result"], 300)),
        rollback_recovery_route=(
            "" if legacy else _guidance_text(raw["rollback_recovery_route"], 300)
        ),
        outcome_provenance=("" if legacy else _guidance_text(raw["outcome_provenance"], 500)),
        execution_authority=_literal(raw["execution_authority"], "none", "execution authority"),
        phone_action_allowed=_literal(raw["phone_action_allowed"], False, "phone action authority"),
        guardian_approval=_literal(raw["guardian_approval"], False, "Guardian approval"),
    )
    if bool(claim.structured_value) == bool(claim.supporting_excerpt):
        raise OnlineEvidenceError("Stored claim requires exactly one value representation")
    expected_identity = (
        _legacy_claim_identity(claim)
        if legacy
        else _claim_identity(
            claim.claim_key,
            claim.structured_value,
            claim.supporting_excerpt,
            claim.scope,
            claim.source,
            knowledge_kind=claim.knowledge_kind,
            symptoms=claim.symptoms,
            error_identifiers=claim.error_identifiers,
            prerequisites=claim.prerequisites,
            affected_builds=claim.affected_builds,
            diagnostic_description=claim.diagnostic_description,
            remedy_description=claim.remedy_description,
            expected_result=claim.expected_result,
            rollback_recovery_route=claim.rollback_recovery_route,
            outcome_provenance=claim.outcome_provenance,
        )
    )
    if claim.claim_id != expected_identity:
        raise OnlineEvidenceError("Online evidence claim identity is invalid")
    return claim


def _parse_scope(raw: object) -> EvidenceScope:
    if not isinstance(raw, dict):
        raise OnlineEvidenceError("Evidence scope must be an object")
    _exact_fields(raw, {field.name for field in fields(EvidenceScope)}, "scope")
    return sanitize_scope(
        EvidenceScope(
            **{
                field.name: (
                    _texts(raw[field.name], maximum=32, length=120)
                    if field.name != "scope_note"
                    else _bounded_text(raw[field.name], 300)
                )
                for field in fields(EvidenceScope)
            }
        )
    )


def _parse_source(raw: object) -> EvidenceSource:
    if not isinstance(raw, dict):
        raise OnlineEvidenceError("Evidence source must be an object")
    _exact_fields(raw, {field.name for field in fields(EvidenceSource)}, "source")
    return EvidenceSource(
        _token(raw["source_id"], 100),
        _clean_source_url(raw["url"]),
        _private_text(raw["publisher"], 120),
        SourceCategory(raw["category"]),
        _timestamp(raw["retrieved_at"]),
        _timestamp(raw["published_at"]) if raw["published_at"] else "",
        EvidenceFreshness(raw["freshness"]),
        _digest(raw["content_digest"]),
        _token(raw["parser_id"], 100),
        _bounded_text(raw["parser_version"], 40),
    )


def _link_claims(claims: tuple[OnlineEvidenceClaim, ...]) -> tuple[OnlineEvidenceClaim, ...]:
    result: list[OnlineEvidenceClaim] = []
    for claim in claims:
        peers = tuple(
            item
            for item in claims
            if item.claim_id != claim.claim_id
            and item.claim_key == claim.claim_key
            and item.scope == claim.scope
        )
        matching = tuple(
            sorted(item.claim_id for item in peers if _claim_value(item) == _claim_value(claim))
        )
        conflicts = tuple(
            sorted(item.claim_id for item in peers if _claim_value(item) != _claim_value(claim))
        )
        result.append(
            replace(
                claim,
                corroborating_claim_ids=matching,
                conflicting_claim_ids=conflicts,
                state=EvidenceState.CONFLICTING if conflicts else claim.state,
            )
        )
    return tuple(sorted(result, key=lambda item: item.claim_id))


def _claim_value(claim: OnlineEvidenceClaim) -> str:
    return claim.structured_value or claim.supporting_excerpt


def _claim_identity(
    claim_key: str,
    structured_value: str,
    supporting_excerpt: str,
    scope: EvidenceScope,
    source: EvidenceSource,
    *,
    knowledge_kind: ClaimKind,
    symptoms: tuple[str, ...],
    error_identifiers: tuple[str, ...],
    prerequisites: tuple[str, ...],
    affected_builds: tuple[str, ...],
    diagnostic_description: str,
    remedy_description: str,
    expected_result: str,
    rollback_recovery_route: str,
    outcome_provenance: str,
) -> str:
    identity = {
        "claim_key": claim_key,
        "structured_value": structured_value,
        "supporting_excerpt": supporting_excerpt,
        "scope": asdict(scope),
        "source": asdict(source),
        "knowledge_kind": knowledge_kind,
        "symptoms": symptoms,
        "error_identifiers": error_identifiers,
        "prerequisites": prerequisites,
        "affected_builds": affected_builds,
        "diagnostic_description": diagnostic_description,
        "remedy_description": remedy_description,
        "expected_result": expected_result,
        "rollback_recovery_route": rollback_recovery_route,
        "outcome_provenance": outcome_provenance,
    }
    return hashlib.sha256(_canonical(identity)).hexdigest()


def _legacy_claim_identity(claim: OnlineEvidenceClaim) -> str:
    return hashlib.sha256(
        _canonical(
            {
                "claim_key": claim.claim_key,
                "structured_value": claim.structured_value,
                "supporting_excerpt": claim.supporting_excerpt,
                "scope": asdict(claim.scope),
                "source": asdict(claim.source),
            }
        )
    ).hexdigest()


def _upgrade_claim_identity(claim: OnlineEvidenceClaim) -> OnlineEvidenceClaim:
    current = _claim_identity(
        claim.claim_key,
        claim.structured_value,
        claim.supporting_excerpt,
        claim.scope,
        claim.source,
        knowledge_kind=claim.knowledge_kind,
        symptoms=claim.symptoms,
        error_identifiers=claim.error_identifiers,
        prerequisites=claim.prerequisites,
        affected_builds=claim.affected_builds,
        diagnostic_description=claim.diagnostic_description,
        remedy_description=claim.remedy_description,
        expected_result=claim.expected_result,
        rollback_recovery_route=claim.rollback_recovery_route,
        outcome_provenance=claim.outcome_provenance,
    )
    return replace(
        claim,
        claim_id=current,
        corroborating_claim_ids=(),
        conflicting_claim_ids=(),
    )


def _safe_url(value: object):
    if not isinstance(value, str) or len(value) > 2_048:
        raise OnlineEvidenceError("Evidence URL is invalid")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise OnlineEvidenceError("Evidence URL must be public HTTPS without credentials")
    sensitive = {"token", "key", "secret", "password", "account", "serial", "imei"}
    if any(key.casefold() in sensitive for key, _value in parse_qsl(parsed.query)):
        raise OnlineEvidenceError("Evidence URL contains a private query field")
    return parsed


def _clean_source_url(value: object) -> str:
    parsed = _safe_url(value)
    if parsed.fragment:
        raise OnlineEvidenceError("Evidence URL fragments are not retained")
    return str(value)


def _bounded_text(value: object, maximum: int) -> str:
    if not isinstance(value, str):
        raise OnlineEvidenceError("Evidence text must be a string")
    normalized = " ".join(value.split())
    if len(normalized) > maximum:
        raise OnlineEvidenceError("Evidence text exceeds its character boundary")
    return normalized


def _private_text(value: object, maximum: int) -> str:
    text = _bounded_text(value, maximum)
    if scrub_private_text(text) != text:
        raise OnlineEvidenceError("Stored evidence contains privacy-unsafe text")
    return text


_EXECUTABLE_GUIDANCE = re.compile(
    r"(?i)(?:`|<\s*(?:code|script)\b|\b(?:adb|fastboot)\s+(?:-|devices\b|shell\b|install\b|push\b|pull\b|reboot\b|kill-server\b|start-server\b)|\b(?:sudo|powershell|cmd\.exe)\s+)"
)


def _guidance_text(value: object, maximum: int) -> str:
    text = _private_text(value, maximum)
    if _EXECUTABLE_GUIDANCE.search(text):
        raise OnlineEvidenceError("Knowledge descriptions cannot contain executable instructions")
    return text


def _guidance_items(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, tuple) or len(value) > 16:
        raise OnlineEvidenceError(f"Knowledge {label} are invalid")
    return tuple(sorted({_guidance_text(item, 200) for item in value if item}))


def _guidance_list(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > 16:
        raise OnlineEvidenceError(f"Stored knowledge {label} are invalid")
    result = tuple(_guidance_text(item, 200) for item in value)
    if result != tuple(sorted(set(result))):
        raise OnlineEvidenceError(f"Stored knowledge {label} must be sorted and unique")
    return result


def _token(value: object, maximum: int) -> str:
    text = _bounded_text(value, maximum)
    if not text or not re.fullmatch(r"[a-z0-9][a-z0-9._:-]*", text):
        raise OnlineEvidenceError("Evidence identifier is invalid")
    return text


def _digest(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise OnlineEvidenceError("Evidence digest is invalid")
    return value


def _time(value: datetime) -> str:
    return _aware(value).isoformat()


def _aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise OnlineEvidenceError("Evidence time requires a timezone")
    return value.astimezone(UTC)


def _timestamp(value: object) -> str:
    if not isinstance(value, str) or len(value) > 40:
        raise OnlineEvidenceError("Evidence timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise OnlineEvidenceError("Evidence timestamp is invalid") from exc
    return _time(parsed)


def _integer(value: object, *, minimum: int, maximum: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise OnlineEvidenceError(f"{label} is invalid")
    return value


def _literal(value: object, expected: object, label: str):
    if value != expected or type(value) is not type(expected):
        raise OnlineEvidenceError(f"{label} is invalid")
    return expected


def _texts(value: object, *, maximum: int, length: int) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum:
        raise OnlineEvidenceError("Evidence text collection is invalid")
    result = tuple(_bounded_text(item, length) for item in value)
    if tuple(sorted(set(result))) != result:
        raise OnlineEvidenceError("Evidence text collection must be unique and sorted")
    return result


def _tokens(value: object, *, maximum: int, digest: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum:
        raise OnlineEvidenceError("Evidence identifier collection is invalid")
    result = tuple(_digest(item) if digest else _token(item, 100) for item in value)
    if tuple(sorted(set(result))) != result:
        raise OnlineEvidenceError("Evidence identifier collection must be unique and sorted")
    return result


def _exact_fields(raw: dict[str, object], expected: set[str], label: str) -> None:
    if set(raw) != expected:
        raise OnlineEvidenceError(f"Online evidence {label} fields are invalid")


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
