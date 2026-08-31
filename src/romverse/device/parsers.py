from __future__ import annotations

import re

from romverse.device.models import DeviceState, MemoryInfo, StorageInfo


def parse_adb_devices(output: str) -> list[dict[str, str]]:
    devices: list[dict[str, str]] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("List of devices") or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        details = {"serial": parts[0], "state": parts[1]}
        for token in parts[2:]:
            if ":" in token:
                key, value = token.split(":", 1)
                details[key] = value
        devices.append(details)
    return devices


def coerce_device_state(value: str) -> DeviceState:
    try:
        return DeviceState(value)
    except ValueError:
        return DeviceState.UNKNOWN


def parse_getprop(output: str) -> dict[str, str]:
    return {
        match.group(1): match.group(2)
        for line in output.splitlines()
        if (match := re.match(r"^\[([^]]+)]\s*:\s*\[(.*)]$", line.strip()))
    }


def parse_uptime(output: str) -> int | None:
    try:
        seconds = float(output.strip().split(maxsplit=1)[0])
    except (ValueError, IndexError):
        return None
    if seconds < 0 or seconds > 10 * 365 * 24 * 60 * 60:
        return None
    return int(seconds)


def parse_battery(output: str) -> tuple[int | None, str, float | None]:
    values: dict[str, str] = {}
    for line in output.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip()
    level = _to_int(values.get("level"))
    status = {1: "Unknown", 2: "Charging", 3: "Discharging", 4: "Not charging", 5: "Full"}.get(
        _to_int(values.get("status")), "Unknown"
    )
    temperature = _to_int(values.get("temperature"))
    return level, status, temperature / 10 if temperature is not None else None


def parse_storage(output: str) -> StorageInfo:
    lines = [line.split() for line in output.splitlines() if line.strip()]
    for columns in reversed(lines):
        # Newer Android releases may report the same data volume mounted at
        # /data/user/0 rather than exposing a literal /data row.
        if len(columns) >= 5 and columns[-1].startswith("/data"):
            try:
                return StorageInfo(
                    total_bytes=int(columns[1]) * 1024,
                    used_bytes=int(columns[2]) * 1024,
                    available_bytes=int(columns[3]) * 1024,
                    percent_used=int(columns[4].rstrip("%")),
                )
            except (ValueError, IndexError):
                break
    return StorageInfo()


def parse_memory(output: str) -> MemoryInfo:
    values: dict[str, int] = {}
    for line in output.splitlines():
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        match = re.search(r"(\d+)", raw_value)
        if match:
            values[key.strip()] = int(match.group(1)) * 1024
    total = values.get("MemTotal")
    available = values.get("MemAvailable") or values.get("MemFree")
    if not total or available is None:
        return MemoryInfo()
    used = max(0, total - available)
    return MemoryInfo(total, available, round(used * 100 / total))


def _to_int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None
