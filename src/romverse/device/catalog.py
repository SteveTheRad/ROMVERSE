from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import unicodedata
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from romverse.device.identity import DeviceNameCandidate, IdentityAuthority
from romverse.device.models import AndroidDevice
from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_bytes,
    atomic_write_json,
    ensure_private_directory,
    read_json_object,
    read_regular_bytes,
)

GOOGLE_PLAY_CATALOG_URL = "https://storage.googleapis.com/play_public/supported_devices.csv"
GOOGLE_PLAY_CATALOG_SOURCE_ID = "google-play-supported-devices"


class CatalogResponse(Protocol):
    status: int
    headers: object

    def geturl(self) -> str: ...

    def read(self, amount: int = -1) -> bytes: ...

    def __enter__(self) -> CatalogResponse: ...

    def __exit__(self, *args: object) -> object: ...


@dataclass(frozen=True, slots=True)
class DeviceCatalogEntry:
    retail_branding: str
    marketing_name: str
    device: str
    model: str


@dataclass(frozen=True, slots=True)
class DeviceCatalogMatch:
    matched: bool
    ambiguous: bool
    marketing_name: str = ""
    model: str = ""
    variant_count: int = 0
    reason: str = ""


@dataclass(frozen=True, slots=True)
class DeviceCatalogStatus:
    valid: bool
    fresh: bool
    reason: str
    entry_count: int = 0
    fetched_at: str = ""
    content_sha256: str = ""


class DeviceCatalogError(RuntimeError):
    """The official identity catalog failed a bounded network or evidence contract."""


