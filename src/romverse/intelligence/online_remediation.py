from __future__ import annotations

import hashlib
import html
import ipaddress
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    bounded_regular_files,
    read_json_object,
)
from romverse.intelligence.action_evidence import (
    LocalActionEvidenceVerifier,
    TypedLocalActionEvidence,
    WorkspaceLocalActionEvidenceVerifier,
)
from romverse.knowledge.android_reference import SOURCES as KNOWLEDGE_SOURCES


class SourceAuthority(StrEnum):
    OFFICIAL = "official"
    MAINTAINER = "maintainer"
    COMMUNITY = "community"
    DISCOVERY = "discovery"


class EvidenceFreshness(StrEnum):
    CURRENT = "current"
    AGED = "aged"
    STALE = "stale"
    UNCONFIRMED = "unconfirmed"


class RemediationDecisionState(StrEnum):
    NO_MATCH = "no-match"
    LOCALLY_VERIFIED = "locally-verified"
    TYPED_ACTION_AVAILABLE = "typed-action-available"
    OFFICIAL_GUIDANCE = "official-guidance"
    REPORTED_RISK = "reported-risk"
    CORROBORATED_HYPOTHESIS = "corroborated-hypothesis"
    COMMUNITY_HYPOTHESIS = "community-hypothesis"
    DISCOVERY_REVIEW = "discovery-review"


