from __future__ import annotations

import hashlib
import json
import re

USB_PAIRING_PACKAGE = "com.radforge.romverse.companion"
USB_PAIRING_COMPONENT = f"{USB_PAIRING_PACKAGE}/.MainActivity"
USB_PAIRING_ACTION = f"{USB_PAIRING_PACKAGE}.action.USB_PAIR"
USB_PAIRING_HOST_EXTRA = "romverse_link_host"
USB_PAIRING_FINGERPRINT_EXTRA = "romverse_link_fingerprint"
USB_PAIRING_CODE_EXTRA = "romverse_link_code"

_SERIAL = re.compile(r"[A-Za-z0-9._:-]{1,128}")
_FINGERPRINT = re.compile(r"[0-9a-f]{64}")
_CODE = re.compile(r"[0-9]{6}")


def validate_usb_pairing_values(
    serial: str,
    port: int,
    certificate_sha256: str,
    pairing_code: str,
) -> tuple[str, int, str, str]:
    normalized_fingerprint = certificate_sha256.strip().casefold()
    normalized_code = pairing_code.replace(" ", "")
    if not _SERIAL.fullmatch(serial):
        raise ValueError("USB pairing requires one exact bounded Android device serial")
    if port not in range(1, 65_536):
        raise ValueError("USB pairing requires a valid local Link port")
    if not _FINGERPRINT.fullmatch(normalized_fingerprint):
        raise ValueError("USB pairing requires the complete Desktop certificate fingerprint")
    if not _CODE.fullmatch(normalized_code):
        raise ValueError("USB pairing requires one six-digit code")
    return serial, port, normalized_fingerprint, normalized_code


def usb_reverse_arguments(serial: str, port: int) -> tuple[str, ...]:
    _validate_serial_port(serial, port)
    endpoint = f"tcp:{port}"
    return ("-s", serial, "reverse", endpoint, endpoint)


def usb_launch_arguments(
    serial: str,
    port: int,
    certificate_sha256: str,
    pairing_code: str,
) -> tuple[str, ...]:
    _, _, fingerprint, code = validate_usb_pairing_values(
        serial,
        port,
        certificate_sha256,
        pairing_code,
    )
    return (
        "-s",
        serial,
        "shell",
        "am",
        "start",
        "-W",
        "-f",
        "0x20000000",
        "-a",
        USB_PAIRING_ACTION,
        "-n",
        USB_PAIRING_COMPONENT,
        "--es",
        USB_PAIRING_HOST_EXTRA,
        f"127.0.0.1:{port}",
        "--es",
        USB_PAIRING_FINGERPRINT_EXTRA,
        fingerprint,
        "--es",
        USB_PAIRING_CODE_EXTRA,
        code,
    )


def usb_reverse_remove_arguments(serial: str, port: int) -> tuple[str, ...]:
    _validate_serial_port(serial, port)
    return ("-s", serial, "reverse", "--remove", f"tcp:{port}")


def usb_operation_digest(operation_id: str, arguments: tuple[str, ...]) -> str:
    encoded = json.dumps(
        {"operation_id": operation_id, "arguments": arguments},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_serial_port(serial: str, port: int) -> None:
    if not _SERIAL.fullmatch(serial):
        raise ValueError("USB pairing requires one exact bounded Android device serial")
    if port not in range(1, 65_536):
        raise ValueError("USB pairing requires a valid local Link port")
