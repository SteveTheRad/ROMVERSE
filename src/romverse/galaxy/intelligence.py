from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import ipaddress
import json
import re
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from romverse.core.privacy import WorkspacePrivacy
from romverse.device.models import AndroidDevice
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
    KnowledgeKind,
    KnowledgeRecord,
    KnowledgeSource,
    KnowledgeSourceTier,
)
from romverse.knowledge.store import (
    ARCHIVE_SCHEMA_VERSION,
    KnowledgeArchiveError,
    KnowledgeArchiveStore,
    load_packaged_archive,
    merge_archives,
    seal_archive,
)
from romverse.rom.source_identity import xiaomi_build_region


class GalaxyIntelligenceError(RuntimeError):
    """A Galaxy contribution crossed an integrity, privacy, or trust boundary."""


class GalaxyContributionKind(StrEnum):
    COMPATIBILITY = "compatibility"
    FIX = "fix"
    FLASH_OUTCOME = "flash-outcome"
    RECOVERY = "recovery"


class GalaxyOutcome(StrEnum):
    WORKING = "working"
    DEGRADED = "degraded"
    FAILED = "failed"
    RECOVERED = "recovered"
    UNRESOLVED = "unresolved"


class GalaxyEvidenceClass(StrEnum):
    OFFICIAL = "official"
    VERIFIED_COMMUNITY = "verified-community"
    EXPERIMENTAL = "experimental"
    DISPUTED = "disputed"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class GalaxyDevicePattern:
    manufacturer: str
    brand: str
    model: str
    product: str
    codename: str
    build_id: str
    android_version: str
    security_patch: str
    region: str
    slot_scheme: str
    dynamic_partitions: str
    verified_boot_state: str
    pack_id: str
    pattern_digest: str


@dataclass(frozen=True, slots=True)
class GalaxyContributionDraft:
    kind: GalaxyContributionKind
    outcome: GalaxyOutcome
    title: str
    summary: str
    symptoms: tuple[str, ...]
    solution_steps: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    contributor_alias: str = "Local contributor"
    pack_id: str = ""


@dataclass(frozen=True, slots=True)
class GalaxyContributionPreview:
    schema_version: int
    preview_id: str
    created_at: str
    kind: GalaxyContributionKind
    outcome: GalaxyOutcome
    title: str
    summary: str
    symptoms: tuple[str, ...]
    solution_steps: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    contributor_key: str
    device_pattern: GalaxyDevicePattern
    evidence_class: GalaxyEvidenceClass
    duplicate_ids: tuple[str, ...]
    conflict_ids: tuple[str, ...]
    warnings: tuple[str, ...]
    excluded_private_fields: tuple[str, ...]
    eligible_for_queue: bool
    upload_authority: str
    phone_changed: bool
    preview_digest: str


@dataclass(frozen=True, slots=True)
class GalaxyContribution:
    schema_version: int
    contribution_id: str
    created_at: str
    updated_at: str
    kind: GalaxyContributionKind
    outcome: GalaxyOutcome
    title: str
    summary: str
    symptoms: tuple[str, ...]
    solution_steps: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    contributor_key: str
    device_pattern: GalaxyDevicePattern
    evidence_class: GalaxyEvidenceClass
    conflict_ids: tuple[str, ...]
    moderation_reason: str
    moderator_id: str
    corroboration_count: int
    public_source_url: str
    queued_for_review: bool
    uploaded: bool
    execution_authority: str
    phone_changed: bool
    record_digest: str


@dataclass(frozen=True, slots=True)
class GalaxyContributorReputation:
    contributor_key: str
    verified_contributions: int
    corroboration_points: int
    reputation_points: int


@dataclass(frozen=True, slots=True)
class GalaxyIntelligenceDashboard:
    official_records: int
    verified_community: int
    experimental: int
    disputed: int
    rejected: int
    unresolved: int
    queued: int
    device_families: int
    contributors: tuple[GalaxyContributorReputation, ...]
    archive_digest: str


@dataclass(frozen=True, slots=True)
class GalaxyModerationKey:
    key_id: str
    public_key_base64: str
    revoked: bool = False

    def public_key(self) -> Ed25519PublicKey:
        if self.revoked:
            raise GalaxyIntelligenceError("Galaxy moderator key is revoked")
        try:
            raw = base64.b64decode(self.public_key_base64, validate=True)
            if len(raw) != 32:
                raise ValueError("wrong key length")
            return Ed25519PublicKey.from_public_bytes(raw)
        except (ValueError, binascii.Error) as exc:
            raise GalaxyIntelligenceError("Galaxy moderator public key is invalid") from exc


@dataclass(frozen=True, slots=True)
class GalaxyModerationDecision:
    contribution_id: str
    contribution_digest: str
    evidence_class: GalaxyEvidenceClass
    reason: str
    corroboration_count: int
    public_source_url: str


@dataclass(frozen=True, slots=True)
class GalaxyModerationPreview:
    source_path: Path
    update_id: str
    signer_id: str
    issued_at: str
    expires_at: str
    decisions: tuple[GalaxyModerationDecision, ...]
    envelope_sha256: str
    current_ledger_digest: str
    execution_authority: str = "none"
    phone_changed: bool = False


