from __future__ import annotations

import argparse
import os
import stat
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from romverse.guardian.runtime_package import (
    RuntimePackageValidationError,
    create_signed_guardian_runtime_package,
    load_guardian_runtime_package,
    write_guardian_runtime_package,
)


def _load_private_key(path: Path, password: bytes | None) -> Ed25519PrivateKey:
    try:
        details = path.lstat()
    except OSError as exc:
        raise RuntimePackageValidationError("Runtime release private key is unavailable") from exc
    if (
        stat.S_ISLNK(details.st_mode)
        or not stat.S_ISREG(details.st_mode)
        or not 1 <= details.st_size <= 65_536
    ):
        raise RuntimePackageValidationError(
            "Runtime release private key must be one bounded regular file"
        )
    try:
        key = serialization.load_pem_private_key(path.read_bytes(), password=password)
    except (OSError, TypeError, ValueError) as exc:
        raise RuntimePackageValidationError(
            "Runtime release private key could not be loaded"
        ) from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise RuntimePackageValidationError("Runtime release private key must use Ed25519")
    return key


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sign a Guardian runtime manifest with an externally held release key"
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--private-key", required=True, type=Path)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--password-env")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    password: bytes | None = None
    if args.password_env:
        value = os.environ.get(args.password_env)
        if not value:
            raise RuntimePackageValidationError(
                "Runtime release private-key password environment variable is unavailable"
            )
        password = value.encode("utf-8")
    envelope = create_signed_guardian_runtime_package(
        load_guardian_runtime_package(args.manifest),
        _load_private_key(args.private_key, password),
        args.key_id,
    )
    write_guardian_runtime_package(args.output, envelope)
    print(f"ROMVERSE Guardian runtime manifest signed with key identity {args.key_id}")
    print("Signing the package does not enroll it or authorize a phone operation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
