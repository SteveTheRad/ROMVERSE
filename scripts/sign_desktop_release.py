from __future__ import annotations

import argparse
import os
import stat
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from romverse.release import (
    ReleaseValidationError,
    create_signed_release_envelope,
    load_release_json,
    write_release_json,
)


def _load_private_key(path: Path, password: bytes | None) -> Ed25519PrivateKey:
    try:
        details = path.lstat()
    except OSError as exc:
        raise ReleaseValidationError("Release private key is unavailable") from exc
    if (
        stat.S_ISLNK(details.st_mode)
        or not stat.S_ISREG(details.st_mode)
        or details.st_size > 65_536
    ):
        raise ReleaseValidationError("Release private key must be one bounded regular file")
    try:
        key = serialization.load_pem_private_key(path.read_bytes(), password=password)
    except (OSError, TypeError, ValueError) as exc:
        raise ReleaseValidationError("Release private key could not be loaded") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise ReleaseValidationError("Release private key must use Ed25519")
    return key


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sign a ROMVERSE Desktop manifest with an externally held Ed25519 key"
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
            raise ReleaseValidationError("Private-key password environment variable is unavailable")
        password = value.encode("utf-8")
    manifest = load_release_json(args.manifest)
    private_key = _load_private_key(args.private_key, password)
    envelope = create_signed_release_envelope(manifest, private_key, args.key_id)
    write_release_json(args.output, envelope)
    print(f"ROMVERSE Desktop manifest signed with key identity {args.key_id}: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
