from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import socket
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, fields, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit
from uuid import uuid4

from romverse.device.models import AndroidDevice
from romverse.device_packs.registry import DevicePackRegistry
from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    ensure_private_directory,
    read_json_object,
)


class IdentityAuthority(StrEnum):
    ON_DEVICE = "on-device"
    DEVICE_PACK = "device-pack"
    OEM_OFFICIAL = "oem-official"
    GOOGLE_PLAY_CATALOG = "google-play-catalog"
    CORROBORATED_PUBLIC = "corroborated-public"
    DISCOVERY = "discovery"


class CanonicalIdentityError(ValueError):
    """A canonical identity could not be established without guessing."""


@dataclass(frozen=True, slots=True)
class CanonicalDeviceIdentity:
    """Immutable evidence-backed identity, separate from retail naming.

    Marketing names, aliases and family relationships are retained for discovery but are
    deliberately excluded from ``device_id``.  They can never make two devices exact matches.
    """

    schema_version: int
    device_id: str
    manufacturer: str
    brand: str
    model: str
    codename: str
    region: str
    oem_identifiers: tuple[tuple[str, str], ...]
    soc: str
    platform: str
    marketing_names: tuple[str, ...]
    aliases: tuple[str, ...]
    family_ids: tuple[str, ...]
    evidence_claim_ids: tuple[str, ...]
    compatibility_status: str = "UNCONFIRMED"
    execution_authority: str = "none"
    phone_action_allowed: bool = False
    guardian_approval: bool = False
    bootloader_relock_allowed: bool = False

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise CanonicalIdentityError("Canonical device identity schema is unsupported")
        if (
            self.compatibility_status != "UNCONFIRMED"
            or self.execution_authority != "none"
            or self.phone_action_allowed
            or self.guardian_approval
            or self.bootloader_relock_allowed
        ):
            raise CanonicalIdentityError(
                "Canonical identity cannot promote compatibility or execution authority"
            )

    def exactly_matches(self, other: CanonicalDeviceIdentity) -> bool:
        return self.device_id == other.device_id


_CANONICAL_DEVICE_FIELDS = {field.name for field in fields(CanonicalDeviceIdentity)}
_PRIVATE_IDENTITY_TEXT = re.compile(
    r"(?i)(?:\b(?:imei|serial|account|username|password|secret|token)\b|"
    r"(?<!\d)\d{15}(?!\d)|/home/|/users/|[a-z]:\\users\\|"
    r"-----begin [^-]+private key-----)"
)


