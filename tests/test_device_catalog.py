from __future__ import annotations

import csv
import io
import json
import os
from datetime import UTC, datetime, timedelta

import pytest

import romverse.device.catalog as catalog_module
from romverse.device.catalog import (
    GOOGLE_PLAY_CATALOG_URL,
    DeviceCatalogError,
    GooglePlayDeviceCatalog,
)
from romverse.device.identity import DeviceIdentityResolver, IdentityAuthority
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.registry import DevicePackRegistry


class _Response:
    def __init__(
        self,
        payload: bytes,
        *,
        url: str = GOOGLE_PLAY_CATALOG_URL,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self._url = url
        self._stream = io.BytesIO(payload)
        self.headers = headers or {
            "Content-Length": str(len(payload)),
            "ETag": '"official-test"',
            "Last-Modified": "Tue, 01 Sep 2026 00:00:00 GMT",
        }

    def geturl(self) -> str:
        return self._url

    def read(self, amount: int = -1) -> bytes:
        return self._stream.read(amount)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _payload(*rows: tuple[str, str, str, str]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(GooglePlayDeviceCatalog.HEADER)
    writer.writerows(rows)
    return output.getvalue().encode("utf-16")


def _device(**changes: str) -> AndroidDevice:
    values = {
        "brand": "Xiaomi",
        "manufacturer": "Xiaomi",
        "model": "2509FPN0BC",
        "codename": "popsicle",
        **changes,
    }
    return AndroidDevice("private", DeviceState.DEVICE, **values)


def _sync(
    catalog: GooglePlayDeviceCatalog,
    payload: bytes,
    *,
    now: datetime | None = None,
    **response_changes: object,
):
    return catalog.sync(
        open_url=lambda *_args, **_kwargs: _Response(payload, **response_changes),
        now=now,
    )


def test_official_catalog_resolves_exact_brand_device_and_model_without_authority(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(GooglePlayDeviceCatalog, "MINIMUM_ENTRIES", 1)
    catalog = GooglePlayDeviceCatalog(tmp_path)
    status = _sync(
        catalog,
        _payload(
            ("Xiaomi", "Xiaomi 17 Pro Max", "popsicle", "2509FPN0BC"),
            ("Google", "Pixel 6", "oriole", "Pixel 6"),
        ),
    )

    match = catalog.match(_device())
    assert status.valid and status.fresh
    assert status.entry_count == 2
    assert match.matched and not match.ambiguous
    assert match.marketing_name == "Xiaomi 17 Pro Max"
    assert match.model == "2509FPN0BC"
    assert "Exact Google Play identity" in match.reason

    resolver = DeviceIdentityResolver(tmp_path, DevicePackRegistry(()), (catalog,))
    resolved = resolver.resolve_online(_device())
    receipt = resolver.load(resolved)
    assert resolved.marketing_name == "Xiaomi 17 Pro Max"
    assert receipt is not None
    assert receipt.authority is IdentityAuthority.GOOGLE_PLAY_CATALOG
    assert receipt.source_urls == (GOOGLE_PLAY_CATALOG_URL,)
    if os.name != "nt":
        assert catalog.catalog_path.stat().st_mode & 0o777 == 0o600
        assert catalog.receipt_path.stat().st_mode & 0o777 == 0o600


def test_catalog_uses_exact_model_to_narrow_variants_and_never_guesses_ambiguity(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(GooglePlayDeviceCatalog, "MINIMUM_ENTRIES", 1)
    catalog = GooglePlayDeviceCatalog(tmp_path)
    _sync(
        catalog,
        _payload(
            ("Example", "Example One", "shared", "MODEL-ONE"),
            ("Example", "Example Two", "shared", "MODEL-TWO"),
        ),
    )

    exact = catalog.match(
        _device(brand="Example", manufacturer="Example", codename="shared", model="MODEL-TWO")
    )
    ambiguous = catalog.match(
        _device(brand="Example", manufacturer="Example", codename="shared", model="UNKNOWN")
    )

    assert exact.matched and exact.marketing_name == "Example Two"
    assert not ambiguous.matched and ambiguous.ambiguous
    assert "will not guess" in ambiguous.reason


def test_catalog_searches_only_the_verified_local_mirror_with_bounded_ranked_results(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(GooglePlayDeviceCatalog, "MINIMUM_ENTRIES", 1)
    catalog = GooglePlayDeviceCatalog(tmp_path)
    _sync(
        catalog,
        _payload(
            ("Example", "Nebula Ultra", "nebula", "EX-200"),
            ("Example", "Nebula", "nebula-lite", "EX-100"),
            ("Other", "Nebula One", "one", "NEBULA"),
        ),
    )

    exact = catalog.search_entries("example ex-200")
    ranked = catalog.search_entries("nebula", limit=2)

    assert [entry.marketing_name for entry in exact] == ["Nebula Ultra"]
    assert [entry.marketing_name for entry in ranked] == ["Nebula", "Nebula One"]
    assert not catalog.search_entries("")
    assert not catalog.search_entries("n")
    assert not catalog.search_entries("nebula", limit=0)
    assert catalog.contains(exact[0])

    catalog.catalog_path.write_bytes(catalog.catalog_path.read_bytes() + b"tampered")
    assert not catalog.search_entries("nebula")
    assert not catalog.contains(exact[0])


def test_catalog_rejects_redirect_encoding_size_and_tampering_without_replacing_cache(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(GooglePlayDeviceCatalog, "MINIMUM_ENTRIES", 1)
    catalog = GooglePlayDeviceCatalog(tmp_path)
    payload = _payload(("Xiaomi", "Xiaomi 17 Pro Max", "popsicle", "2509FPN0BC"))
    _sync(catalog, payload)
    original = catalog.catalog_path.read_bytes()

    with pytest.raises(DeviceCatalogError, match="unexpected route"):
        _sync(catalog, payload, url="https://example.com/redirect.csv")
    with pytest.raises(DeviceCatalogError, match="encoding marker"):
        _sync(catalog, b"Retail Branding,Marketing Name,Device,Model\n")
    with pytest.raises(DeviceCatalogError, match="size"):
        _sync(catalog, payload, headers={"Content-Length": str(20 * 1024 * 1024)})
    with pytest.raises(DeviceCatalogError, match="incomplete"):
        _sync(catalog, payload, headers={"Content-Length": str(len(payload) + 1)})
    with pytest.raises(DeviceCatalogError, match="content type"):
        _sync(
            catalog,
            payload,
            headers={"Content-Length": str(len(payload)), "Content-Type": "text/html"},
        )
    assert catalog.catalog_path.read_bytes() == original
    assert catalog.status().valid

    catalog.catalog_path.write_bytes(original + b"tampered")
    assert not catalog.status().valid
    assert not catalog.match(_device()).matched

    _sync(catalog, payload)
    if os.name != "nt":
        outside = tmp_path / "outside-catalog.csv"
        outside.write_bytes(catalog.catalog_path.read_bytes())
        catalog.catalog_path.unlink()
        catalog.catalog_path.symlink_to(outside)
        assert not catalog.status().valid
        catalog.catalog_path.unlink()
        _sync(catalog, payload)
    receipt = json.loads(catalog.receipt_path.read_text(encoding="utf-8"))
    receipt["execution_authority"] = "full"
    unsigned = dict(receipt)
    unsigned.pop("receipt_digest")
    receipt["receipt_digest"] = catalog_module._digest(unsigned)
    catalog.receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    assert not catalog.status().valid


def test_stale_verified_catalog_remains_read_only_usable_while_refresh_is_due(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(GooglePlayDeviceCatalog, "MINIMUM_ENTRIES", 1)
    catalog = GooglePlayDeviceCatalog(tmp_path)
    fetched = datetime.now(UTC) - timedelta(days=8)
    _sync(
        catalog,
        _payload(("Xiaomi", "Xiaomi 17 Pro Max", "popsicle", "2509FPN0BC")),
        now=fetched,
    )

    status = catalog.status(now=datetime.now(UTC))

    assert status.valid and not status.fresh
    assert catalog.needs_refresh(now=datetime.now(UTC))
    assert catalog.match(_device()).marketing_name == "Xiaomi 17 Pro Max"
