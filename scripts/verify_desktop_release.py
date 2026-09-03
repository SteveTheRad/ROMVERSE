from __future__ import annotations

import argparse
import stat
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from romverse.release import (
    ReleaseValidationError,
    load_release_json,
    verify_release_bundle,
)


def _load_public_key(path: Path) -> Ed25519PublicKey:
    try:
        details = path.lstat()
    except OSError as exc:
        raise ReleaseValidationError("Release public key is unavailable") from exc
    if (
        stat.S_ISLNK(details.st_mode)
        or not stat.S_ISREG(details.st_mode)
        or details.st_size > 65_536
    ):
        raise ReleaseValidationError("Release public key must be one bounded regular file")
    try:
        key = serialization.load_pem_public_key(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise ReleaseValidationError("Release public key could not be loaded") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise ReleaseValidationError("Release public key must use Ed25519")
    return key


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify a signed ROMVERSE Desktop release and every named artifact"
    )
    parser.add_argument("envelope", type=Path)
    parser.add_argument("--public-key", required=True, type=Path)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--artifact-directory", required=True, type=Path)
    args = parser.parse_args()

    result = verify_release_bundle(
        envelope=load_release_json(args.envelope),
        public_key=_load_public_key(args.public_key),
        expected_key_id=args.key_id,
        artifact_directory=args.artifact_directory,
    )
    print(
        f"ROMVERSE Desktop release verified: {result.manifest.release_id}; "
        f"{result.artifact_count} artifact(s), {result.artifact_bytes} bytes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
