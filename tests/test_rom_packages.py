from romverse.rom.packages import inventory_apks


def test_inventory_apks_is_read_only_and_hashed(tmp_path):
    (tmp_path / "system.apk").write_bytes(b"apk")
    assert inventory_apks(tmp_path)[0].name == "system"
    assert len(inventory_apks(tmp_path)[0].sha256) == 64