class GalaxyIntelligenceService:
    """Local, opt-in Galaxy evidence queue with no built-in publishing transport."""

    FORMAT = "romverse.galaxy.intelligence"
    SCHEMA_VERSION = 1
    MAX_BYTES = 8 * 1024 * 1024
    MAX_CONTRIBUTIONS = 2_000
    MAX_LIST = 64
    MAX_TEXT = 2_000
    MAX_EVIDENCE = 32
    EXCLUDED_PRIVATE_FIELDS = (
        "device serial",
        "IMEI / MEID",
        "phone number",
        "email address",
        "Wi-Fi identifiers",
        "accounts and personal files",
        "raw logs not explicitly reviewed",
    )
    _SENSITIVE_PATTERNS = (
        ("email address", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
        ("IMEI / long device number", re.compile(r"(?<!\d)\d{14,16}(?!\d)")),
        ("MAC address", re.compile(r"\b(?:[0-9A-F]{2}:){5}[0-9A-F]{2}\b", re.I)),
        ("home-directory path", re.compile(r"(?:/home/|C:\\Users\\)[^\s/\\]+", re.I)),
        (
            "labelled private identifier",
            re.compile(r"\b(?:serial|imei|meid|imsi|phone\s*number)\s*[:=]\s*\S+", re.I),
        ),
    )
    _MALICIOUS_PATTERNS = (
        re.compile(r"\brm\s+-rf\s+(?:/|~|\$HOME)(?:\s|$)", re.I),
        re.compile(r"\b(?:fastboot|fastbootd)\b.*\b(?:flashing\s+lock|oem\s+lock)\b", re.I),
        re.compile(r"\b(?:curl|wget)\b[^\n|]*\|\s*(?:sh|bash)\b", re.I),
        re.compile(r"\b(?:disable|bypass)\b.*\b(?:avb|verified\s+boot|anti-rollback)\b", re.I),
    )

    def __init__(self, workspace: Path, *, sharing_enabled: bool = False) -> None:
        self.workspace = workspace.expanduser().resolve()
        self.root = self.workspace / "galaxy"
        self.path = self.root / "intelligence-v1.json"
        self.privacy = WorkspacePrivacy(self.workspace)
        self.sharing_enabled = bool(sharing_enabled)

    def set_sharing_enabled(self, enabled: bool) -> None:
        self.sharing_enabled = bool(enabled)

    def preview(
        self,
        draft: GalaxyContributionDraft,
        device: AndroidDevice,
    ) -> GalaxyContributionPreview:
        if not isinstance(draft, GalaxyContributionDraft) or not isinstance(device, AndroidDevice):
            raise GalaxyIntelligenceError(
                "A structured contribution and live Device DNA are required"
            )
        title = self._text(draft.title, "title", 160, required=True)
        summary = self._text(draft.summary, "summary", self.MAX_TEXT, required=True)
        alias = self._text(draft.contributor_alias, "contributor alias", 100, required=True)
        symptoms = self._text_list(draft.symptoms, "symptoms", required=True)
        steps = self._text_list(draft.solution_steps, "solution steps")
        evidence_refs = tuple(
            dict.fromkeys(self._evidence_ref(item) for item in draft.evidence_refs)
        )
        pattern = self._device_pattern(device, draft.pack_id)
        contributor_key = self.privacy.pseudonym(f"galaxy:{alias}")
        searchable = "\n".join((title, summary, *symptoms, *steps, *evidence_refs))
        warnings = [
            f"Private data detected: {label}"
            for label, matcher in self._SENSITIVE_PATTERNS
            if matcher.search(searchable)
        ]
        if device.serial and device.serial in searchable:
            warnings.append("Private data detected: connected device serial")
        if any(matcher.search(searchable) for matcher in self._MALICIOUS_PATTERNS):
            warnings.append("Unsafe or malicious instruction pattern requires moderator rejection")
        if not evidence_refs:
            warnings.append(
                "At least one reviewable HTTPS or SHA-256 evidence reference is required"
            )
        if (
            draft.kind in {GalaxyContributionKind.FIX, GalaxyContributionKind.RECOVERY}
            and not steps
        ):
            warnings.append("A fix or recovery contribution needs explicit solution steps")
        identity_payload = {
            "kind": draft.kind.value,
            "outcome": draft.outcome.value,
            "title": title.casefold(),
            "summary": summary.casefold(),
            "symptoms": tuple(item.casefold() for item in symptoms),
            "solution_steps": tuple(item.casefold() for item in steps),
            "evidence_refs": evidence_refs,
            "device_pattern_digest": pattern.pattern_digest,
        }
        identity_digest = _digest(identity_payload)
        contributions = self.load()
        duplicates = tuple(
            item.contribution_id
            for item in contributions
            if self._identity_digest(item) == identity_digest
        )
        conflict_key = self._conflict_key(draft.kind, symptoms, pattern)
        conflicts = tuple(
            item.contribution_id
            for item in contributions
            if self._conflict_key(item.kind, item.symptoms, item.device_pattern) == conflict_key
            and item.outcome is not draft.outcome
            and item.evidence_class is not GalaxyEvidenceClass.REJECTED
        )
        if duplicates:
            warnings.append("An exact duplicate is already present in the local review ledger")
        if conflicts:
            warnings.append("Conflicting outcome evidence exists for this device/build scope")
        unsafe = any(
            item.startswith("Private data detected:") or item.startswith("Unsafe or malicious")
            for item in warnings
        )
        evidence_class = (
            GalaxyEvidenceClass.REJECTED
            if unsafe
            else GalaxyEvidenceClass.DISPUTED
            if conflicts
            else GalaxyEvidenceClass.EXPERIMENTAL
        )
        eligible = bool(not unsafe and not duplicates and evidence_refs)
        created_at = datetime.now(UTC).isoformat()
        payload: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "preview_id": uuid4().hex,
            "created_at": created_at,
            "kind": draft.kind,
            "outcome": draft.outcome,
            "title": title,
            "summary": summary,
            "symptoms": symptoms,
            "solution_steps": steps,
            "evidence_refs": evidence_refs,
            "contributor_key": contributor_key,
            "device_pattern": pattern,
            "evidence_class": evidence_class,
            "duplicate_ids": duplicates,
            "conflict_ids": conflicts,
            "warnings": tuple(warnings),
            "excluded_private_fields": self.EXCLUDED_PRIVATE_FIELDS,
            "eligible_for_queue": eligible,
            "upload_authority": "reviewed-export-only" if self.sharing_enabled else "disabled",
            "phone_changed": False,
        }
        digest_payload = {**payload, "device_pattern": asdict(pattern)}
        return GalaxyContributionPreview(
            **payload,
            preview_digest=_digest(digest_payload),
        )

    def queue(
        self,
        preview: GalaxyContributionPreview,
        accepted_preview_digest: str,
    ) -> GalaxyContribution:
        if not self.sharing_enabled:
            raise GalaxyIntelligenceError(
                "Galaxy contribution sharing is opted out; enable it in Privacy settings first"
            )
        if not isinstance(preview, GalaxyContributionPreview):
            raise GalaxyIntelligenceError("Galaxy contribution preview is invalid")
        if not hmac.compare_digest(preview.preview_digest, accepted_preview_digest):
            raise GalaxyIntelligenceError("The exact privacy preview was not accepted")
        preview_payload = asdict(preview)
        digest = preview_payload.pop("preview_digest")
        if (
            digest != _digest(preview_payload)
            or not preview.eligible_for_queue
            or preview.upload_authority != "reviewed-export-only"
            or preview.phone_changed is not False
        ):
            raise GalaxyIntelligenceError(
                "Galaxy contribution preview failed integrity or privacy review"
            )
        contributions = self.load()
        if any(
            self._identity_digest(item) == self._preview_identity_digest(preview)
            for item in contributions
        ):
            raise GalaxyIntelligenceError("Galaxy contribution became a duplicate after preview")
        now = datetime.now(UTC).isoformat()
        payload: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "contribution_id": uuid4().hex,
            "created_at": now,
            "updated_at": now,
            "kind": preview.kind,
            "outcome": preview.outcome,
            "title": preview.title,
            "summary": preview.summary,
            "symptoms": preview.symptoms,
            "solution_steps": preview.solution_steps,
            "evidence_refs": preview.evidence_refs,
            "contributor_key": preview.contributor_key,
            "device_pattern": preview.device_pattern,
            "evidence_class": preview.evidence_class,
            "conflict_ids": preview.conflict_ids,
            "moderation_reason": "Awaiting evidence moderation",
            "moderator_id": "",
            "corroboration_count": 0,
            "public_source_url": "",
            "queued_for_review": True,
            "uploaded": False,
            "execution_authority": "none",
            "phone_changed": False,
        }
        digest_payload = {**payload, "device_pattern": asdict(preview.device_pattern)}
        contribution = GalaxyContribution(
            **payload,
            record_digest=_digest(digest_payload),
        )
        self._save((contribution, *contributions))
        return contribution

    def export_submission(self, contribution: GalaxyContribution, destination: Path) -> Path:
        if not self.sharing_enabled:
            raise GalaxyIntelligenceError(
                "Galaxy contribution sharing is opted out; enable it in Privacy settings first"
            )
        current = next(
            (item for item in self.load() if item.contribution_id == contribution.contribution_id),
            None,
        )
        if current is None or current.record_digest != contribution.record_digest:
            raise GalaxyIntelligenceError("Galaxy contribution changed before export")
        target = destination.expanduser()
        if target.exists() and target.is_dir():
            target = target / f"romverse-galaxy-{contribution.contribution_id[:12]}.json"
        parent = target.parent.resolve(strict=True)
        if parent.is_relative_to(self.workspace):
            raise GalaxyIntelligenceError(
                "Galaxy submissions must be exported outside the workspace"
            )
        if target.exists() or target.is_symlink():
            raise GalaxyIntelligenceError("Galaxy submission export already exists")
        document = {
            "format": "romverse.galaxy.reviewed-submission",
            "schema_version": 1,
            "privacy": "serial-imei-account-free",
            "submission": asdict(current),
            "upload_authority": "none",
            "phone_changed": False,
        }
        document["export_digest"] = _digest(document)
        try:
            atomic_write_json(target, document, boundary=parent, maximum_bytes=self.MAX_BYTES)
        except LocalStoreError as exc:
            raise GalaxyIntelligenceError("Galaxy submission could not be exported") from exc
        return target

    def load(self) -> tuple[GalaxyContribution, ...]:
        if not self.path.exists() and not self.path.is_symlink():
            return ()
        try:
            payload = read_json_object(
                self.path,
                boundary=self.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            if (
                set(payload) != {"format", "schema_version", "contributions", "ledger_digest"}
                or payload["format"] != self.FORMAT
                or payload["schema_version"] != self.SCHEMA_VERSION
                or not isinstance(payload["contributions"], list)
                or len(payload["contributions"]) > self.MAX_CONTRIBUTIONS
            ):
                raise ValueError("Galaxy intelligence envelope is invalid")
            unsigned = dict(payload)
            ledger_digest = unsigned.pop("ledger_digest")
            if not _sha256(ledger_digest) or not hmac.compare_digest(
                ledger_digest,
                _digest(unsigned),
            ):
                raise ValueError("Galaxy intelligence ledger digest does not match")
            contributions = tuple(self._parse(item) for item in payload["contributions"])
            if len({item.contribution_id for item in contributions}) != len(contributions):
                raise ValueError("Galaxy contribution identifiers are duplicated")
            if (
                tuple(sorted(contributions, key=lambda item: item.created_at, reverse=True))
                != contributions
            ):
                raise ValueError("Galaxy intelligence ledger is not ordered")
            return contributions
        except (LocalStoreError, OSError, TypeError, ValueError, KeyError) as exc:
            raise GalaxyIntelligenceError(
                f"Galaxy intelligence ledger is unreadable: {exc}"
            ) from exc

    def dashboard(self) -> GalaxyIntelligenceDashboard:
        contributions = self.load()
        archive_digest = ""
        official = 0
        try:
            store = KnowledgeArchiveStore(self.workspace)
            archive = store.load() if store.path.exists() else load_packaged_archive()
        except (KnowledgeArchiveError, OSError):
            archive = None
        if archive is not None:
            archive_digest = archive.bundle_digest
            sources = {item.source_id: item for item in archive.sources}
            official = sum(
                any(
                    sources[source_id].tier
                    in {KnowledgeSourceTier.OFFICIAL_PLATFORM, KnowledgeSourceTier.OFFICIAL_VENDOR}
                    for source_id in record.source_ids
                )
                for record in archive.records
            )
        verified = tuple(
            item
            for item in contributions
            if item.evidence_class is GalaxyEvidenceClass.VERIFIED_COMMUNITY
        )
        reputation: dict[str, tuple[int, int]] = {}
        for item in verified:
            count, corroboration = reputation.get(item.contributor_key, (0, 0))
            reputation[item.contributor_key] = (
                count + 1,
                corroboration + item.corroboration_count,
            )
        contributors = tuple(
            sorted(
                (
                    GalaxyContributorReputation(
                        key, count, corroboration, count * 10 + corroboration
                    )
                    for key, (count, corroboration) in reputation.items()
                ),
                key=lambda item: (item.reputation_points, item.contributor_key),
                reverse=True,
            )
        )
        return GalaxyIntelligenceDashboard(
            official,
            len(verified),
            sum(item.evidence_class is GalaxyEvidenceClass.EXPERIMENTAL for item in contributions),
            sum(item.evidence_class is GalaxyEvidenceClass.DISPUTED for item in contributions),
            sum(item.evidence_class is GalaxyEvidenceClass.REJECTED for item in contributions),
            sum(item.outcome is GalaxyOutcome.UNRESOLVED for item in contributions),
            sum(item.queued_for_review for item in contributions),
            len({item.device_pattern.pattern_digest for item in contributions}),
            contributors,
            archive_digest,
        )

    def unresolved(self) -> tuple[GalaxyContribution, ...]:
        return tuple(
            item
            for item in self.load()
            if item.outcome is GalaxyOutcome.UNRESOLVED
            or item.evidence_class in {GalaxyEvidenceClass.DISPUTED, GalaxyEvidenceClass.REJECTED}
        )

    def apply_moderation(
        self,
        decisions: tuple[GalaxyModerationDecision, ...],
        moderator_id: str,
    ) -> tuple[GalaxyContribution, ...]:
        moderator = self._text(moderator_id, "moderator identity", 96, required=True)
        current_items = self.load()
        current = {item.contribution_id: item for item in current_items}
        updated: list[GalaxyContribution] = []
        changed: list[GalaxyContribution] = []
        now = datetime.now(UTC).isoformat()
        for decision in decisions:
            if decision.evidence_class not in {
                GalaxyEvidenceClass.VERIFIED_COMMUNITY,
                GalaxyEvidenceClass.DISPUTED,
                GalaxyEvidenceClass.REJECTED,
            }:
                raise GalaxyIntelligenceError(
                    "Galaxy moderation cannot grant official or experimental evidence status"
                )
            if decision.evidence_class is GalaxyEvidenceClass.VERIFIED_COMMUNITY and (
                decision.corroboration_count < 1 or not decision.public_source_url
            ):
                raise GalaxyIntelligenceError(
                    "Verified community evidence needs corroboration and a public evidence page"
                )
            if decision.public_source_url:
                normalized_url = self._public_url(decision.public_source_url)
                if normalized_url != decision.public_source_url:
                    raise GalaxyIntelligenceError("Galaxy moderation evidence URL is not canonical")
            if not self._valid_text(decision.reason, 600, required=True):
                raise GalaxyIntelligenceError("Galaxy moderation reason is invalid")
            if type(decision.corroboration_count) is not int or not (
                0 <= decision.corroboration_count <= 100_000
            ):
                raise GalaxyIntelligenceError("Galaxy moderation corroboration count is invalid")
            item = current.get(decision.contribution_id)
            if item is None or item.record_digest != decision.contribution_digest:
                raise GalaxyIntelligenceError(
                    "Galaxy moderation decision does not match the current contribution"
                )
            payload = asdict(item)
            payload.pop("record_digest")
            payload.update(
                {
                    "updated_at": now,
                    "evidence_class": decision.evidence_class,
                    "moderation_reason": decision.reason,
                    "moderator_id": moderator,
                    "corroboration_count": decision.corroboration_count,
                    "public_source_url": decision.public_source_url,
                    "queued_for_review": False,
                }
            )
            revised = GalaxyContribution(
                **{**payload, "device_pattern": item.device_pattern},
                record_digest=_digest(payload),
            )
            current[item.contribution_id] = revised
            changed.append(revised)
        for item in current_items:
            updated.append(current[item.contribution_id])
        verified = tuple(
            item
            for item in changed
            if item.evidence_class is GalaxyEvidenceClass.VERIFIED_COMMUNITY
        )
        if verified:
            self._promote_to_synapse(verified)
        self._save(tuple(updated))
        return tuple(changed)

    def _promote_to_synapse(self, contributions: tuple[GalaxyContribution, ...]) -> None:
        current = KnowledgeArchiveStore(self.workspace).ensure_seeded()
        sources = []
        records = []
        for item in contributions:
            if item.corroboration_count < 1 or not item.public_source_url:
                raise GalaxyIntelligenceError(
                    "Verified community promotion requires corroboration and a public evidence page"
                )
            source_id = f"galaxy.{item.contribution_id}"
            sources.append(
                KnowledgeSource(
                    source_id,
                    f"Galaxy verified contribution {item.contribution_id[:12]}",
                    f"Galaxy contributor {item.contributor_key[:10]}",
                    item.public_source_url,
                    KnowledgeSourceTier.COMMUNITY,
                    "Signed moderator decision over a privacy-reviewed contribution",
                    datetime.now(UTC).date().isoformat(),
                )
            )
            kind = {
                GalaxyContributionKind.COMPATIBILITY: KnowledgeKind.COMPATIBILITY,
                GalaxyContributionKind.FIX: KnowledgeKind.FIX,
                GalaxyContributionKind.FLASH_OUTCOME: KnowledgeKind.GUIDE,
                GalaxyContributionKind.RECOVERY: KnowledgeKind.RECOVERY,
            }[item.kind]
            pattern = item.device_pattern
            scope_note = (
                f"Community evidence scoped to {pattern.manufacturer or 'unknown maker'} "
                f"{pattern.model or pattern.codename or 'unknown model'}, build "
                f"{pattern.build_id or 'unconfirmed'}; not execution authority."
            )
            records.append(
                KnowledgeRecord(
                    f"galaxy.{item.contribution_id}",
                    1,
                    item.title,
                    kind,
                    item.summary,
                    item.symptoms,
                    (),
                    (f"galaxy.{item.kind.value}.{item.outcome.value}",),
                    ("Compare the exact Device DNA and evidence references.",),
                    item.solution_steps,
                    ("Revalidate the exact target, firmware hash, backup and recovery route.",),
                    (f"Reported outcome: {item.outcome.value}",),
                    (
                        f"{pattern.manufacturer} {pattern.model} / {pattern.codename} / "
                        f"{pattern.build_id}",
                    ),
                    ("Every device or build outside the recorded scope",),
                    item.solution_steps if item.kind is GalaxyContributionKind.RECOVERY else (),
                    tuple(
                        dict.fromkeys(
                            (
                                "galaxy",
                                "verified community",
                                item.kind.value,
                                item.outcome.value,
                                pattern.codename,
                            )
                        )
                    ),
                    DeviceKnowledgeScope(
                        manufacturers=(pattern.manufacturer,) if pattern.manufacturer else (),
                        brands=(pattern.brand,) if pattern.brand else (),
                        models=(pattern.model,) if pattern.model else (),
                        codenames=(pattern.codename,) if pattern.codename else (),
                        build_ids=(pattern.build_id,) if pattern.build_id else (),
                        android_versions=(pattern.android_version,)
                        if pattern.android_version
                        else (),
                        bootloader_states=(),
                        partitions=(),
                        scope_note=scope_note,
                    ),
                    (source_id,),
                    KnowledgeConfidence.HIGH,
                    item.corroboration_count,
                    (),
                )
            )
        incoming = seal_archive(
            KnowledgeArchive(
                ARCHIVE_SCHEMA_VERSION,
                "galaxy-verified-community",
                datetime.now(UTC).isoformat(),
                tuple(sources),
                tuple(records),
                "",
            )
        )
        merged, _result = merge_archives(current, incoming)
        KnowledgeArchiveStore(self.workspace).save(merged)

    def _save(self, contributions: tuple[GalaxyContribution, ...]) -> None:
        if len(contributions) > self.MAX_CONTRIBUTIONS:
            raise GalaxyIntelligenceError("Galaxy contribution ledger reached its safe limit")
        payload = {
            "format": self.FORMAT,
            "schema_version": self.SCHEMA_VERSION,
            "contributions": [asdict(item) for item in contributions],
        }
        payload["ledger_digest"] = _digest(payload)
        try:
            ensure_private_directory(self.root, boundary=self.workspace)
            atomic_write_json(
                self.path,
                payload,
                boundary=self.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
        except LocalStoreError as exc:
            raise GalaxyIntelligenceError("Galaxy contribution ledger could not be saved") from exc
        if self.load() != contributions:
            raise GalaxyIntelligenceError(
                "Galaxy contribution ledger failed post-write verification"
            )

    def _parse(self, value: object) -> GalaxyContribution:
        if not isinstance(value, dict):
            raise ValueError("Galaxy contribution must be an object")
        expected = {field.name for field in fields(GalaxyContribution)}
        if set(value) != expected:
            raise ValueError("Galaxy contribution fields do not match schema 1")
        raw = dict(value)
        pattern_raw = raw.pop("device_pattern")
        if not isinstance(pattern_raw, dict):
            raise ValueError("Galaxy Device DNA pattern is invalid")
        pattern = GalaxyDevicePattern(**pattern_raw)
        raw["kind"] = GalaxyContributionKind(raw["kind"])
        raw["outcome"] = GalaxyOutcome(raw["outcome"])
        raw["evidence_class"] = GalaxyEvidenceClass(raw["evidence_class"])
        for field in ("symptoms", "solution_steps", "evidence_refs", "conflict_ids"):
            if not isinstance(raw[field], list):
                raise ValueError(f"Galaxy contribution {field} must be a list")
            raw[field] = tuple(raw[field])
        contribution = GalaxyContribution(**raw, device_pattern=pattern)
        self._validate_contribution(contribution)
        return contribution

    def _validate_contribution(self, item: GalaxyContribution) -> None:
        payload = asdict(item)
        digest = payload.pop("record_digest")
        if (
            item.schema_version != self.SCHEMA_VERSION
            or not re.fullmatch(r"[0-9a-f]{32}", item.contribution_id)
            or not self._timestamp(item.created_at)
            or not self._timestamp(item.updated_at)
            or datetime.fromisoformat(item.created_at) > datetime.fromisoformat(item.updated_at)
            or not self._valid_pattern(item.device_pattern)
            or not re.fullmatch(r"[0-9a-f]{20}", item.contributor_key)
            or not self._valid_text(item.title, 160, required=True)
            or not self._valid_text(item.summary, self.MAX_TEXT, required=True)
            or not self._valid_text_list(item.symptoms, required=True)
            or not self._valid_text_list(item.solution_steps)
            or len(item.evidence_refs) > self.MAX_EVIDENCE
            or any(self._evidence_ref(ref) != ref for ref in item.evidence_refs)
            or len(item.conflict_ids) > self.MAX_LIST
            or any(not re.fullmatch(r"[0-9a-f]{32}", value) for value in item.conflict_ids)
            or not self._valid_text(item.moderation_reason, 600, required=True)
            or not self._valid_text(item.moderator_id, 96)
            or type(item.corroboration_count) is not int
            or not 0 <= item.corroboration_count <= 100_000
            or (
                item.public_source_url
                and self._public_url(item.public_source_url) != item.public_source_url
            )
            or type(item.queued_for_review) is not bool
            or item.uploaded is not False
            or item.execution_authority != "none"
            or item.phone_changed is not False
            or not _sha256(digest)
            or not hmac.compare_digest(digest, _digest(payload))
        ):
            raise ValueError("Galaxy contribution integrity validation failed")

    def _device_pattern(self, device: AndroidDevice, pack_id: str) -> GalaxyDevicePattern:
        serial = device.serial.strip().casefold()

        def public_value(value: object, label: str, maximum: int) -> str:
            clean = self._text(value, label, maximum)
            return "" if serial and serial in clean.casefold() else clean

        build_id = public_value(device.build_id, "build ID", 180)
        payload = {
            "manufacturer": public_value(device.manufacturer, "manufacturer", 100),
            "brand": public_value(device.brand, "brand", 100),
            "model": public_value(device.model, "model", 140),
            "product": public_value(device.product, "product", 140),
            "codename": public_value(device.codename, "codename", 140),
            "build_id": build_id,
            "android_version": public_value(
                device.android_version,
                "Android version",
                80,
            ),
            "security_patch": public_value(device.security_patch, "security patch", 40),
            "region": self._text(xiaomi_build_region(build_id), "region", 80),
            "slot_scheme": "Virtual A/B"
            if device.virtual_ab is True
            else "A/B"
            if device.ab_update is True
            else "Single-slot"
            if device.ab_update is False
            else "Unconfirmed",
            "dynamic_partitions": _yes_no_unknown(device.dynamic_partitions),
            "verified_boot_state": public_value(
                device.verified_boot,
                "Verified Boot state",
                80,
            ),
            "pack_id": public_value(pack_id, "Device Pack", 180),
        }
        return GalaxyDevicePattern(**payload, pattern_digest=_digest(payload))

    @classmethod
    def _valid_pattern(cls, pattern: GalaxyDevicePattern) -> bool:
        payload = asdict(pattern)
        digest = payload.pop("pattern_digest")
        return bool(
            _sha256(digest)
            and digest == _digest(payload)
            and all(cls._valid_text(value, 180) for value in payload.values())
            and pattern.slot_scheme in {"Virtual A/B", "A/B", "Single-slot", "Unconfirmed"}
            and pattern.dynamic_partitions in {"yes", "no", "unavailable"}
        )

    @classmethod
    def _identity_digest(cls, item: GalaxyContribution) -> str:
        return _digest(
            {
                "kind": item.kind.value,
                "outcome": item.outcome.value,
                "title": item.title.casefold(),
                "summary": item.summary.casefold(),
                "symptoms": tuple(value.casefold() for value in item.symptoms),
                "solution_steps": tuple(value.casefold() for value in item.solution_steps),
                "evidence_refs": item.evidence_refs,
                "device_pattern_digest": item.device_pattern.pattern_digest,
            }
        )

    @staticmethod
    def _preview_identity_digest(item: GalaxyContributionPreview) -> str:
        return _digest(
            {
                "kind": item.kind.value,
                "outcome": item.outcome.value,
                "title": item.title.casefold(),
                "summary": item.summary.casefold(),
                "symptoms": tuple(value.casefold() for value in item.symptoms),
                "solution_steps": tuple(value.casefold() for value in item.solution_steps),
                "evidence_refs": item.evidence_refs,
                "device_pattern_digest": item.device_pattern.pattern_digest,
            }
        )

    @staticmethod
    def _conflict_key(
        kind: GalaxyContributionKind,
        symptoms: tuple[str, ...],
        pattern: GalaxyDevicePattern,
    ) -> str:
        return _digest(
            {
                "kind": kind.value,
                "symptoms": tuple(sorted(value.casefold() for value in symptoms)),
                "device": pattern.pattern_digest,
            }
        )

    @classmethod
    def _text_list(
        cls,
        values: tuple[str, ...],
        label: str,
        *,
        required: bool = False,
    ) -> tuple[str, ...]:
        if not isinstance(values, tuple) or len(values) > cls.MAX_LIST:
            raise GalaxyIntelligenceError(f"Galaxy {label} collection is invalid")
        cleaned = tuple(
            dict.fromkeys(cls._text(item, label, cls.MAX_TEXT, required=True) for item in values)
        )
        if required and not cleaned:
            raise GalaxyIntelligenceError(f"Galaxy {label} are required")
        return cleaned

    @classmethod
    def _valid_text_list(cls, values: tuple[str, ...], *, required: bool = False) -> bool:
        return bool(
            isinstance(values, tuple)
            and len(values) <= cls.MAX_LIST
            and (values or not required)
            and len(set(values)) == len(values)
            and all(cls._valid_text(value, cls.MAX_TEXT, required=True) for value in values)
        )

    @staticmethod
    def _text(value: object, label: str, maximum: int, *, required: bool = False) -> str:
        if not isinstance(value, str):
            raise GalaxyIntelligenceError(f"Galaxy {label} must be text")
        clean = value.strip()
        if (
            len(clean) > maximum
            or (required and not clean)
            or "\x00" in clean
            or any(ord(char) < 32 and char not in "\n\t" for char in clean)
        ):
            raise GalaxyIntelligenceError(f"Galaxy {label} is invalid")
        return clean

    @staticmethod
    def _valid_text(value: object, maximum: int, *, required: bool = False) -> bool:
        try:
            GalaxyIntelligenceService._text(value, "value", maximum, required=required)
        except GalaxyIntelligenceError:
            return False
        return True

    @classmethod
    def _evidence_ref(cls, value: object) -> str:
        text = cls._text(value, "evidence reference", 500, required=True)
        if re.fullmatch(r"sha256:[0-9a-f]{64}", text):
            return text
        return cls._public_url(text)

    @staticmethod
    def _public_url(value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise GalaxyIntelligenceError(
                "Galaxy evidence URLs must be public HTTPS links without credentials or tracking data"
            )
        hostname = parsed.hostname.casefold().rstrip(".")
        if hostname == "localhost" or hostname.endswith(".localhost"):
            raise GalaxyIntelligenceError("Galaxy evidence URLs cannot use a local address")
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            pass
        else:
            if not address.is_global:
                raise GalaxyIntelligenceError("Galaxy evidence URLs cannot use a private address")
        return urlunsplit(("https", parsed.netloc.casefold(), parsed.path or "/", "", ""))

    @staticmethod
    def _timestamp(value: object) -> bool:
        if not isinstance(value, str) or len(value) > 80:
            return False
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return False
        return bool(
            parsed.tzinfo is not None and parsed <= datetime.now(UTC) + timedelta(minutes=5)
        )


class GalaxyModerationService:
    """Verify signed moderation decisions before promoting community evidence."""

    FORMAT = "romverse.galaxy.signed-moderation"
    SCHEMA_VERSION = 1
    DOMAIN = b"ROMVERSE-GALAXY-MODERATION-V1\x00"
    MAX_BYTES = 2 * 1024 * 1024
    _FIELDS = {
        "format",
        "schema_version",
        "update_id",
        "signer_id",
        "signature_algorithm",
        "issued_at",
        "expires_at",
        "decisions",
        "signature",
    }

    def __init__(
        self,
        intelligence: GalaxyIntelligenceService,
        trust_keys: tuple[GalaxyModerationKey, ...],
        *,
        unavailable_reason: str = "No production Galaxy moderator key is configured.",
    ) -> None:
        self.intelligence = intelligence
        self.keys = {self._identifier(item.key_id): item for item in trust_keys}
        if len(self.keys) != len(trust_keys):
            raise GalaxyIntelligenceError("Galaxy moderator key identities are duplicated")
        for item in trust_keys:
            item.public_key()
        self.unavailable_reason = unavailable_reason

    @property
    def configured(self) -> bool:
        return any(not item.revoked for item in self.keys.values())

    def inspect(self, source: Path, *, now: datetime | None = None) -> GalaxyModerationPreview:
        if not self.configured:
            raise GalaxyIntelligenceError(self.unavailable_reason)
        payload = self._read(source)
        document = self._document(payload)
        issued = self._timestamp(document["issued_at"])
        expires = self._timestamp(document["expires_at"])
        current_time = (now or datetime.now(UTC)).astimezone(UTC)
        if (
            issued > current_time + timedelta(minutes=5)
            or expires <= current_time
            or expires <= issued
        ):
            raise GalaxyIntelligenceError("Galaxy moderation validity window is invalid")
        signer_id = self._identifier(document["signer_id"])
        key = self.keys.get(signer_id)
        if key is None:
            raise GalaxyIntelligenceError("Galaxy moderation signer is not trusted")
        try:
            signature = base64.b64decode(str(document["signature"]), validate=True)
        except (ValueError, binascii.Error) as exc:
            raise GalaxyIntelligenceError("Galaxy moderation signature is malformed") from exc
        unsigned = dict(document)
        unsigned.pop("signature")
        try:
            key.public_key().verify(signature, self.DOMAIN + _canonical(unsigned))
        except InvalidSignature as exc:
            raise GalaxyIntelligenceError(
                "Galaxy moderation signature verification failed"
            ) from exc
        raw_decisions = document["decisions"]
        if not isinstance(raw_decisions, list) or not 1 <= len(raw_decisions) <= 500:
            raise GalaxyIntelligenceError("Galaxy moderation decision collection is invalid")
        decisions = tuple(self._decision(value) for value in raw_decisions)
        if len({item.contribution_id for item in decisions}) != len(decisions):
            raise GalaxyIntelligenceError("Galaxy moderation decisions are duplicated")
        return GalaxyModerationPreview(
            source_path=source.resolve(),
            update_id=self._identifier(document["update_id"]),
            signer_id=signer_id,
            issued_at=issued.isoformat(),
            expires_at=expires.isoformat(),
            decisions=decisions,
            envelope_sha256=hashlib.sha256(payload).hexdigest(),
            current_ledger_digest=self._ledger_digest(),
        )

    def apply(self, preview: GalaxyModerationPreview) -> tuple[GalaxyContribution, ...]:
        fresh = self.inspect(preview.source_path)
        if (
            fresh.update_id != preview.update_id
            or fresh.signer_id != preview.signer_id
            or fresh.decisions != preview.decisions
            or not hmac.compare_digest(fresh.envelope_sha256, preview.envelope_sha256)
            or not hmac.compare_digest(fresh.current_ledger_digest, preview.current_ledger_digest)
        ):
            raise GalaxyIntelligenceError(
                "Galaxy moderation bundle or contribution ledger changed after preview"
            )
        return self.intelligence.apply_moderation(fresh.decisions, fresh.signer_id)

    def _ledger_digest(self) -> str:
        if not self.intelligence.path.exists():
            return "0" * 64
        payload = read_json_object(
            self.intelligence.path,
            boundary=self.intelligence.workspace,
            maximum_bytes=self.intelligence.MAX_BYTES,
        )
        digest = payload.get("ledger_digest")
        if not _sha256(digest):
            raise GalaxyIntelligenceError("Galaxy intelligence ledger digest is unavailable")
        return str(digest)

    def _read(self, source: Path) -> bytes:
        unresolved = source.expanduser()
        if unresolved.is_symlink():
            raise GalaxyIntelligenceError("Galaxy moderation bundle cannot be a symbolic link")
        try:
            resolved = unresolved.resolve(strict=True)
            return read_regular_bytes(
                resolved,
                boundary=resolved.parent,
                maximum_bytes=self.MAX_BYTES,
            )
        except (LocalStoreError, OSError) as exc:
            raise GalaxyIntelligenceError("Galaxy moderation bundle is unavailable") from exc

    def _document(self, payload: bytes) -> dict[str, object]:
        try:
            value = json.loads(payload.decode("utf-8"), object_pairs_hook=self._strict_object)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GalaxyIntelligenceError("Galaxy moderation bundle is not valid JSON") from exc
        if not isinstance(value, dict) or set(value) != self._FIELDS:
            raise GalaxyIntelligenceError("Galaxy moderation fields do not match schema 1")
        if (
            value["format"] != self.FORMAT
            or value["schema_version"] != self.SCHEMA_VERSION
            or value["signature_algorithm"] != "ed25519"
        ):
            raise GalaxyIntelligenceError("Galaxy moderation format is unsupported")
        return value

    @staticmethod
    def _decision(value: object) -> GalaxyModerationDecision:
        if not isinstance(value, dict) or set(value) != {
            "contribution_id",
            "contribution_digest",
            "evidence_class",
            "reason",
            "corroboration_count",
            "public_source_url",
        }:
            raise GalaxyIntelligenceError("Galaxy moderation decision fields are invalid")
        try:
            evidence_class = GalaxyEvidenceClass(value["evidence_class"])
        except ValueError as exc:
            raise GalaxyIntelligenceError("Galaxy moderation evidence class is invalid") from exc
        if evidence_class not in {
            GalaxyEvidenceClass.VERIFIED_COMMUNITY,
            GalaxyEvidenceClass.DISPUTED,
            GalaxyEvidenceClass.REJECTED,
        }:
            raise GalaxyIntelligenceError("Galaxy moderation cannot grant official evidence status")
        contribution_id = str(value["contribution_id"])
        digest = str(value["contribution_digest"])
        reason = GalaxyIntelligenceService._text(
            value["reason"],
            "moderation reason",
            600,
            required=True,
        )
        count = value["corroboration_count"]
        raw_url = GalaxyIntelligenceService._text(
            value["public_source_url"],
            "public evidence URL",
            500,
        )
        url = GalaxyIntelligenceService._public_url(raw_url) if raw_url else ""
        if (
            not re.fullmatch(r"[0-9a-f]{32}", contribution_id)
            or not _sha256(digest)
            or type(count) is not int
            or not 0 <= count <= 100_000
            or (evidence_class is GalaxyEvidenceClass.VERIFIED_COMMUNITY and (count < 1 or not url))
        ):
            raise GalaxyIntelligenceError("Galaxy moderation decision is invalid")
        return GalaxyModerationDecision(
            contribution_id,
            digest,
            evidence_class,
            reason,
            count,
            url,
        )

    @staticmethod
    def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise GalaxyIntelligenceError(f"Duplicate Galaxy moderation field: {key}")
            result[key] = value
        return result

    @staticmethod
    def _identifier(value: object) -> str:
        result = str(value).strip().casefold()
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,95}", result):
            raise GalaxyIntelligenceError("Galaxy moderation identifier is invalid")
        return result

    @staticmethod
    def _timestamp(value: object) -> datetime:
        try:
            result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise GalaxyIntelligenceError("Galaxy moderation timestamp is invalid") from exc
        if result.tzinfo is None:
            raise GalaxyIntelligenceError("Galaxy moderation timestamp needs a timezone")
        return result.astimezone(UTC)


def galaxy_moderation_document(
    decisions: tuple[GalaxyModerationDecision, ...],
    *,
    update_id: str,
    signer_id: str,
    issued_at: str,
    expires_at: str,
) -> dict[str, object]:
    return {
        "format": GalaxyModerationService.FORMAT,
        "schema_version": GalaxyModerationService.SCHEMA_VERSION,
        "update_id": GalaxyModerationService._identifier(update_id),
        "signer_id": GalaxyModerationService._identifier(signer_id),
        "signature_algorithm": "ed25519",
        "issued_at": GalaxyModerationService._timestamp(issued_at).isoformat(),
        "expires_at": GalaxyModerationService._timestamp(expires_at).isoformat(),
        "decisions": [asdict(item) for item in decisions],
    }


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sha256(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _yes_no_unknown(value: bool | None) -> str:
    return "yes" if value is True else "no" if value is False else "unavailable"