@dataclass(frozen=True, slots=True)
class ErrorFingerprint:
    fingerprint_id: str
    category: str
    normalized_error: str
    manufacturer: str = ""
    model: str = ""
    marketing_name: str = ""
    codename: str = ""
    build_id: str = ""
    source_kind: str = ""
    tool_name: str = ""
    tool_version: str = ""

    @classmethod
    def create(
        cls,
        message: str,
        *,
        category: str = "unknown",
        manufacturer: str = "",
        model: str = "",
        marketing_name: str = "",
        codename: str = "",
        build_id: str = "",
        source_kind: str = "",
        tool_name: str = "",
        tool_version: str = "",
    ) -> ErrorFingerprint:
        normalized = _bounded_text(_normalize_error(message), 600)
        values = {
            "category": _token(category, 80),
            "normalized_error": normalized,
            "manufacturer": _bounded_text(manufacturer, 80),
            "model": _bounded_text(model, 120),
            "marketing_name": _bounded_text(marketing_name, 120),
            "codename": _token(codename, 80),
            "build_id": _bounded_text(build_id, 160),
            "source_kind": _token(source_kind, 80),
            "tool_name": _bounded_text(tool_name, 80),
            "tool_version": _bounded_text(tool_version, 80),
        }
        digest = hashlib.sha256(
            json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return cls(digest, **values)

    @property
    def query(self) -> str:
        identity = self.marketing_name or self.model
        parts = (
            identity,
            self.codename,
            self.build_id,
            self.tool_name,
            self.normalized_error,
        )
        return " ".join(part for part in parts if part)[:500]


@dataclass(frozen=True, slots=True)
class OnlineFixCandidate:
    source_id: str
    authority: SourceAuthority
    title: str
    url: str
    summary: str
    exact_tokens: tuple[str, ...] = ()
    corroboration_key: str = ""
    local_action_id: str = ""
    confidence: int = 0
    confirmed_working: bool = False
    retrieved_at: str = ""
    published_at: str = ""
    freshness: EvidenceFreshness = EvidenceFreshness.UNCONFIRMED
    corroboration_count: int = 1
    corroborating_authorities: tuple[SourceAuthority, ...] = ()
    scope_match: str = "unconfirmed"
    confidence_reason: str = ""


@dataclass(frozen=True, slots=True)
class OnlineFixReceipt:
    schema_version: int
    receipt_id: str
    created_at: str
    fingerprint: ErrorFingerprint
    candidates: tuple[OnlineFixCandidate, ...]
    diagnosis: str
    cache_path: str
    receipt_digest: str
    execution_authority: str = "guidance-only"


@dataclass(frozen=True, slots=True)
class RemediationDecision:
    """A deterministic, explainable next-step synthesis with no device authority."""

    state: RemediationDecisionState
    headline: str
    rationale: str
    next_safe_action: str
    lead_signal: str
    lead_source_id: str
    evidence_source_ids: tuple[str, ...]
    locally_verified_source_ids: tuple[str, ...]
    candidate_count: int
    execution_authority: str = "guidance-only"
    phone_action_allowed: bool = False


_TYPED_ACTION_LABELS = {
    "refresh-adb-evidence": "refresh the USB and ADB connection evidence",
    "verify-platform-tools": "verify Android Platform Tools",
    "inspect-payload-source": "inspect the OTA payload source",
    "inspect-avb-topology": "inspect the Verified Boot layout",
    "classify-ota-source": "classify the OTA source",
}

_REPORTED_RISK_PATTERNS = (
    "boot loop",
    "bootloop",
    "bricked",
    "caused data loss",
    "caused a wipe",
    "failed after",
    "not working after",
    "was not working",
)


def candidate_evidence_signal(
    candidate: OnlineFixCandidate,
    *,
    locally_verified: bool = False,
) -> str:
    """Label evidence conservatively; report wording can add caution, never authority."""

    if locally_verified or candidate.confirmed_working:
        return "locally-verified"
    if candidate.local_action_id and candidate.authority in {
        SourceAuthority.OFFICIAL,
        SourceAuthority.MAINTAINER,
    }:
        return "typed-local-action"
    evidence_text = f"{candidate.title} {candidate.summary}".casefold()
    if candidate.authority in {SourceAuthority.MAINTAINER, SourceAuthority.COMMUNITY} and any(
        pattern in evidence_text for pattern in _REPORTED_RISK_PATTERNS
    ):
        return "reported-risk"
    if candidate.authority is SourceAuthority.OFFICIAL:
        return "official-guidance"
    if candidate.authority is SourceAuthority.MAINTAINER:
        return "maintainer-guidance"
    if candidate.authority is SourceAuthority.COMMUNITY:
        return "community-report"
    return "discovery-only"


def synthesize_remediation(
    receipt: OnlineFixReceipt,
    *,
    verified_candidate_keys: frozenset[tuple[str, str, str]] = frozenset(),
) -> RemediationDecision:
    """Turn vetted candidates into one bounded review path without interpreting commands."""

    candidates = receipt.candidates
    if not candidates:
        return RemediationDecision(
            RemediationDecisionState.NO_MATCH,
            "No evidence-backed solution identified",
            "No vetted source matched this exact privacy-scrubbed error fingerprint.",
            "Keep the current evidence unchanged, collect the exact error and Device DNA, then retry or use the matching local Archives guide.",
            "no-match",
            "",
            (),
            (),
            0,
        )

    lead = candidates[0]
    evidence_ids = tuple(dict.fromkeys(item.source_id for item in candidates[:5]))
    verified_source_ids = tuple(
        dict.fromkeys(
            item.source_id
            for item in candidates
            if item.confirmed_working
            or (item.source_id, item.url, item.local_action_id) in verified_candidate_keys
        )
    )
    lead_locally_verified = (
        lead.confirmed_working
        or (lead.source_id, lead.url, lead.local_action_id) in verified_candidate_keys
    )
    lead_signal = candidate_evidence_signal(lead, locally_verified=lead_locally_verified)
    rationale = (
        f"Lead evidence is {lead.authority.value}; scope is {lead.scope_match}; freshness is "
        f"{lead.freshness.value}; corroboration is {lead.corroboration_count} source(s); "
        f"confidence is {lead.confidence}%."
    )
    if lead_locally_verified:
        state = RemediationDecisionState.LOCALLY_VERIFIED
        headline = "A matching typed fix was verified locally"
        next_action = (
            "Review the current evidence and rerun only the same built-in typed action after "
            "Guardian revalidates its exact target and receipt requirements."
        )
    elif lead.local_action_id and lead.authority in {
        SourceAuthority.OFFICIAL,
        SourceAuthority.MAINTAINER,
    }:
        state = RemediationDecisionState.TYPED_ACTION_AVAILABLE
        headline = "A bounded ROMVERSE action can test the leading hypothesis"
        action_label = _TYPED_ACTION_LABELS[lead.local_action_id]
        next_action = (
            f"Open the matching ROMVERSE workflow to {action_label}, review its current "
            "preconditions, and run it only through its typed Guardian boundary."
        )
    elif lead.authority is SourceAuthority.OFFICIAL:
        state = RemediationDecisionState.OFFICIAL_GUIDANCE
        headline = "Official guidance is the strongest current path"
        next_action = (
            "Open the lead official source, confirm its exact model/build/package scope, and "
            "collect the stated evidence before proposing any repair or firmware action."
        )
    elif lead_signal == "reported-risk":
        state = RemediationDecisionState.REPORTED_RISK
        headline = "The leading community evidence reports a failed or harmful outcome"
        next_action = (
            "Do not reproduce the reported action. Compare the failure with official and exact-"
            "device recovery evidence, then use read-only checks to determine whether it applies."
        )
    elif lead.corroboration_count > 1:
        state = RemediationDecisionState.CORROBORATED_HYPOTHESIS
        headline = "Multiple sources support a reviewable hypothesis"
        next_action = (
            "Compare the independent reports with official documentation and the exact Device "
            "Pack, then validate the hypothesis read-only before considering an action."
        )
    elif lead.authority in {SourceAuthority.MAINTAINER, SourceAuthority.COMMUNITY}:
        state = RemediationDecisionState.COMMUNITY_HYPOTHESIS
        headline = "Community or maintainer evidence suggests a hypothesis"
        next_action = (
            "Treat the report as unconfirmed, seek exact-device corroboration, and validate only "
            "with read-only evidence; do not copy its commands into a device workflow."
        )
    else:
        state = RemediationDecisionState.DISCOVERY_REVIEW
        headline = "A discovery result needs authoritative confirmation"
        next_action = (
            "Find an official or recognized maintainer source for the exact device and build "
            "before ROMVERSE treats this as a repair candidate."
        )
    return RemediationDecision(
        state,
        headline,
        rationale,
        next_action,
        lead_signal,
        lead.source_id,
        evidence_ids,
        verified_source_ids,
        len(candidates),
    )


@dataclass(frozen=True, slots=True)
class VerifiedFixOutcome:
    schema_version: int
    outcome_id: str
    created_at: str
    fingerprint_id: str
    source_id: str
    source_url: str
    local_action_id: str
    action_receipt_digest: str
    verification_summary: str
    success: bool
    phone_changed: bool
    outcome_digest: str
    action_evidence_ref: str = ""
    action_evidence_format: str = ""


class OnlineFixProvider(Protocol):
    def search(self, fingerprint: ErrorFingerprint) -> Sequence[OnlineFixCandidate]: ...


@dataclass(frozen=True, slots=True)
class _CatalogEntry:
    source_id: str
    patterns: tuple[str, ...]
    title: str
    url: str
    summary: str
    local_action_id: str = ""


_OFFICIAL_CATALOG = (
    _CatalogEntry(
        "android.adb",
        ("adb", "unauthorized", "device offline", "no devices", "transport"),
        "Android Debug Bridge documentation",
        "https://developer.android.com/tools/adb",
        "Verify the current Platform Tools, USB authorization, transport state, and exact target before retrying the read-only probe.",
        "refresh-adb-evidence",
    ),
    _CatalogEntry(
        "android.platform-tools",
        ("fastboot", "platform tools", "command not found", "executable", "exit code 127"),
        "SDK Platform Tools release notes",
        "https://developer.android.com/tools/releases/platform-tools",
        "ROMVERSE should verify or update the official adb/fastboot package and then rerun the exact version check.",
        "verify-platform-tools",
    ),
    _CatalogEntry(
        "aosp.ota-payload",
        ("payload.bin", "payload", "ota", "update engine"),
        "A/B system updates and OTA payloads",
        "https://source.android.com/docs/core/ota/ab",
        "Treat an OTA payload as a structured update source, extract it with a verified payload tool, and bind every resulting partition hash to the project.",
        "inspect-payload-source",
    ),
    _CatalogEntry(
        "aosp.avb",
        ("avb", "avbtool", "vbmeta", "verity", "verified boot", "hash footer"),
        "Android Verified Boot",
        "https://source.android.com/docs/security/features/verifiedboot/avb",
        "Inspect the exact descriptor topology, algorithms, salts, rollback indices, and chained partitions before proposing any local rebuild or signing action.",
        "inspect-avb-topology",
    ),
    _CatalogEntry(
        "aosp.ota-tools",
        ("ota", "target files", "build ota", "block based"),
        "Build OTA packages",
        "https://source.android.com/docs/core/ota/tools",
        "Identify whether the input is a full or incremental OTA and use the matching source-bound build path.",
        "classify-ota-source",
    ),
    _CatalogEntry(
        "android.build-identity",
        ("device id", "model", "codename", "fingerprint", "build id", "product"),
        "Android Build identity fields",
        "https://developer.android.com/reference/android/os/Build",
        "Compare model, device, product, fingerprint, SDK, incremental, and security-patch evidence as separate fields; do not infer firmware support from one label.",
    ),
    _CatalogEntry(
        "google.play-device-catalog",
        ("retail name", "marketing name", "device catalog", "device id", "unknown model"),
        "Google Play supported Android device catalog",
        "https://storage.googleapis.com/play_public/supported_devices.csv",
        "Use the official catalog for retail naming and device/model identifiers only; it provides no build, partition, recovery, or flash authority.",
    ),
    _CatalogEntry(
        "android.hardware-device",
        ("usb", "driver", "udev", "plugdev", "cable", "wireless debugging"),
        "Run apps on a hardware device",
        "https://developer.android.com/studio/run/device",
        "Check the host-specific USB driver or permissions, data cable, Developer options, authorization, and current Platform Tools before changing the phone.",
    ),
    _CatalogEntry(
        "aosp.update-engine-errors",
        (
            "update engine",
            "update_engine",
            "payload hash mismatch",
            "payload size mismatch",
            "payload timestamp",
            "not enough space",
            "updated but not active",
        ),
        "Android update_engine error definitions",
        "https://android.googlesource.com/platform/system/update_engine/+/refs/heads/main/common/error_code.h",
        "Keep the exact numeric code: transfer, integrity, timestamp, inactive-slot, space, and corruption failures have different recovery paths.",
    ),
    _CatalogEntry(
        "aosp.fastbootd",
        ("fastbootd", "is-userspace", "logical partition", "partition not found", "super"),
        "Userspace fastbootd and logical partitions",
        "https://source.android.com/docs/core/architecture/bootloader/fastbootd",
        "Verify whether the device is in bootloader Fastboot or userspace fastbootd and whether the target is logical before planning any partition operation.",
    ),
    _CatalogEntry(
        "aosp.dynamic-partitions",
        ("dynamic partition", "super partition", "lpmake", "lp metadata", "group size"),
        "Android dynamic partitions",
        "https://source.android.com/docs/core/ota/dynamic_partitions",
        "Compare the exact super geometry, groups, slots, logical partitions, filesystem sizes, and metadata before rebuilding an image set.",
    ),
    _CatalogEntry(
        "aosp.ota-signing",
        ("signature verification", "ota signature", "otacerts", "res keys", "sideload"),
        "Sign Android builds and OTA packages",
        "https://source.android.com/docs/core/ota/sign_builds",
        "Sideloading does not bypass recovery signature checks; inspect the signer and the device recovery trust contract.",
    ),
    _CatalogEntry(
        "aosp.bootloader-lock",
        ("bootloader", "unlock", "locked", "flashing unlock", "factory reset"),
        "Lock and unlock the Android bootloader",
        "https://source.android.com/docs/core/architecture/bootloader/locking_unlocking",
        "Treat unlocking as a destructive, physically confirmed transition that normally erases user data and remains subject to stricter OEM rules.",
    ),
    _CatalogEntry(
        "aosp.gsi",
        ("gsi", "treble", "generic system image", "vts", "cts on gsi"),
        "Android Generic System Images",
        "https://source.android.com/docs/core/tests/vts/gsi",
        "Confirm Treble/vendor interfaces, CPU architecture, launch version, partition layout, AVB, and a recovery route; GSI support does not mean every ROM is compatible.",
    ),
    _CatalogEntry(
        "aosp.compatibility",
        ("compatibility", "compatible", "incompatible", "cdd", "cts", "vts"),
        "Android compatibility program",
        "https://source.android.com/docs/compatibility/overview",
        "Separate Android platform compatibility from exact firmware-to-device compatibility; require device, build, partition, signer, and recovery evidence.",
    ),
    _CatalogEntry(
        "android.apk-signing",
        ("apk", "signature", "certificate", "update incompatible", "apksigner"),
        "Verify APK signatures with apksigner",
        "https://developer.android.com/tools/apksigner",
        "Verify the full APK or split set and compare certificate identity with the installed package before requesting an install or update.",
    ),
    _CatalogEntry(
        "google.pixel-images",
        ("pixel", "factory image", "full ota", "anti rollback"),
        "Factory and full OTA images for Google Pixel",
        "https://developers.google.com/android/images",
        "Read the exact Pixel build notes and checksums; full OTA sideload and factory-image flashing have different prerequisites and data-loss behavior.",
    ),
    _CatalogEntry(
        "xiaomi.hyperos-support",
        ("xiaomi", "redmi", "poco", "hyperos", "miui", "popsicle"),
        "Xiaomi HyperOS update guidance",
        KNOWLEDGE_SOURCES["xiaomi"].url,
        "Check exact model, codename, firmware channel, current build, rollout, and package metadata; physical location alone never blocks compatibility, while a higher marketing version alone is insufficient.",
    ),
    _CatalogEntry(
        "motorola.software-fix",
        ("motorola", "lenovo", "moto", "rescue smart assistant", "software fix"),
        "Motorola Software Fix rescue guidance",
        KNOWLEDGE_SOURCES["motorola"].url,
        "Use Motorola's own identity-matched recovery route when applicable and treat Rescue as data-erasing until the current OEM workflow proves otherwise.",
    ),
    _CatalogEntry(
        "samsung.smart-switch",
        ("samsung", "galaxy", "one ui", "smart switch"),
        "Samsung Smart Switch update and recovery guidance",
        KNOWLEDGE_SOURCES["samsung_update"].url,
        "Use Samsung's current model/carrier-scoped update route; Emergency Software Recovery and Reset is data-erasing and needs separate informed approval.",
    ),
    _CatalogEntry(
        "sony.xperia-companion",
        ("sony", "xperia", "xperia companion"),
        "Sony Xperia Companion software repair",
        KNOWLEDGE_SOURCES["sony_repair"].url,
        "Confirm exact Xperia support, backup state, and account credentials; Software repair deletes internal storage.",
    ),
    _CatalogEntry(
        "oneplus.oxygenos-update",
        ("oneplus", "oxygenos"),
        "OnePlus OxygenOS local update guidance",
        KNOWLEDGE_SOURCES["oneplus_update"].url,
        "Match model, build, package channel, version direction, signer, and digest before treating Local install as applicable.",
    ),
    _CatalogEntry(
        "asus.firmware-update",
        ("asus", "zenfone", "rog phone"),
        "ASUS phone firmware update guidance",
        KNOWLEDGE_SOURCES["asus_update"].url,
        "Require the exact phone model and matching firmware SKU; ASUS documents cross-SKU and downgrade boundaries.",
    ),
    _CatalogEntry(
        "nothing.ota-troubleshooting",
        ("nothing", "nothing os", "cmf"),
        "Nothing OS OTA troubleshooting",
        KNOWLEDGE_SOURCES["nothing_update"].url,
        "Separate network, incomplete-download, storage, battery, and interrupted-install evidence before escalating a repeated exact-device failure.",
    ),
    _CatalogEntry(
        "oppo.coloros-assistant",
        ("oppo", "coloros"),
        "OPPO ColorOS update guidance",
        KNOWLEDGE_SOURCES["oppo_update"].url,
        "Use the official on-phone route or current ColorOS Assistant only when it identifies the exact supported phone and update.",
    ),
    _CatalogEntry(
        "realme.recovery-update",
        ("realme", "realme ui"),
        "realme recovery and update guidance",
        KNOWLEDGE_SOURCES["realme_recovery"].url,
        "Match the exact RMX model, region, UI base, package, battery, storage, and recovery-menu availability before proposing official recovery.",
    ),
    _CatalogEntry(
        "vivo.firmware-update",
        ("vivo", "iqoo", "funtouch", "originos"),
        "vivo and iQOO firmware installation guidance",
        KNOWLEDGE_SOURCES["vivo_update"].url,
        "Classify upgrade, reinstall, or downgrade and require the exact device package; the official path documents downgrade restrictions.",
    ),
    _CatalogEntry(
        "huawei.system-recovery",
        ("huawei", "emui", "harmonyos", "hisuite", "erecovery"),
        "HUAWEI HiSuite and eRecovery guidance",
        KNOWLEDGE_SOURCES["huawei_recovery"].url,
        "Check whether the exact device supports restoration and disclose possible data erasure; the service chooses the available version.",
    ),
    _CatalogEntry(
        "honor.system-update",
        ("honor", "magicos"),
        "HONOR MagicOS update troubleshooting",
        KNOWLEDGE_SOURCES["honor_update"].url,
        "Distinguish network, SIM, updater-state, staged-rollout, and rooted-phone cases before proposing a retry or support escalation.",
    ),
    _CatalogEntry(
        "hmd.update-delivery",
        ("hmd", "nokia"),
        "HMD and Nokia update delivery guidance",
        KNOWLEDGE_SOURCES["hmd_update"].url,
        "Treat model, operator, market, and rollout as separate availability evidence; another phone's newer build is not a compatible package.",
    ),
    _CatalogEntry(
        "fairphone.update-troubleshooting",
        ("fairphone",),
        "Fairphone update-problem troubleshooting",
        KNOWLEDGE_SOURCES["fairphone_update"].url,
        "Select the matching evidence branch for rollout, space, download, install, freeze, optimization, or restart-preparation failures.",
    ),
    _CatalogEntry(
        "tecno.update-scope",
        ("tecno",),
        "TECNO update coverage",
        KNOWLEDGE_SOURCES["tecno_updates"].url,
        "Match exact TECNO model, country, dated coverage, current build, and security patch; do not transfer this evidence to Infinix or itel.",
    ),
    _CatalogEntry(
        "infinix.update-support",
        ("infinix", "xos"),
        "Infinix support and System Update",
        KNOWLEDGE_SOURCES["infinix_support"].url,
        "Use exact-model Infinix support and published update commitments; a family name or another model's promise is not compatibility evidence.",
    ),
    _CatalogEntry(
        "itel.ota-support",
        ("itel",),
        "itel OTA and firmware troubleshooting",
        KNOWLEDGE_SOURCES["itel_support"].url,
        "Separate normal OTA, storage/network readiness, boot crash, and no-power cases; forced updating may lose data.",
    ),
    _CatalogEntry(
        "zte.system-update",
        ("zte", "zteos"),
        "ZTE system update guidance",
        KNOWLEDGE_SOURCES["zte_update"].url,
        "Prefer an official online offer and require the exact product/region package for any documented offline update route.",
    ),
    _CatalogEntry(
        "nubia.myos-update",
        ("nubia", "redmagic", "myos", "redmagic os"),
        "nubia MyOS update and issue guidance",
        KNOWLEDGE_SOURCES["nubia_updates"].url,
        "Bind changelogs and bug reports to the exact model, country, installed version, and offered build; do not borrow a ZTE package.",
    ),
)


class OfficialCatalogProvider:
    def search(self, fingerprint: ErrorFingerprint) -> Sequence[OnlineFixCandidate]:
        haystack = (
            f"{fingerprint.category} {fingerprint.manufacturer} {fingerprint.query}"
        ).casefold()
        matches = []
        for entry in _OFFICIAL_CATALOG:
            tokens = tuple(pattern for pattern in entry.patterns if pattern in haystack)
            if not tokens:
                continue
            matches.append(
                OnlineFixCandidate(
                    entry.source_id,
                    SourceAuthority.OFFICIAL,
                    entry.title,
                    entry.url,
                    entry.summary,
                    tokens,
                    entry.source_id,
                    entry.local_action_id,
                    min(95, 72 + 5 * len(tokens)),
                )
            )
        return tuple(matches)


class RedditSearchProvider:
    """Read public Reddit search metadata; returned text never gains execution authority."""

    def __init__(
        self,
        loader: Callable[[str, Mapping[str, str], int], bytes] | None = None,
    ) -> None:
        self.loader = loader or _load_url

    def search(self, fingerprint: ErrorFingerprint) -> Sequence[OnlineFixCandidate]:
        query = urllib.parse.urlencode(
            {"q": fingerprint.query, "sort": "relevance", "t": "all", "limit": "8"}
        )
        url = f"https://www.reddit.com/search.json?{query}"
        try:
            payload = json.loads(
                self.loader(
                    url,
                    {"User-Agent": "ROMVERSE/0.1 verified-remediation-research"},
                    2_000_000,
                )
            )
        except (OSError, ValueError, TypeError, urllib.error.URLError):
            return ()
        children = payload.get("data", {}).get("children", []) if isinstance(payload, dict) else []
        candidates = []
        for child in children[:8]:
            data = child.get("data", {}) if isinstance(child, dict) else {}
            title = _bounded_text(data.get("title", ""), 180)
            body = _bounded_text(data.get("selftext", ""), 500)
            permalink = str(data.get("permalink", ""))
            if not title or not permalink.startswith("/"):
                continue
            exact = _exact_identity_tokens(fingerprint, f"{title} {body}")
            published_at = _unix_timestamp(data.get("created_utc"))
            if (
                fingerprint.model
                and fingerprint.model.casefold() not in f"{title} {body}".casefold()
                and not exact
            ):
                continue
            candidates.append(
                OnlineFixCandidate(
                    f"reddit.{data.get('id', uuid4().hex[:10])}",
                    SourceAuthority.COMMUNITY,
                    title,
                    f"https://www.reddit.com{permalink}",
                    body
                    or "Community report discovered for review; open the source to inspect context and outcomes.",
                    exact,
                    _corroboration_key(title),
                    confidence=min(68, 32 + 7 * len(exact)),
                    confirmed_working=False,
                    published_at=published_at,
                )
            )
        return tuple(candidates)


class StackExchangeSearchProvider:
    """Search accepted Android Enthusiasts questions as scoped community evidence."""

    def __init__(
        self,
        loader: Callable[[str, Mapping[str, str], int], bytes] | None = None,
    ) -> None:
        self.loader = loader or _load_url

    def search(self, fingerprint: ErrorFingerprint) -> Sequence[OnlineFixCandidate]:
        query = urllib.parse.urlencode(
            {
                "site": "android",
                "order": "desc",
                "sort": "relevance",
                "accepted": "true",
                "pagesize": "8",
                "filter": "withbody",
                "q": fingerprint.query,
            }
        )
        url = f"https://api.stackexchange.com/2.3/search/advanced?{query}"
        try:
            payload = json.loads(
                self.loader(
                    url,
                    {"User-Agent": "ROMVERSE/0.1 verified-remediation-research"},
                    2_000_000,
                )
            )
        except (OSError, ValueError, TypeError, urllib.error.URLError):
            return ()
        items = payload.get("items", ()) if isinstance(payload, dict) else ()
        candidates = []
        for item in items[:8] if isinstance(items, Sequence) else ():
            if not isinstance(item, Mapping) or not item.get("accepted_answer_id"):
                continue
            title = _bounded_text(html.unescape(str(item.get("title", ""))), 180)
            body = _bounded_text(_strip_html(str(item.get("body", ""))), 500)
            link = str(item.get("link", ""))
            if (
                not title
                or not _safe_public_https_url(link)
                or (urllib.parse.urlsplit(link).hostname or "").casefold()
                != "android.stackexchange.com"
            ):
                continue
            exact = _exact_identity_tokens(fingerprint, f"{title} {body}")
            if fingerprint.model and not exact:
                continue
            candidates.append(
                OnlineFixCandidate(
                    f"stackexchange.{item.get('question_id', uuid4().hex[:10])}",
                    SourceAuthority.COMMUNITY,
                    title,
                    link,
                    body or "Accepted-answer community thread found for scoped review.",
                    exact,
                    _corroboration_key(title),
                    confidence=min(74, 44 + 7 * len(exact)),
                    confirmed_working=False,
                    published_at=_unix_timestamp(item.get("last_activity_date")),
                )
            )
        return tuple(candidates)


class GoogleProgrammableSearchProvider:
    """Google discovery provider enabled only when the user configures API credentials."""

    def __init__(
        self,
        api_key: str,
        engine_id: str,
        loader: Callable[[str, Mapping[str, str], int], bytes] | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.engine_id = engine_id.strip()
        self.loader = loader or _load_url

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.engine_id)

    def search(self, fingerprint: ErrorFingerprint) -> Sequence[OnlineFixCandidate]:
        if not self.configured:
            return ()
        query = urllib.parse.urlencode(
            {"key": self.api_key, "cx": self.engine_id, "q": fingerprint.query, "num": "8"}
        )
        try:
            payload = json.loads(
                self.loader(
                    f"https://www.googleapis.com/customsearch/v1?{query}",
                    {"User-Agent": "ROMVERSE/0.1 verified-remediation-research"},
                    2_000_000,
                )
            )
        except (OSError, ValueError, TypeError, urllib.error.URLError):
            return ()
        candidates = []
        for item in payload.get("items", [])[:8] if isinstance(payload, dict) else ():
            title = _bounded_text(item.get("title", ""), 180)
            url = str(item.get("link", ""))
            summary = _bounded_text(item.get("snippet", ""), 500)
            if not title or not _safe_public_https_url(url):
                continue
            exact = _exact_identity_tokens(fingerprint, f"{title} {summary}")
            authority = _authority_for_host(urllib.parse.urlsplit(url).hostname or "")
            published_at = _google_result_timestamp(item)
            candidates.append(
                OnlineFixCandidate(
                    f"google.{hashlib.sha256(url.encode()).hexdigest()[:16]}",
                    authority,
                    title,
                    url,
                    summary or "Google result discovered for source review.",
                    exact,
                    _corroboration_key(title),
                    confidence=min(
                        82 if authority is SourceAuthority.OFFICIAL else 60, 28 + 8 * len(exact)
                    ),
                    confirmed_working=False,
                    published_at=published_at,
                )
            )
        return tuple(candidates)


class OnlineRemediationService:
    """Find and cache source-attributed guidance without executing remote instructions."""

    MAX_RECEIPT_BYTES = 256 * 1024
    MAX_OUTCOME_BYTES = 32 * 1024
    MAX_OUTCOME_FILES = 64

    def __init__(
        self,
        workspace: Path,
        providers: Iterable[OnlineFixProvider] = (),
        action_evidence_verifier: LocalActionEvidenceVerifier | None = None,
    ) -> None:
        self.workspace = workspace.resolve()
        self.cache_root = self.workspace / "knowledge" / "online-remediation"
        self.providers = tuple(providers) or (OfficialCatalogProvider(),)
        self.outcomes_root = self.cache_root / "verified-outcomes"
        self.action_evidence_verifier = action_evidence_verifier or (
            WorkspaceLocalActionEvidenceVerifier(self.workspace)
        )

    @classmethod
    def connected(
        cls,
        workspace: Path,
        *,
        include_community: bool = True,
    ) -> OnlineRemediationService:
        providers: list[OnlineFixProvider] = [OfficialCatalogProvider()]
        if include_community:
            providers.append(RedditSearchProvider())
            providers.append(StackExchangeSearchProvider())
            google = GoogleProgrammableSearchProvider(
                os.environ.get("ROMVERSE_GOOGLE_SEARCH_API_KEY", ""),
                os.environ.get("ROMVERSE_GOOGLE_SEARCH_ENGINE_ID", ""),
            )
            if google.configured:
                providers.append(google)
        return cls(workspace, providers)

    def lookup(self, fingerprint: ErrorFingerprint) -> OnlineFixReceipt:
        candidates: list[OnlineFixCandidate] = []
        for provider in self.providers:
            try:
                candidates.extend(provider.search(fingerprint))
            except (OSError, ValueError, TypeError, urllib.error.URLError):
                continue
        created_at = datetime.now(UTC).isoformat()
        vetted = self._apply_verified_outcomes(
            fingerprint,
            _vet_candidates(fingerprint, candidates, retrieved_at=created_at),
        )
        diagnosis = (
            f"Found {len(vetted)} source-attributed candidate(s). Official guidance and exact-device corroboration rank first; remote text has no execution authority."
            if vetted
            else "No sufficiently relevant online fix was found. ROMVERSE preserved the exact fingerprint for a later retry and did not guess."
        )
        path = self.cache_root / f"{fingerprint.fingerprint_id}.romverse"
        payload = {
            "schema_version": 2,
            "receipt_id": uuid4().hex,
            "created_at": created_at,
            "fingerprint": asdict(fingerprint),
            "candidates": [asdict(candidate) for candidate in vetted],
            "diagnosis": diagnosis,
            "cache_path": str(path),
            "execution_authority": "guidance-only",
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        receipt = OnlineFixReceipt(
            2,
            str(payload["receipt_id"]),
            created_at,
            fingerprint,
            vetted,
            diagnosis,
            str(path),
            digest,
        )
        atomic_write_json(
            path,
            {"format": "romverse.online-remediation", **asdict(receipt)},
            boundary=self.workspace,
            maximum_bytes=self.MAX_RECEIPT_BYTES,
        )
        return receipt

    def synthesize(self, receipt: OnlineFixReceipt) -> RemediationDecision:
        """Revalidate persisted evidence and derive its current no-authority decision."""

        if not isinstance(receipt, OnlineFixReceipt):
            raise TypeError("Online remediation decision needs a validated receipt")
        persisted = self.load(receipt.fingerprint)
        if persisted is None or persisted.receipt_digest != receipt.receipt_digest:
            raise ValueError("Online remediation decision receipt is stale or invalid")
        verified = frozenset(
            (outcome.source_id, outcome.source_url, outcome.local_action_id)
            for outcome in self._load_verified_outcomes(receipt.fingerprint)
        )
        return synthesize_remediation(receipt, verified_candidate_keys=verified)

    def load(self, fingerprint: ErrorFingerprint) -> OnlineFixReceipt | None:
        path = self.cache_root / f"{fingerprint.fingerprint_id}.romverse"
        try:
            payload = read_json_object(
                path,
                boundary=self.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
            receipt = _receipt_from_payload(payload, path=path, fingerprint=fingerprint)
            verified = {
                (outcome.source_id, outcome.source_url, outcome.local_action_id)
                for outcome in self._load_verified_outcomes(fingerprint)
            }
            if any(
                candidate.confirmed_working
                and (candidate.source_id, candidate.url, candidate.local_action_id) not in verified
                for candidate in receipt.candidates
            ):
                return None
            return receipt
        except (OSError, ValueError, TypeError, KeyError):
            return None

    def record_verified_outcome(
        self,
        fingerprint: ErrorFingerprint,
        candidate: OnlineFixCandidate,
        action_evidence: TypedLocalActionEvidence,
        verification_summary: str,
        *,
        phone_changed: bool = False,
    ) -> VerifiedFixOutcome:
        """Promote only a successful built-in typed action, never remote instructions."""

        if (
            not candidate.local_action_id
            or candidate.authority not in {SourceAuthority.OFFICIAL, SourceAuthority.MAINTAINER}
            or candidate.local_action_id not in _TYPED_LOCAL_ACTIONS
            or not _safe_public_https_url(candidate.url)
            or not _source_identifier(candidate.source_id)
        ):
            raise ValueError("Online candidate has no trusted typed local repair action")
        research_receipt = self.load(fingerprint)
        candidate_key = (
            candidate.source_id,
            candidate.url,
            candidate.local_action_id,
            candidate.authority,
        )
        if research_receipt is None or not any(
            (
                item.source_id,
                item.url,
                item.local_action_id,
                item.authority,
            )
            == candidate_key
            for item in research_receipt.candidates
        ):
            raise ValueError("Online candidate is not bound to this persisted error fingerprint")
        if (
            not isinstance(action_evidence, TypedLocalActionEvidence)
            or action_evidence.local_action_id != candidate.local_action_id
            or not self.action_evidence_verifier.verify(action_evidence)
        ):
            raise ValueError("Typed local action evidence is absent, invalid, or mismatched")
        receipt_digest = action_evidence.receipt_digest
        summary = _bounded_text(verification_summary, 500)
        if not summary:
            raise ValueError("Typed repair verification summary is required")
        if phone_changed:
            raise ValueError("Online remediation learning accepts host/read-only outcomes only")
        payload = {
            "schema_version": 2,
            "outcome_id": uuid4().hex,
            "created_at": datetime.now(UTC).isoformat(),
            "fingerprint_id": fingerprint.fingerprint_id,
            "source_id": candidate.source_id,
            "source_url": candidate.url,
            "local_action_id": candidate.local_action_id,
            "action_receipt_digest": receipt_digest,
            "verification_summary": summary,
            "success": True,
            "phone_changed": False,
            "action_evidence_ref": action_evidence.evidence_ref,
            "action_evidence_format": action_evidence.evidence_format,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        outcome = VerifiedFixOutcome(**payload, outcome_digest=digest)
        root = self.outcomes_root / fingerprint.fingerprint_id
        outcome_key = hashlib.sha256(
            f"{candidate.source_id}\0{candidate.url}\0{candidate.local_action_id}".encode()
        ).hexdigest()
        path = root / f"{outcome_key}.romverse"
        atomic_write_json(
            path,
            {"format": "romverse.verified-fix-outcome", **asdict(outcome)},
            boundary=self.workspace,
            maximum_bytes=self.MAX_OUTCOME_BYTES,
        )
        return outcome

    def _load_verified_outcomes(
        self,
        fingerprint: ErrorFingerprint,
    ) -> tuple[VerifiedFixOutcome, ...]:
        root = self.outcomes_root / fingerprint.fingerprint_id
        outcomes = []
        try:
            paths = bounded_regular_files(
                root,
                ".romverse",
                boundary=self.workspace,
                maximum_entries=self.MAX_OUTCOME_FILES,
            )
        except (FileNotFoundError, LocalStoreError):
            return ()
        for path in paths:
            try:
                payload = read_json_object(
                    path,
                    boundary=self.workspace,
                    maximum_bytes=self.MAX_OUTCOME_BYTES,
                )
                expected_keys = {field.name for field in fields(VerifiedFixOutcome)} | {"format"}
                if (
                    set(payload) != expected_keys
                    or payload.pop("format") != "romverse.verified-fix-outcome"
                ):
                    continue
                outcome = VerifiedFixOutcome(**payload)
                unsigned = asdict(outcome)
                expected = str(unsigned.pop("outcome_digest", ""))
                actual = hashlib.sha256(
                    json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
                if (
                    outcome.schema_version != 2
                    or outcome.fingerprint_id != fingerprint.fingerprint_id
                    or not outcome.success
                    or outcome.phone_changed
                    or outcome.local_action_id not in _TYPED_LOCAL_ACTIONS
                    or not _hex_identifier(outcome.outcome_id, 32)
                    or not _aware_timestamp_at_or_before_now(outcome.created_at)
                    or not _source_identifier(outcome.source_id)
                    or not _safe_public_https_url(outcome.source_url)
                    or not _sha256_value(outcome.action_receipt_digest)
                    or not self.action_evidence_verifier.verify(
                        TypedLocalActionEvidence(
                            outcome.local_action_id,
                            outcome.action_receipt_digest,
                            outcome.action_evidence_ref,
                            outcome.action_evidence_format,
                        )
                    )
                    or not _bounded_identity(outcome.verification_summary, 500)
                    or not _sha256_value(expected)
                    or expected != actual
                ):
                    continue
                outcomes.append(outcome)
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                continue
        return tuple(outcomes)

    def _apply_verified_outcomes(
        self,
        fingerprint: ErrorFingerprint,
        candidates: tuple[OnlineFixCandidate, ...],
    ) -> tuple[OnlineFixCandidate, ...]:
        verified = {
            (outcome.source_id, outcome.source_url, outcome.local_action_id)
            for outcome in self._load_verified_outcomes(fingerprint)
        }
        enriched = tuple(
            OnlineFixCandidate(
                candidate.source_id,
                candidate.authority,
                candidate.title,
                candidate.url,
                candidate.summary,
                candidate.exact_tokens,
                candidate.corroboration_key,
                candidate.local_action_id,
                candidate.confidence,
                (
                    candidate.source_id,
                    candidate.url,
                    candidate.local_action_id,
                )
                in verified,
                candidate.retrieved_at,
                candidate.published_at,
                candidate.freshness,
                candidate.corroboration_count,
                candidate.corroborating_authorities,
                candidate.scope_match,
                _confidence_reason(
                    candidate.authority,
                    candidate.exact_tokens,
                    candidate.freshness,
                    candidate.corroboration_count,
                    confirmed_working=(
                        (
                            candidate.source_id,
                            candidate.url,
                            candidate.local_action_id,
                        )
                        in verified
                    ),
                ),
            )
            for candidate in candidates
        )
        return tuple(
            sorted(
                enriched,
                key=lambda item: (
                    not item.confirmed_working,
                    -item.confidence,
                    item.authority.value,
                    item.title.casefold(),
                ),
            )
        )


_TYPED_LOCAL_ACTIONS = frozenset(
    {
        "refresh-adb-evidence",
        "verify-platform-tools",
        "inspect-payload-source",
        "inspect-avb-topology",
        "classify-ota-source",
    }
)


def _vet_candidates(
    fingerprint: ErrorFingerprint,
    candidates: Iterable[OnlineFixCandidate],
    *,
    retrieved_at: str | None = None,
) -> tuple[OnlineFixCandidate, ...]:
    observed_at = retrieved_at or datetime.now(UTC).isoformat()
    unique: dict[str, OnlineFixCandidate] = {}
    for candidate in candidates:
        if (
            not isinstance(candidate, OnlineFixCandidate)
            or not isinstance(candidate.authority, SourceAuthority)
            or not _source_identifier(candidate.source_id)
            or not _bounded_identity(candidate.title, 180)
            or not _safe_public_https_url(candidate.url)
            or not _bounded_identity(candidate.summary, 500)
            or type(candidate.confidence) is not int
            or not 0 <= candidate.confidence <= 100
            or candidate.local_action_id not in {"", *_TYPED_LOCAL_ACTIONS}
            or not _bounded_identity(candidate.corroboration_key, 180, allow_empty=True)
        ):
            continue
        if candidate.confidence < 30 and candidate.authority not in {
            SourceAuthority.OFFICIAL,
            SourceAuthority.MAINTAINER,
        }:
            continue
        current = unique.get(candidate.url)
        if current is None or candidate.confidence > current.confidence:
            unique[candidate.url] = candidate
    corroboration: dict[str, list[OnlineFixCandidate]] = {}
    for candidate in unique.values():
        if candidate.corroboration_key:
            corroboration.setdefault(candidate.corroboration_key, []).append(candidate)
    output = []
    for candidate in unique.values():
        related = corroboration.get(candidate.corroboration_key, ())
        authorities = tuple(
            sorted({item.authority for item in related}, key=lambda item: item.value)
        )
        corroboration_count = max(1, len({item.url for item in related}))
        exact_tokens = _exact_identity_tokens(
            fingerprint,
            f"{candidate.title} {candidate.summary}",
        )
        published_at = _normalised_timestamp(candidate.published_at)
        freshness = _freshness_for(published_at, observed_at)
        confidence = _evidence_confidence(
            candidate.confidence,
            candidate.authority,
            freshness,
            corroboration_count,
        )
        output.append(
            OnlineFixCandidate(
                candidate.source_id,
                candidate.authority,
                candidate.title,
                candidate.url,
                candidate.summary,
                exact_tokens,
                candidate.corroboration_key,
                candidate.local_action_id,
                confidence,
                False,
                observed_at,
                published_at,
                freshness,
                corroboration_count,
                authorities,
                _scope_match_summary(fingerprint, exact_tokens),
                _confidence_reason(
                    candidate.authority,
                    exact_tokens,
                    freshness,
                    corroboration_count,
                    confirmed_working=False,
                ),
            )
        )
    return tuple(
        sorted(
            output,
            key=lambda item: (
                not item.confirmed_working,
                -item.confidence,
                item.authority.value,
                item.title.casefold(),
            ),
        )[:12]
    )


def _load_url(url: str, headers: Mapping[str, str], maximum: int) -> bytes:
    if not _safe_public_https_url(url):
        raise ValueError("Online remediation URL is not a safe public HTTPS endpoint")
    request = urllib.request.Request(url, headers=dict(headers))
    with urllib.request.urlopen(request, timeout=8) as response:  # noqa: S310 - URL validated above
        content_type = response.headers.get_content_type()
        if content_type not in {"application/json", "text/json"}:
            raise ValueError("Online remediation endpoint did not return JSON")
        data = response.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError("Online remediation response exceeded its safety limit")
    return data


def _normalize_error(message: str) -> str:
    value = str(message)
    value = re.sub(r"/home/[^\s]+", "<path>", value)
    value = re.sub(r"/Users/[^\s]+", "<path>", value, flags=re.IGNORECASE)
    value = re.sub(r"[A-Z]:\\Users\\[^\s]+", "<path>", value, flags=re.IGNORECASE)
    value = re.sub(
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        "<email>",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"\b(?:api[_ -]?key|token|password|secret)\s*[:=]\s*\S+",
        "<credential>",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "<ip>", value)
    value = re.sub(
        r"\b(?:serial|device[_ -]?id)\s*[:=]\s*[A-Za-z0-9._:-]{4,}\b",
        "<identifier>",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(r"\b[0-9a-f]{32,}\b", "<digest>", value, flags=re.IGNORECASE)
    value = re.sub(r"\b[A-Z0-9]{12,}\b", "<identifier>", value)
    return re.sub(r"\s+", " ", value).strip()


def _bounded_text(value: object, maximum: int) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()[:maximum]


def _strip_html(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]{0,500}>", " ", value))


def _receipt_from_payload(
    payload: Mapping[str, object],
    *,
    path: Path,
    fingerprint: ErrorFingerprint,
) -> OnlineFixReceipt:
    expected_keys = {
        "format",
        "schema_version",
        "receipt_id",
        "created_at",
        "fingerprint",
        "candidates",
        "diagnosis",
        "cache_path",
        "receipt_digest",
        "execution_authority",
    }
    if set(payload) != expected_keys or payload.get("format") != "romverse.online-remediation":
        raise ValueError("online remediation receipt schema is invalid")
    schema_version = payload.get("schema_version")
    if type(schema_version) is not int or schema_version not in {1, 2}:
        raise ValueError("online remediation receipt version is invalid")
    if not _hex_identifier(payload.get("receipt_id"), 32):
        raise ValueError("online remediation receipt identity is invalid")
    if not _aware_timestamp_at_or_before_now(payload.get("created_at")):
        raise ValueError("online remediation receipt timestamp is invalid")
    if payload.get("execution_authority") != "guidance-only":
        raise ValueError("online remediation receipt authority is invalid")
    if payload.get("cache_path") != str(path):
        raise ValueError("online remediation cache binding is invalid")
    if not _bounded_identity(payload.get("diagnosis"), 1_000):
        raise ValueError("online remediation diagnosis is invalid")
    if not _sha256_value(payload.get("receipt_digest")):
        raise ValueError("online remediation receipt digest is invalid")

    raw_fingerprint = payload.get("fingerprint")
    fingerprint_fields = {field.name for field in fields(ErrorFingerprint)}
    if not isinstance(raw_fingerprint, Mapping) or set(raw_fingerprint) != fingerprint_fields:
        raise ValueError("online remediation fingerprint schema is invalid")
    if any(not isinstance(value, str) for value in raw_fingerprint.values()):
        raise ValueError("online remediation fingerprint fields are invalid")
    stored = ErrorFingerprint(**raw_fingerprint)
    expected_fingerprint = ErrorFingerprint.create(
        stored.normalized_error,
        category=stored.category,
        manufacturer=stored.manufacturer,
        model=stored.model,
        marketing_name=stored.marketing_name,
        codename=stored.codename,
        build_id=stored.build_id,
        source_kind=stored.source_kind,
        tool_name=stored.tool_name,
        tool_version=stored.tool_version,
    )
    if stored != fingerprint or stored != expected_fingerprint:
        raise ValueError("online remediation fingerprint binding is invalid")

    raw_candidates = payload.get("candidates")
    if not isinstance(raw_candidates, list) or len(raw_candidates) > 12:
        raise ValueError("online remediation candidate collection is invalid")
    all_candidate_fields = {field.name for field in fields(OnlineFixCandidate)}
    legacy_missing = {
        "retrieved_at",
        "published_at",
        "freshness",
        "corroboration_count",
        "corroborating_authorities",
        "scope_match",
        "confidence_reason",
    }
    expected_candidate_fields = (
        all_candidate_fields - legacy_missing if schema_version == 1 else all_candidate_fields
    )
    candidates = []
    for raw_candidate in raw_candidates:
        if (
            not isinstance(raw_candidate, Mapping)
            or set(raw_candidate) != expected_candidate_fields
        ):
            raise ValueError("online remediation candidate schema is invalid")
        candidate = _candidate_from_payload(raw_candidate)
        _validate_stored_candidate(candidate, schema_version=schema_version)
        candidates.append(candidate)

    unsigned = {
        key: payload[key]
        for key in (
            "schema_version",
            "receipt_id",
            "created_at",
            "fingerprint",
            "candidates",
            "diagnosis",
            "cache_path",
            "execution_authority",
        )
    }
    actual_digest = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    receipt_digest = str(payload["receipt_digest"])
    if actual_digest != receipt_digest:
        raise ValueError("online remediation receipt integrity is invalid")
    return OnlineFixReceipt(
        schema_version,
        str(payload["receipt_id"]),
        str(payload["created_at"]),
        stored,
        tuple(candidates),
        str(payload["diagnosis"]),
        str(payload["cache_path"]),
        receipt_digest,
        "guidance-only",
    )


def _validate_stored_candidate(candidate: OnlineFixCandidate, *, schema_version: int) -> None:
    if (
        not _source_identifier(candidate.source_id)
        or not _bounded_identity(candidate.title, 180)
        or not _safe_public_https_url(candidate.url)
        or not _bounded_identity(candidate.summary, 500)
        or type(candidate.confidence) is not int
        or not 0 <= candidate.confidence <= 100
        or type(candidate.confirmed_working) is not bool
        or candidate.local_action_id not in {"", *_TYPED_LOCAL_ACTIONS}
        or len(candidate.exact_tokens) > 8
        or any(not _bounded_identity(value, 160) for value in candidate.exact_tokens)
        or not _bounded_identity(candidate.corroboration_key, 180, allow_empty=True)
    ):
        raise ValueError("online remediation candidate values are invalid")
    if schema_version == 1:
        return
    if (
        not _aware_timestamp_at_or_before_now(candidate.retrieved_at)
        or (
            candidate.published_at
            and not _aware_timestamp_at_or_before_now(candidate.published_at, future_days=None)
        )
        or type(candidate.corroboration_count) is not int
        or not 1 <= candidate.corroboration_count <= 12
        or len(candidate.corroborating_authorities) > len(SourceAuthority)
        or not _bounded_identity(candidate.scope_match, 180)
        or not _bounded_identity(candidate.confidence_reason, 500)
    ):
        raise ValueError("online remediation candidate evidence is invalid")


def _bounded_identity(value: object, maximum: int, *, allow_empty: bool = False) -> bool:
    if not isinstance(value, str) or len(value) > maximum:
        return False
    cleaned = _bounded_text(value, maximum)
    return cleaned == value and (allow_empty or bool(cleaned))


def _hex_identifier(value: object, length: int) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(rf"[0-9a-f]{{{length}}}", value))


def _sha256_value(value: object) -> bool:
    return _hex_identifier(value, 64)


def _source_identifier(value: object) -> bool:
    return isinstance(value, str) and bool(
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}", value)
    )


def _aware_timestamp_at_or_before_now(value: object, *, future_days: int | None = 0) -> bool:
    if not isinstance(value, str) or len(value) > 80:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        return False
    return future_days is None or parsed <= datetime.now(UTC) + timedelta(
        days=future_days,
        minutes=5,
    )


def _candidate_from_payload(item: Mapping[str, object]) -> OnlineFixCandidate:
    values = dict(item)
    values["authority"] = SourceAuthority(values["authority"])
    values["exact_tokens"] = tuple(values.get("exact_tokens", ()))
    values["freshness"] = EvidenceFreshness(values.get("freshness", EvidenceFreshness.UNCONFIRMED))
    values["corroborating_authorities"] = tuple(
        SourceAuthority(value) for value in values.get("corroborating_authorities", ())
    )
    return OnlineFixCandidate(**values)


def _normalised_timestamp(value: object) -> str:
    text = _bounded_text(value, 80)
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if parsed.tzinfo is None:
        return ""
    return parsed.astimezone(UTC).isoformat()


def _unix_timestamp(value: object) -> str:
    try:
        parsed = datetime.fromtimestamp(float(value), UTC)
    except (OverflowError, TypeError, ValueError):
        return ""
    return parsed.isoformat()


def _google_result_timestamp(item: object) -> str:
    if not isinstance(item, Mapping):
        return ""
    pagemap = item.get("pagemap", {})
    if not isinstance(pagemap, Mapping):
        return ""
    metatags = pagemap.get("metatags", ())
    if not isinstance(metatags, Sequence) or not metatags:
        return ""
    metadata = metatags[0]
    if not isinstance(metadata, Mapping):
        return ""
    for key in (
        "article:modified_time",
        "article:published_time",
        "og:updated_time",
        "date",
    ):
        timestamp = _normalised_timestamp(metadata.get(key, ""))
        if timestamp:
            return timestamp
    return ""


def _freshness_for(published_at: str, retrieved_at: str) -> EvidenceFreshness:
    try:
        published = datetime.fromisoformat(published_at)
        retrieved = datetime.fromisoformat(retrieved_at)
    except ValueError:
        return EvidenceFreshness.UNCONFIRMED
    if published.tzinfo is None or retrieved.tzinfo is None:
        return EvidenceFreshness.UNCONFIRMED
    age = retrieved - published
    if age < -timedelta(days=1):
        return EvidenceFreshness.UNCONFIRMED
    if age <= timedelta(days=180):
        return EvidenceFreshness.CURRENT
    if age <= timedelta(days=730):
        return EvidenceFreshness.AGED
    return EvidenceFreshness.STALE


def _evidence_confidence(
    claimed: int,
    authority: SourceAuthority,
    freshness: EvidenceFreshness,
    corroboration_count: int,
) -> int:
    confidence = max(0, min(100, int(claimed)))
    if freshness is EvidenceFreshness.STALE:
        confidence -= (
            15 if authority in {SourceAuthority.COMMUNITY, SourceAuthority.DISCOVERY} else 5
        )
    elif freshness is EvidenceFreshness.AGED:
        confidence -= (
            5 if authority in {SourceAuthority.COMMUNITY, SourceAuthority.DISCOVERY} else 2
        )
    if corroboration_count > 1:
        confidence += min(10, 4 * (corroboration_count - 1))
    return max(0, min(100, confidence))


def _scope_match_summary(
    fingerprint: ErrorFingerprint,
    exact_tokens: tuple[str, ...],
) -> str:
    matches = []
    if fingerprint.build_id and fingerprint.build_id in exact_tokens:
        matches.append("exact build")
    if any(
        value and value in exact_tokens
        for value in (fingerprint.marketing_name, fingerprint.model, fingerprint.codename)
    ):
        matches.append("exact device")
    if fingerprint.tool_version and fingerprint.tool_version in exact_tokens:
        matches.append("exact tool version")
    if matches:
        return ", ".join(matches)
    return "error/category only; device and build remain unconfirmed"


def _confidence_reason(
    authority: SourceAuthority,
    exact_tokens: tuple[str, ...],
    freshness: EvidenceFreshness,
    corroboration_count: int,
    *,
    confirmed_working: bool,
) -> str:
    parts = [f"{authority.value} source"]
    parts.append("exact identity evidence" if exact_tokens else "no exact identity evidence")
    parts.append(f"freshness {freshness.value}")
    parts.append(
        f"{corroboration_count} independent source(s)"
        if corroboration_count > 1
        else "not independently corroborated"
    )
    if confirmed_working:
        parts.append("matching typed repair verified locally")
    return "; ".join(parts)


def _token(value: object, maximum: int) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", str(value).casefold()).strip("-")[:maximum]


def _safe_public_https_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(url)
    except (TypeError, ValueError):
        return False
    host = (parsed.hostname or "").casefold().rstrip(".")
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        return False
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not address.is_global:
            return False
    return True


def _exact_identity_tokens(fingerprint: ErrorFingerprint, text: str) -> tuple[str, ...]:
    haystack = text.casefold()
    values = (
        fingerprint.model,
        fingerprint.marketing_name,
        fingerprint.codename,
        fingerprint.build_id,
        fingerprint.tool_version,
    )
    return tuple(value for value in values if len(value) >= 3 and value.casefold() in haystack)


def _corroboration_key(title: str) -> str:
    words = re.findall(r"[a-z0-9]{4,}", title.casefold())
    return "-".join(sorted(set(words))[:8])


def _authority_for_host(host: str) -> SourceAuthority:
    host = host.casefold().rstrip(".")
    if _host_matches(
        host,
        (
            "developer.android.com",
            "source.android.com",
            "support.google.com",
            "developers.google.com",
            "android.googlesource.com",
            "samsung.com",
            "samsungknox.com",
            "mi.com",
            "xiaomi.com",
            "motorola.com",
            "sony.com",
            "oneplus.com",
            "oppo.com",
            "realme.com",
            "vivo.com",
            "huawei.com",
            "honor.com",
            "asus.com",
            "hmd.com",
            "nokia.com",
            "fairphone.com",
            "nothing.tech",
            "ztedevices.com",
            "nubia.com",
            "infinixmobility.com",
            "itel-life.com",
        ),
    ):
        return SourceAuthority.OFFICIAL
    if _host_matches(host, ("github.com", "gitlab.com")):
        return SourceAuthority.MAINTAINER
    if _host_matches(
        host,
        (
            "reddit.com",
            "xda-developers.com",
            "xdaforums.com",
            "stackexchange.com",
            "stackoverflow.com",
        ),
    ):
        return SourceAuthority.COMMUNITY
    return SourceAuthority.DISCOVERY


def _host_matches(host: str, domains: tuple[str, ...]) -> bool:
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)
