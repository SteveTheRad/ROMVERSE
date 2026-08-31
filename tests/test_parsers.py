from romverse.device.parsers import (
    parse_adb_devices,
    parse_battery,
    parse_getprop,
    parse_memory,
    parse_storage,
    parse_uptime,
)


def test_parse_devices_including_unauthorized():
    output = """List of devices attached
ABC123 device usb:1-2 product:foo model:Pixel_8 device:shiba transport_id:1
XYZ999 unauthorized usb:2-1 transport_id:2
"""
    devices = parse_adb_devices(output)
    assert devices[0]["model"] == "Pixel_8"
    assert devices[0]["device"] == "shiba"
    assert devices[1]["state"] == "unauthorized"


def test_parse_getprop_and_battery():
    props = parse_getprop("[ro.product.model]: [Example Phone]\n[ro.build.version.release]: [15]\n")
    assert props["ro.product.model"] == "Example Phone"
    level, status, temperature = parse_battery("level: 81\nstatus: 2\ntemperature: 325\n")
    assert (level, status, temperature) == (81, "Charging", 32.5)


def test_parse_uptime_is_bounded_and_never_invents_a_value():
    assert parse_uptime("1234.50 987.00\n") == 1234
    assert parse_uptime("not uptime") is None
    assert parse_uptime("-1 0") is None


def test_parse_storage_kilobytes():
    storage = parse_storage(
        "Filesystem 1K-blocks Used Available Use% Mounted on\n/dev/block/dm-8 100000 42000 58000 42% /data\n"
    )
    assert storage.total_bytes == 102_400_000
    assert storage.percent_used == 42


def test_parse_storage_modern_android_data_mount():
    storage = parse_storage(
        "Filesystem 1K-blocks Used Available Use% Mounted on\n"
        "/dev/block/dm-62 500367340 25386164 474850104 6% /data/user/0\n"
    )
    assert storage.available_bytes == 474850104 * 1024
    assert storage.percent_used == 6


def test_parse_android_meminfo() -> None:
    memory = parse_memory("MemTotal:       24576000 kB\nMemAvailable:   16711680 kB\n")
    assert memory.total_bytes == 24576000 * 1024
    assert memory.available_bytes == 16711680 * 1024
    assert memory.percent_used == 32
