from __future__ import annotations

import argparse
import stat
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from romverse.guardian.runtime_package import (
    RUNTIME_PLATFORMS,
    RuntimePackageValidationError,
    load_guardian_runtime_package,
    verify_guardian_runtime_package,
)


def _load_public_key(path: Path) -> Ed25519PublicKey:
    try:
        details = path.lstat()
    except OSError as exc:
        raise RuntimePackageValidationError("Runtime release public key is unavailable") from exc
    if (
        stat.S_ISLNK(details.st_mode)
        or not stat.S_ISREG(details.st_mode)
        or not 1 <= details.st_size <= 65_536
    ):
        raise RuntimePackageValidationError(
            "Runtime release public key must be one bounded regular file"
        )
    try:
        key = serialization.load_pem_public_key(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise RuntimePackageValidationError(
            "Runtime release public key could not be loaded"
        ) from exc
    if not isinstance(key, Ed25519PublicKey):
        raise RuntimePackageValidationError("Runtime release public key must use Ed25519")
    return key


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify a release-signed Guardian runtime manifest and exact artifact"
    )
    parser.add_argument("envelope", type=Path)
    parser.add_argument("--release-public-key", required=True, type=Path)
    parser.add_argument("--release-key-id", required=True)
    parser.add_argument("--package-directory", required=True, type=Path)
    parser.add_argument("--platform", choices=sorted(RUNTIME_PLATFORMS), required=True)
    args = parser.parse_args()

    verified = verify_guardian_runtime_package(
        envelope=load_guardian_runtime_package(args.envelope),
        release_public_key=_load_public_key(args.release_public_key),
        expected_release_key_id=args.release_key_id,
        package_directory=args.package_directory,
        expected_platform=args.platform,
    )
    print(
        f"ROMVERSE Guardian runtime package verified: {verified.manifest.runtime_id} "
        f"{verified.manifest.runtime_version}; artifact "
        f"{verified.manifest.artifact.sha256}; execution authority none"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