def create_canonical_device_identity(
    *,
    manufacturer: str,
    brand: str,
    model: str,
    codename: str,
    evidence_claim_ids: Sequence[str],
    region: str = "",
    oem_identifiers: Mapping[str, str] | Sequence[tuple[str, str]] = (),
    soc: str = "",
    platform: str = "",
    marketing_names: Sequence[str] = (),
    aliases: Sequence[str] = (),
    family_ids: Sequence[str] = (),
) -> CanonicalDeviceIdentity:
    """Create one deterministic exact-device identity or fail closed as UNCONFIRMED."""

    manufacturer_value = _canonical_identity_text(manufacturer, 80, required=True)
    brand_value = _canonical_identity_text(brand, 80)
    model_value = _canonical_identity_text(model, 120, required=True)
    codename_value = _canonical_identity_text(codename, 80, required=True)
    region_value = _canonical_identity_text(region, 80)
    soc_value = _canonical_identity_text(soc, 120)
    platform_value = _canonical_identity_text(platform, 120)
    claims = _canonical_digests(evidence_claim_ids, required=True)
    identifiers = _canonical_oem_identifiers(oem_identifiers)
    names = _canonical_texts(marketing_names, 120)
    alias_values = _canonical_texts(aliases, 120)
    families = _canonical_texts(family_ids, 120)
    identity_basis = {
        "schema": "romverse.canonical-device-identity.v1",
        "manufacturer": manufacturer_value.casefold(),
        "brand": brand_value.casefold(),
        "model": model_value.casefold(),
        "codename": codename_value.casefold(),
        "region": region_value.casefold(),
        "oem_identifiers": tuple(
            (name.casefold(), value.casefold()) for name, value in identifiers
        ),
        "soc": soc_value.casefold(),
        "platform": platform_value.casefold(),
    }
    device_id = hashlib.sha256(
        json.dumps(identity_basis, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return CanonicalDeviceIdentity(
        1,
        device_id,
        manufacturer_value,
        brand_value,
        model_value,
        codename_value,
        region_value,
        identifiers,
        soc_value,
        platform_value,
        names,
        alias_values,
        families,
        claims,
    )


def canonical_device_identity_mapping(identity: CanonicalDeviceIdentity) -> dict[str, object]:
    return json.loads(json.dumps(asdict(identity)))


def parse_canonical_device_identity(raw: Mapping[str, object]) -> CanonicalDeviceIdentity:
    """Strictly load the additive schema without changing legacy identity receipts."""

    if (
        set(raw) != _CANONICAL_DEVICE_FIELDS
        or type(raw.get("schema_version")) is not int
        or raw.get("schema_version") != 1
    ):
        raise CanonicalIdentityError("Canonical device identity schema is unsupported")
    _canonical_zero_authority(raw)
    identifiers_raw = raw.get("oem_identifiers")
    if not isinstance(identifiers_raw, list):
        raise CanonicalIdentityError("Canonical OEM identifiers are malformed")
    identifiers: list[tuple[str, str]] = []
    for item in identifiers_raw:
        if not isinstance(item, list) or len(item) != 2:
            raise CanonicalIdentityError("Canonical OEM identifiers are malformed")
        identifiers.append((str(item[0]), str(item[1])))
    created = create_canonical_device_identity(
        manufacturer=_canonical_mapping_text(raw, "manufacturer"),
        brand=_canonical_mapping_text(raw, "brand"),
        model=_canonical_mapping_text(raw, "model"),
        codename=_canonical_mapping_text(raw, "codename"),
        region=_canonical_mapping_text(raw, "region"),
        oem_identifiers=identifiers,
        soc=_canonical_mapping_text(raw, "soc"),
        platform=_canonical_mapping_text(raw, "platform"),
        marketing_names=_canonical_raw_texts(raw.get("marketing_names")),
        aliases=_canonical_raw_texts(raw.get("aliases")),
        family_ids=_canonical_raw_texts(raw.get("family_ids")),
        evidence_claim_ids=_canonical_raw_texts(raw.get("evidence_claim_ids")),
    )
    if raw.get("device_id") != created.device_id:
        raise CanonicalIdentityError("Canonical device identity digest is invalid")
    if raw.get("compatibility_status") != "UNCONFIRMED":
        raise CanonicalIdentityError("Canonical identity cannot promote compatibility")
    expected = json.loads(json.dumps(canonical_device_identity_mapping(created)))
    if dict(raw) != expected:
        raise CanonicalIdentityError("Canonical device identity is not deterministic")
    return created


def _canonical_identity_text(value: object, limit: int, *, required: bool = False) -> str:
    if not isinstance(value, str) or "\0" in value:
        raise CanonicalIdentityError("Canonical identity text is malformed")
    cleaned = " ".join(value.split())
    if len(cleaned) > limit or (required and not cleaned):
        raise CanonicalIdentityError("Canonical identity remains UNCONFIRMED")
    if _PRIVATE_IDENTITY_TEXT.search(cleaned):
        raise CanonicalIdentityError("Canonical identity contains private data")
    return cleaned


def _canonical_texts(values: Sequence[str], limit: int) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or len(values) > 32:
        raise CanonicalIdentityError("Canonical identity collection is malformed")
    return tuple(
        sorted({_canonical_identity_text(value, limit, required=True) for value in values})
    )


def _canonical_digests(values: Sequence[str], *, required: bool) -> tuple[str, ...]:
    result = _canonical_texts(values, 64)
    if (required and not result) or any(
        re.fullmatch(r"[0-9a-f]{64}", value) is None for value in result
    ):
        raise CanonicalIdentityError("Canonical identity requires exact evidence digests")
    return result


def _canonical_oem_identifiers(
    values: Mapping[str, str] | Sequence[tuple[str, str]],
) -> tuple[tuple[str, str], ...]:
    items = values.items() if isinstance(values, Mapping) else values
    result = tuple(
        sorted(
            {
                (
                    _canonical_identity_text(name, 80, required=True),
                    _canonical_identity_text(value, 120, required=True),
                )
                for name, value in items
            }
        )
    )
    if len(result) > 32:
        raise CanonicalIdentityError("Canonical OEM identifiers exceed their boundary")
    return result


def _canonical_raw_texts(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise CanonicalIdentityError("Canonical identity collection is malformed")
    return tuple(value)


def _canonical_mapping_text(raw: Mapping[str, object], name: str) -> str:
    value = raw.get(name)
    if not isinstance(value, str):
        raise CanonicalIdentityError("Canonical identity text is malformed")
    return value


def _canonical_zero_authority(raw: Mapping[str, object]) -> None:
    required = {
        "execution_authority": "none",
        "phone_action_allowed": False,
        "guardian_approval": False,
        "bootloader_relock_allowed": False,
    }
    if any(
        raw.get(name) != value or type(raw.get(name)) is not type(value)
        for name, value in required.items()
    ):
        raise CanonicalIdentityError("Canonical identity cannot grant execution authority")


@dataclass(frozen=True, slots=True)
class DeviceNameCandidate:
    marketing_name: str
    source_id: str
    source_url: str
    authority: IdentityAuthority = IdentityAuthority.DISCOVERY
    confidence: int = 0


class DeviceNameProvider(Protocol):
    def search(self, device: AndroidDevice) -> Sequence[DeviceNameCandidate]: ...


@dataclass(frozen=True, slots=True)
class DeviceIdentityReceipt:
    schema_version: int
    receipt_id: str
    created_at: str
    identity_key: str
    manufacturer: str
    model: str
    codename: str
    marketing_name: str
    authority: IdentityAuthority
    source_ids: tuple[str, ...]
    source_urls: tuple[str, ...]
    receipt_digest: str


class DeviceIdentityResolver:
    """Resolve a retail device name without turning search text into truth.

    Resolution is deliberately conservative: a phone property wins, an exact
    model-specific Device Pack is next, and public results require either an
    OEM-owned HTTPS source or two independent hosts agreeing on the same name.
    """

    MAX_RECEIPT_BYTES = 16 * 1024
    RECEIPT_FIELDS = {
        "schema_version",
        "receipt_id",
        "created_at",
        "identity_key",
        "manufacturer",
        "model",
        "codename",
        "marketing_name",
        "authority",
        "source_ids",
        "source_urls",
        "receipt_digest",
    }

    def __init__(
        self,
        workspace: Path,
        registry: DevicePackRegistry,
        providers: Sequence[DeviceNameProvider] = (),
    ) -> None:
        self.workspace = workspace
        self.registry = registry
        self.providers = tuple(providers)
        self.receipt_root = workspace / "knowledge" / "device-identity"

    def resolve_local(self, device: AndroidDevice) -> AndroidDevice:
        if _clean_name(device.marketing_name):
            name = _clean_name(device.marketing_name)
            self._record(device, name, IdentityAuthority.ON_DEVICE, ("android-property",), ())
            return replace(device, marketing_name=name)

        pack = self.registry.resolve(device).pack
        if pack is None or not _pack_is_exact(pack, device):
            return self._resolve_cached(device)
        name = _pack_marketing_name(pack.display_name, device.manufacturer)
        if not name:
            return self._resolve_cached(device)
        self._record(device, name, IdentityAuthority.DEVICE_PACK, (pack.pack_id,), ())
        return replace(device, marketing_name=name)

    def _resolve_cached(self, device: AndroidDevice) -> AndroidDevice:
        """Reuse only an intact exact-identity receipt from a still-trusted authority."""

        receipt = self.load(device)
        if receipt is None or receipt.authority not in {
            IdentityAuthority.ON_DEVICE,
            IdentityAuthority.OEM_OFFICIAL,
            IdentityAuthority.GOOGLE_PLAY_CATALOG,
            IdentityAuthority.CORROBORATED_PUBLIC,
        }:
            return device
        name = _clean_name(receipt.marketing_name)
        return replace(device, marketing_name=name) if name else device

    def resolve_online(self, device: AndroidDevice) -> AndroidDevice:
        local = self.resolve_local(device)
        if local.marketing_name:
            return local

        candidates = tuple(
            candidate
            for provider in self.providers
            for candidate in provider.search(device)
            if _candidate_is_safe(candidate)
        )
        catalog = tuple(
            candidate
            for candidate in candidates
            if candidate.authority is IdentityAuthority.GOOGLE_PLAY_CATALOG
            and candidate.source_id == "google-play-supported-devices"
            and candidate.source_url
            == "https://storage.googleapis.com/play_public/supported_devices.csv"
        )
        if len(catalog) == 1:
            selected = catalog[0]
            name = _clean_name(selected.marketing_name)
            self._record(
                device,
                name,
                IdentityAuthority.GOOGLE_PLAY_CATALOG,
                (selected.source_id,),
                (selected.source_url,),
            )
            return replace(device, marketing_name=name)
        official = tuple(
            candidate
            for candidate in candidates
            if _is_official_oem_source(device.manufacturer, candidate.source_url)
        )
        if official:
            selected = max(official, key=lambda item: item.confidence)
            name = _clean_name(selected.marketing_name)
            self._record(
                device,
                name,
                IdentityAuthority.OEM_OFFICIAL,
                (selected.source_id,),
                (selected.source_url,),
            )
            return replace(device, marketing_name=name)

        by_name: dict[str, list[DeviceNameCandidate]] = defaultdict(list)
        for candidate in candidates:
            by_name[_normalized_name(candidate.marketing_name)].append(candidate)
        corroborated = [
            group
            for group in by_name.values()
            if len({_source_host(item.source_url) for item in group}) >= 2
        ]
        if not corroborated:
            return device
        selected_group = max(
            corroborated,
            key=lambda group: (len(group), max(item.confidence for item in group)),
        )
        selected = max(selected_group, key=lambda item: item.confidence)
        self._record(
            device,
            _clean_name(selected.marketing_name),
            IdentityAuthority.CORROBORATED_PUBLIC,
            tuple(sorted({item.source_id for item in selected_group})),
            tuple(sorted({item.source_url for item in selected_group})),
        )
        return replace(device, marketing_name=_clean_name(selected.marketing_name))

    def load(self, device: AndroidDevice) -> DeviceIdentityReceipt | None:
        path = self._receipt_path(device)
        try:
            raw = read_json_object(
                path,
                boundary=self.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
            if set(raw) != self.RECEIPT_FIELDS:
                return None
            digest = raw.get("receipt_digest")
            unsigned = dict(raw)
            unsigned.pop("receipt_digest", None)
            if (
                not _digest_value(digest)
                or digest != _digest(unsigned)
                or raw.get("identity_key") != _identity_key(device)
                or not _receipt_identity_matches(raw, device)
                or not _valid_receipt_shape(raw)
            ):
                return None
            authority = IdentityAuthority(str(raw["authority"]))
            source_ids = tuple(raw["source_ids"])
            source_urls = tuple(raw["source_urls"])
            if not _valid_authority_sources(
                str(raw["manufacturer"]),
                authority,
                source_ids,
                source_urls,
            ):
                return None
            return DeviceIdentityReceipt(
                schema_version=int(raw["schema_version"]),
                receipt_id=str(raw["receipt_id"]),
                created_at=str(raw["created_at"]),
                identity_key=str(raw["identity_key"]),
                manufacturer=str(raw["manufacturer"]),
                model=str(raw["model"]),
                codename=str(raw["codename"]),
                marketing_name=str(raw["marketing_name"]),
                authority=authority,
                source_ids=source_ids,
                source_urls=source_urls,
                receipt_digest=str(digest),
            )
        except (LocalStoreError, OSError, ValueError, KeyError, TypeError):
            return None

    def _record(
        self,
        device: AndroidDevice,
        marketing_name: str,
        authority: IdentityAuthority,
        source_ids: tuple[str, ...],
        source_urls: tuple[str, ...],
    ) -> DeviceIdentityReceipt:
        existing = self.load(device)
        if (
            existing is not None
            and existing.marketing_name == marketing_name
            and existing.authority is authority
            and existing.source_ids == source_ids
            and existing.source_urls == source_urls
        ):
            return existing
        payload = {
            "schema_version": 1,
            "receipt_id": uuid4().hex,
            "created_at": datetime.now(UTC).isoformat(),
            "identity_key": _identity_key(device),
            "manufacturer": _bounded(device.manufacturer, 80),
            "model": _bounded(device.model, 120),
            "codename": _bounded(device.codename, 80),
            "marketing_name": _bounded(marketing_name, 120),
            "authority": authority.value,
            "source_ids": source_ids,
            "source_urls": source_urls,
        }
        receipt = DeviceIdentityReceipt(
            **{**payload, "authority": authority}, receipt_digest=_digest(payload)
        )
        ensure_private_directory(self.receipt_root, boundary=self.workspace)
        path = self._receipt_path(device)
        serialized = {**asdict(receipt), "authority": receipt.authority.value}
        atomic_write_json(
            path,
            serialized,
            boundary=self.workspace,
            maximum_bytes=self.MAX_RECEIPT_BYTES,
        )
        return receipt

    def _receipt_path(self, device: AndroidDevice) -> Path:
        return self.receipt_root / f"{_identity_key(device)}.romverse"


def _pack_is_exact(pack, device: AndroidDevice) -> bool:
    if pack.priority <= 0 or pack.manufacturers == ("*",):
        return False
    model = device.model.casefold().strip()
    products = {device.product.casefold().strip(), device.codename.casefold().strip()}
    exact_model = any(_literal(pattern) == model for pattern in pack.model_patterns)
    exact_product = any(_literal(pattern) in products for pattern in pack.product_patterns)
    return bool(exact_model or exact_product)


def _literal(pattern: str) -> str:
    value = pattern.casefold().strip()
    return "" if any(token in value for token in "*?[") else value


def _pack_marketing_name(display_name: str, manufacturer: str) -> str:
    name = _clean_name(display_name.split(" / ", 1)[0])
    if not name or name.casefold() in {"generic android", manufacturer.casefold().strip()}:
        return ""
    return name


def _candidate_is_safe(candidate: DeviceNameCandidate) -> bool:
    name = _clean_name(candidate.marketing_name)
    parts = urlsplit(candidate.source_url)
    if not name or len(name) < 3 or parts.scheme != "https" or not parts.hostname:
        return False
    if candidate.authority is IdentityAuthority.GOOGLE_PLAY_CATALOG:
        return (
            candidate.source_id == "google-play-supported-devices"
            and candidate.source_url
            == "https://storage.googleapis.com/play_public/supported_devices.csv"
        )
    return _public_host(parts.hostname)


def _public_host(hostname: str) -> bool:
    host = hostname.casefold().rstrip(".")
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return False
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    except OSError:
        return False
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return False
        if not ip.is_global:
            return False
    return bool(addresses)


_OEM_DOMAINS = {
    "google": ("google.com", "store.google.com"),
    "motorola": ("motorola.com",),
    "oneplus": ("oneplus.com",),
    "samsung": ("samsung.com",),
    "sony": ("sony.com",),
    "xiaomi": ("mi.com", "xiaomi.com"),
}


def _is_official_oem_source(manufacturer: str, url: str) -> bool:
    host = _source_host(url)
    domains = _OEM_DOMAINS.get(manufacturer.casefold().strip(), ())
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


def _source_host(url: str) -> str:
    return (urlsplit(url).hostname or "").casefold().rstrip(".")


def _identity_key(device: AndroidDevice) -> str:
    values = {
        "manufacturer": device.manufacturer.casefold().strip(),
        "model": device.model.casefold().strip(),
        "codename": device.codename.casefold().strip(),
        "product": device.product.casefold().strip(),
    }
    if device.brand.strip():
        values["brand"] = device.brand.casefold().strip()
    return hashlib.sha256(
        json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _normalized_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _clean_name(value).casefold()).strip()


def _clean_name(value: str) -> str:
    return " ".join(str(value).split())[:120]


def _bounded(value: str, limit: int) -> str:
    return " ".join(str(value).split())[:limit]


def _valid_receipt_shape(raw: dict[str, object]) -> bool:
    if type(raw.get("schema_version")) is not int or raw["schema_version"] != 1:
        return False
    receipt_id = raw.get("receipt_id")
    identity_key = raw.get("identity_key")
    if not isinstance(receipt_id, str) or re.fullmatch(r"[0-9a-f]{32}", receipt_id) is None:
        return False
    if not isinstance(identity_key, str) or re.fullmatch(r"[0-9a-f]{64}", identity_key) is None:
        return False
    created_at = raw.get("created_at")
    if not isinstance(created_at, str):
        return False
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if created.tzinfo is None or created > datetime.now(UTC) + timedelta(minutes=5):
        return False
    text_limits = {
        "manufacturer": 80,
        "model": 120,
        "codename": 80,
        "marketing_name": 120,
        "authority": 40,
    }
    for field, limit in text_limits.items():
        value = raw.get(field)
        if not isinstance(value, str) or "\0" in value or len(value) > limit:
            return False
    if len(str(raw["marketing_name"]).strip()) < 3:
        return False
    source_ids = raw.get("source_ids")
    source_urls = raw.get("source_urls")
    if not isinstance(source_ids, list) or not isinstance(source_urls, list):
        return False
    if not 1 <= len(source_ids) <= 8 or len(source_urls) > 8:
        return False
    if any(
        not isinstance(value, str) or not value or "\0" in value or len(value) > 120
        for value in source_ids
    ):
        return False
    if any(
        not isinstance(value, str) or not value or "\0" in value or len(value) > 2048
        for value in source_urls
    ):
        return False
    return len(set(source_ids)) == len(source_ids) and len(set(source_urls)) == len(source_urls)


def _receipt_identity_matches(raw: dict[str, object], device: AndroidDevice) -> bool:
    return (
        raw.get("manufacturer") == _bounded(device.manufacturer, 80)
        and raw.get("model") == _bounded(device.model, 120)
        and raw.get("codename") == _bounded(device.codename, 80)
    )


def _valid_authority_sources(
    manufacturer: str,
    authority: IdentityAuthority,
    source_ids: tuple[str, ...],
    source_urls: tuple[str, ...],
) -> bool:
    if authority is IdentityAuthority.ON_DEVICE:
        return source_ids == ("android-property",) and not source_urls
    if authority is IdentityAuthority.DEVICE_PACK:
        return len(source_ids) == 1 and not source_urls
    if authority is IdentityAuthority.OEM_OFFICIAL:
        return (
            len(source_ids) == 1
            and len(source_urls) == 1
            and _public_https_shape(source_urls[0])
            and _is_official_oem_source(manufacturer, source_urls[0])
        )
    if authority is IdentityAuthority.GOOGLE_PLAY_CATALOG:
        return source_ids == ("google-play-supported-devices",) and source_urls == (
            "https://storage.googleapis.com/play_public/supported_devices.csv",
        )
    if authority is IdentityAuthority.CORROBORATED_PUBLIC:
        return (
            len(source_ids) >= 2
            and len(source_urls) >= 2
            and all(_public_https_shape(url) for url in source_urls)
            and len({_source_host(url) for url in source_urls}) >= 2
        )
    return False


def _public_https_shape(url: str) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").casefold().rstrip(".")
    if parts.scheme != "https" or not host or parts.username or parts.password:
        return False
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return "." in host and not host.startswith(".") and not host.endswith(".")


def _digest_value(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _digest(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
