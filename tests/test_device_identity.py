from __future__ import annotations

from dataclasses import replace

import romverse.device.identity as identity_module
from romverse.device.identity import (
    DeviceIdentityResolver,
    DeviceNameCandidate,
    IdentityAuthority,
)
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.models import DevicePack
from romverse.device_packs.registry import DevicePackRegistry


def _device(**changes) -> AndroidDevice:
    return replace(
        AndroidDevice(
            "private",
            DeviceState.DEVICE,
            manufacturer="Xiaomi",
            model="2509FPN0BC",
            product="popsicle",
            codename="popsicle",
        ),
        **changes,
    )


def _pack(**changes) -> DevicePack:
    return replace(
        DevicePack(
            pack_id="xiaomi.popsicle",
            version="1",
            display_name="Xiaomi 17 Pro Max / HyperOS 4",
            priority=300,
            manufacturers=("xiaomi",),
            model_patterns=("2509fpn0bc",),
            product_patterns=("popsicle",),
            capabilities=(),
            notes=(),
            sha256="a" * 64,
        ),
        **changes,
    )


def test_phone_reported_name_wins_and_receipt_detects_tampering(tmp_path):
    resolver = DeviceIdentityResolver(tmp_path, DevicePackRegistry((_pack(),)))
    resolved = resolver.resolve_local(_device(marketing_name="  Xiaomi 17 Pro Max "))

    assert resolved.marketing_name == "Xiaomi 17 Pro Max"
    receipt = resolver.load(resolved)
    assert receipt is not None
    assert receipt.authority is IdentityAuthority.ON_DEVICE

    path = next((tmp_path / "knowledge" / "device-identity").glob("*.romverse"))
    path.write_text(path.read_text().replace("17 Pro Max", "Fake Phone"))
    assert resolver.load(resolved) is None


def test_exact_device_pack_supplies_retail_name_but_generic_pack_cannot(tmp_path):
    resolved = DeviceIdentityResolver(tmp_path, DevicePackRegistry((_pack(),))).resolve_local(
        _device()
    )
    assert resolved.marketing_name == "Xiaomi 17 Pro Max"

    generic = _pack(
        pack_id="android.generic",
        display_name="Generic Android",
        priority=0,
        manufacturers=("*",),
        model_patterns=(),
        product_patterns=(),
    )
    untouched = DeviceIdentityResolver(
        tmp_path / "generic", DevicePackRegistry((generic,))
    ).resolve_local(_device())
    assert not untouched.marketing_name


def test_single_public_result_cannot_rename_but_two_independent_sources_can(tmp_path, monkeypatch):
    monkeypatch.setattr(identity_module, "_public_host", lambda _host: True)

    class OneProvider:
        def search(self, _device):
            return (
                DeviceNameCandidate(
                    "Xiaomi 17 Pro Max",
                    "community-one",
                    "https://example.com/device",
                ),
            )

    assert (
        not DeviceIdentityResolver(tmp_path / "one", DevicePackRegistry(()), (OneProvider(),))
        .resolve_online(_device())
        .marketing_name
    )

    class TwoProvider:
        def search(self, _device):
            return (
                DeviceNameCandidate(
                    "Xiaomi 17 Pro Max",
                    "source-one",
                    "https://example.com/device",
                    confidence=70,
                ),
                DeviceNameCandidate(
                    "Xiaomi 17 Pro Max",
                    "source-two",
                    "https://another.example/device",
                    confidence=80,
                ),
            )

    resolved = DeviceIdentityResolver(
        tmp_path / "two", DevicePackRegistry(()), (TwoProvider(),)
    ).resolve_online(_device())
    assert resolved.marketing_name == "Xiaomi 17 Pro Max"
    assert (
        DeviceIdentityResolver(tmp_path / "two", DevicePackRegistry(()), (TwoProvider(),))
        .load(resolved)
        .authority
        is IdentityAuthority.CORROBORATED_PUBLIC
    )


def test_verified_oem_host_can_supply_name_without_community_corroboration(tmp_path, monkeypatch):
    monkeypatch.setattr(identity_module, "_public_host", lambda _host: True)

    class OfficialProvider:
        def search(self, _device):
            return (
                DeviceNameCandidate(
                    "Xiaomi 17 Pro Max",
                    "xiaomi-product-page",
                    "https://www.mi.com/global/product/xiaomi-17-pro-max/",
                    confidence=95,
                ),
            )

    resolver = DeviceIdentityResolver(tmp_path, DevicePackRegistry(()), (OfficialProvider(),))
    resolved = resolver.resolve_online(_device())
    assert resolved.marketing_name == "Xiaomi 17 Pro Max"
    assert resolver.load(resolved).authority is IdentityAuthority.OEM_OFFICIAL
