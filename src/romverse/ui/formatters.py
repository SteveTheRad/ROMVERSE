from __future__ import annotations


def human_bytes(value: int | None) -> str:
    if value is None:
        return "Unavailable"
    amount = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if amount < 1024 or unit == "TB":
            return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024
    return "Unavailable"


def yes_no_unknown(value: bool | None, yes: str = "Yes", no: str = "No") -> str:
    return "Unknown" if value is None else yes if value else no
