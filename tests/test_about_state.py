from __future__ import annotations

import json
import os
import stat

import pytest

from romverse.ui.about_state import OriginDiscoveryError, OriginDiscoveryStore


def test_origin_discovery_store_round_trips_private_strict_state(tmp_path) -> None:
    store = OriginDiscoveryStore(tmp_path)
    assert not store.load()

    store.discover()

    assert store.load()
    assert json.loads(store.path.read_text(encoding="utf-8")) == {
        "award": "beyond-the-verse",
        "discovered": True,
        "format": "romverse.about.origin",
        "schema_version": 1,
    }
    assert stat.S_IMODE(store.directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600


def test_origin_discovery_store_rejects_extra_fields_oversize_and_links(tmp_path) -> None:
    store = OriginDiscoveryStore(tmp_path)
    store.discover()
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    payload["xp"] = 1000
    store.path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(OriginDiscoveryError, match="fields are invalid"):
        store.load()

    store.path.write_bytes(b" " * (store.MAX_BYTES + 1))
    with pytest.raises(OriginDiscoveryError, match="size limit"):
        store.load()

    store.path.unlink()
    outside = tmp_path / "outside.romverse"
    outside.write_text("preserve me", encoding="utf-8")
    store.path.symlink_to(outside)
    with pytest.raises(OriginDiscoveryError, match="regular file"):
        store.discover()
    assert os.path.islink(store.path)
    assert outside.read_text(encoding="utf-8") == "preserve me"