class GooglePlayDeviceCatalog:
    """Bounded local mirror of Google's public Android supported-device catalog.

    A match may supply a retail name only. It never creates a Device Pack, build
    contract, flash contract, approval, command, or execution authority.
    """

    SCHEMA_VERSION = 1
    MAXIMUM_BYTES = 16 * 1024 * 1024
    MAXIMUM_ENTRIES = 100_000
    MINIMUM_ENTRIES = 1_000
    MAXIMUM_AGE = timedelta(days=7)
    MAXIMUM_SEARCH_RESULTS = 25
    CHUNK_BYTES = 128 * 1024
    HEADER = ("Retail Branding", "Marketing Name", "Device", "Model")
    RECEIPT_FIELDS = frozenset(
        {
            "schema_version",
            "source_id",
            "source_url",
            "fetched_at",
            "content_sha256",
            "content_bytes",
            "entry_count",
            "etag",
            "last_modified",
            "identity_authority",
            "build_authority",
            "flash_authority",
            "execution_authority",
            "receipt_digest",
        }
    )

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.root = workspace / "knowledge" / "android-device-catalog"
        self.catalog_path = self.root / "google-play-supported-devices.csv"
        self.receipt_path = self.root / "google-play-supported-devices.romverse"
        self._loaded_digest = ""
        self._entries: tuple[DeviceCatalogEntry, ...] = ()
        self._index: dict[tuple[str, str], tuple[DeviceCatalogEntry, ...]] = {}

    def status(self, *, now: datetime | None = None) -> DeviceCatalogStatus:
        try:
            receipt, entries = self._load_verified()
        except (DeviceCatalogError, LocalStoreError, OSError, ValueError, TypeError):
            return DeviceCatalogStatus(
                False,
                False,
                "Official Android device IDs have not been synced or the local evidence was rejected",
            )
        fetched_at = str(receipt["fetched_at"])
        fetched = _aware_time(fetched_at)
        current = now or datetime.now(UTC)
        fresh = fetched <= current + timedelta(minutes=5) and current - fetched <= self.MAXIMUM_AGE
        reason = (
            "Official Google Play device IDs are current and integrity checked"
            if fresh
            else "Official device IDs are usable for read-only naming but an update is due"
        )
        return DeviceCatalogStatus(
            True,
            fresh,
            reason,
            len(entries),
            fetched_at,
            str(receipt["content_sha256"]),
        )

    def needs_refresh(self, *, now: datetime | None = None) -> bool:
        status = self.status(now=now)
        return not status.valid or not status.fresh

    def sync(
        self,
        *,
        open_url: Callable[..., CatalogResponse] | None = None,
        now: datetime | None = None,
    ) -> DeviceCatalogStatus:
        opener = open_url or urllib.request.urlopen
        request = urllib.request.Request(
            GOOGLE_PLAY_CATALOG_URL,
            headers={
                "Accept": "text/csv",
                "Accept-Encoding": "identity",
                "User-Agent": "ROMVERSE/0.1 official-device-catalog",
            },
        )
        try:
            with opener(request, timeout=20) as response:  # noqa: S310 - fixed Google URL
                if response.status != 200 or response.geturl() != GOOGLE_PLAY_CATALOG_URL:
                    raise DeviceCatalogError("Official device catalog returned an unexpected route")
                content_encoding = str(_header(response.headers, "Content-Encoding")).casefold()
                if content_encoding not in {"", "identity"}:
                    raise DeviceCatalogError("Compressed catalog responses are not accepted")
                content_type = _header(response.headers, "Content-Type").casefold()
                if content_type and not content_type.startswith("text/csv"):
                    raise DeviceCatalogError("Official device catalog content type is invalid")
                reported = _content_length(response.headers)
                if reported is not None and not 0 < reported <= self.MAXIMUM_BYTES:
                    raise DeviceCatalogError("Official device catalog size is outside the boundary")
                chunks: list[bytes] = []
                total = 0
                while True:
                    chunk = response.read(self.CHUNK_BYTES)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > self.MAXIMUM_BYTES:
                        raise DeviceCatalogError(
                            "Official device catalog exceeded the size boundary"
                        )
                    chunks.append(chunk)
                payload = b"".join(chunks)
                if reported is not None and reported != len(payload):
                    raise DeviceCatalogError("Official device catalog download was incomplete")
                entries = self._parse(payload)
                etag = _bounded_header(_header(response.headers, "ETag"))
                last_modified = _bounded_header(_header(response.headers, "Last-Modified"))
        except DeviceCatalogError:
            raise
        except (OSError, TimeoutError, ValueError, TypeError, urllib.error.URLError) as exc:
            raise DeviceCatalogError("Official Android device IDs could not be downloaded") from exc

        fetched_at = (now or datetime.now(UTC)).isoformat()
        digest = hashlib.sha256(payload).hexdigest()
        receipt: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "source_id": GOOGLE_PLAY_CATALOG_SOURCE_ID,
            "source_url": GOOGLE_PLAY_CATALOG_URL,
            "fetched_at": fetched_at,
            "content_sha256": digest,
            "content_bytes": len(payload),
            "entry_count": len(entries),
            "etag": etag,
            "last_modified": last_modified,
            "identity_authority": "read-only retail identity",
            "build_authority": "none",
            "flash_authority": "none",
            "execution_authority": "none",
        }
        receipt["receipt_digest"] = _digest(receipt)
        try:
            ensure_private_directory(self.root, boundary=self.workspace)
            atomic_write_bytes(
                self.catalog_path,
                payload,
                boundary=self.workspace,
                maximum_bytes=self.MAXIMUM_BYTES,
            )
            atomic_write_json(
                self.receipt_path,
                receipt,
                boundary=self.workspace,
                maximum_bytes=16 * 1024,
            )
        except LocalStoreError as exc:
            raise DeviceCatalogError(
                "Official Android device IDs could not be stored safely"
            ) from exc
        self._cache(digest, entries)
        return self.status(now=now)

    def search(self, device: AndroidDevice) -> tuple[DeviceNameCandidate, ...]:
        match = self.match(device)
        if not match.matched:
            return ()
        return (
            DeviceNameCandidate(
                match.marketing_name,
                GOOGLE_PLAY_CATALOG_SOURCE_ID,
                GOOGLE_PLAY_CATALOG_URL,
                IdentityAuthority.GOOGLE_PLAY_CATALOG,
                100,
            ),
        )

    def search_entries(
        self,
        query: str,
        *,
        limit: int = 12,
    ) -> tuple[DeviceCatalogEntry, ...]:
        """Search the verified local mirror without making a network request.

        Results are retail-identity evidence only. Searching cannot create a
        Device Pack, build contract, flash contract, approval, or device action.
        """

        normalized = _key(str(query).replace("\x00", " "))[:120]
        if len(normalized) < 2 or type(limit) is not int or limit <= 0:
            return ()
        bounded_limit = min(limit, self.MAXIMUM_SEARCH_RESULTS)
        try:
            _receipt, entries = self._load_verified()
        except (DeviceCatalogError, LocalStoreError, OSError, ValueError, TypeError):
            return ()

        terms = tuple(term for term in normalized.split() if term)
        ranked: list[tuple[int, str, str, str, int, DeviceCatalogEntry]] = []
        for position, entry in enumerate(entries):
            fields = tuple(
                _key(value)
                for value in (
                    entry.retail_branding,
                    entry.marketing_name,
                    entry.device,
                    entry.model,
                )
            )
            searchable = " ".join(fields)
            if not all(term in searchable for term in terms):
                continue
            if normalized in fields:
                rank = 0
            elif fields[1].startswith(normalized):
                rank = 1
            elif any(field.startswith(normalized) for field in fields):
                rank = 2
            else:
                rank = 3
            ranked.append((rank, fields[1], fields[2], fields[3], position, entry))

        ranked.sort(key=lambda item: item[:-1])
        return tuple(item[-1] for item in ranked[:bounded_limit])

    def contains(self, entry: DeviceCatalogEntry) -> bool:
        """Revalidate one displayed identity against the current verified mirror."""

        if not isinstance(entry, DeviceCatalogEntry):
            return False
        try:
            _receipt, entries = self._load_verified()
        except (DeviceCatalogError, LocalStoreError, OSError, ValueError, TypeError):
            return False
        return entry in entries

    def match(self, device: AndroidDevice) -> DeviceCatalogMatch:
        brand = _key(device.brand)
        codename = _key(device.codename)
        if not brand or not codename:
            return DeviceCatalogMatch(
                False,
                False,
                reason="Exact Build.BRAND and Build.DEVICE properties are required",
            )
        try:
            _receipt, entries = self._load_verified()
        except (DeviceCatalogError, LocalStoreError, OSError, ValueError, TypeError):
            return DeviceCatalogMatch(False, False, reason="Official device ID catalog unavailable")
        candidates = self._index.get((brand, codename), ())
        if not candidates:
            return DeviceCatalogMatch(
                False,
                False,
                reason=f"No exact official {device.brand}/{device.codename} identity was found",
            )
        model = _key(device.model)
        exact_models = tuple(item for item in candidates if model and _key(item.model) == model)
        selected = exact_models or candidates
        names: dict[str, str] = {}
        for item in selected:
            normalized = _key(item.marketing_name)
            if normalized:
                names.setdefault(normalized, item.marketing_name)
        if len(names) != 1:
            return DeviceCatalogMatch(
                False,
                True,
                variant_count=len(selected),
                reason=(
                    "Official brand/device identity has multiple retail names; ROMVERSE will not guess"
                ),
            )
        marketing_name = next(iter(names.values()))
        matched_model = next((item.model for item in selected if _key(item.model) == model), "")
        return DeviceCatalogMatch(
            True,
            False,
            marketing_name,
            matched_model,
            len(selected),
            (
                f"Exact Google Play identity matched {device.brand}/{device.codename}"
                + (f" and model {device.model}" if exact_models else "")
            ),
        )

    def _load_verified(self) -> tuple[dict[str, object], tuple[DeviceCatalogEntry, ...]]:
        receipt = read_json_object(
            self.receipt_path,
            boundary=self.workspace,
            maximum_bytes=16 * 1024,
        )
        if set(receipt) != self.RECEIPT_FIELDS or not self._valid_receipt(receipt):
            raise DeviceCatalogError("Official device catalog receipt is invalid")
        payload = read_regular_bytes(
            self.catalog_path,
            boundary=self.workspace,
            maximum_bytes=self.MAXIMUM_BYTES,
        )
        digest = hashlib.sha256(payload).hexdigest()
        if digest != receipt["content_sha256"] or len(payload) != receipt["content_bytes"]:
            raise DeviceCatalogError("Official device catalog content does not match its receipt")
        if digest == self._loaded_digest and self._entries:
            entries = self._entries
        else:
            entries = self._parse(payload)
            self._cache(digest, entries)
        if len(entries) != receipt["entry_count"]:
            raise DeviceCatalogError(
                "Official device catalog entry count does not match its receipt"
            )
        return receipt, entries

    def _valid_receipt(self, receipt: dict[str, object]) -> bool:
        unsigned = dict(receipt)
        digest = unsigned.pop("receipt_digest", None)
        try:
            fetched = _aware_time(str(receipt.get("fetched_at", "")))
        except ValueError:
            return False
        return bool(
            receipt.get("schema_version") == self.SCHEMA_VERSION
            and receipt.get("source_id") == GOOGLE_PLAY_CATALOG_SOURCE_ID
            and receipt.get("source_url") == GOOGLE_PLAY_CATALOG_URL
            and fetched <= datetime.now(UTC) + timedelta(minutes=5)
            and _sha256(receipt.get("content_sha256"))
            and type(receipt.get("content_bytes")) is int
            and 0 < int(receipt["content_bytes"]) <= self.MAXIMUM_BYTES
            and type(receipt.get("entry_count")) is int
            and self.MINIMUM_ENTRIES <= int(receipt["entry_count"]) <= self.MAXIMUM_ENTRIES
            and _safe_header(receipt.get("etag"))
            and _safe_header(receipt.get("last_modified"))
            and receipt.get("identity_authority") == "read-only retail identity"
            and receipt.get("build_authority") == "none"
            and receipt.get("flash_authority") == "none"
            and receipt.get("execution_authority") == "none"
            and _sha256(digest)
            and digest == _digest(unsigned)
        )

    def _parse(self, payload: bytes) -> tuple[DeviceCatalogEntry, ...]:
        if not payload.startswith(b"\xff\xfe"):
            raise DeviceCatalogError("Official device catalog encoding marker is invalid")
        try:
            decoded = payload.decode("utf-16")
            reader = csv.reader(io.StringIO(decoded, newline=""), strict=True)
            header = tuple(next(reader))
            if header != self.HEADER:
                raise DeviceCatalogError("Official device catalog columns are invalid")
            entries: list[DeviceCatalogEntry] = []
            seen: set[DeviceCatalogEntry] = set()
            for row in reader:
                if len(row) != len(self.HEADER):
                    raise DeviceCatalogError("Official device catalog row is invalid")
                entry = DeviceCatalogEntry(*(_text(value) for value in row))
                if entry in seen:
                    continue
                seen.add(entry)
                entries.append(entry)
                if len(entries) > self.MAXIMUM_ENTRIES:
                    raise DeviceCatalogError("Official device catalog has too many entries")
        except (UnicodeDecodeError, csv.Error, StopIteration) as exc:
            raise DeviceCatalogError("Official device catalog could not be parsed") from exc
        if len(entries) < self.MINIMUM_ENTRIES:
            raise DeviceCatalogError("Official device catalog is unexpectedly incomplete")
        return tuple(entries)

    def _cache(self, digest: str, entries: tuple[DeviceCatalogEntry, ...]) -> None:
        grouped: dict[tuple[str, str], list[DeviceCatalogEntry]] = {}
        for entry in entries:
            brand = _key(entry.retail_branding)
            device = _key(entry.device)
            if brand and device:
                grouped.setdefault((brand, device), []).append(entry)
        self._loaded_digest = digest
        self._entries = entries
        self._index = {key: tuple(value) for key, value in grouped.items()}


def _header(headers: object, name: str) -> str:
    getter = getattr(headers, "get", None)
    value = getter(name, "") if callable(getter) else ""
    return str(value or "")


def _content_length(headers: object) -> int | None:
    raw = _header(headers, "Content-Length").strip()
    if not raw:
        return None
    if re.fullmatch(r"[0-9]+", raw) is None:
        raise DeviceCatalogError("Official device catalog length is invalid")
    return int(raw)


def _bounded_header(value: str) -> str:
    cleaned = " ".join(value.split())
    return cleaned[:200] if "\x00" not in cleaned else ""


def _safe_header(value: object) -> bool:
    return isinstance(value, str) and "\x00" not in value and len(value) <= 200


def _text(value: str) -> str:
    cleaned = " ".join(unicodedata.normalize("NFKC", value).split())
    if len(cleaned) > 160 or any(ord(character) < 32 for character in cleaned):
        raise DeviceCatalogError("Official device catalog contains unsafe text")
    return cleaned


def _key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value)).casefold().split())


def _aware_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(UTC)


def _sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _digest(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
