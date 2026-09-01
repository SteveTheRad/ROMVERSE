from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import socket
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
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
    CORROBORATED_PUBLIC = "corroborated-public"
    DISCOVERY = "discovery"


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
