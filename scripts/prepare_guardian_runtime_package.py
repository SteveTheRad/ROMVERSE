from __future__ import annotations

import argparse
import stat
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from romverse.guardian.runtime_package import (
    RUNTIME_PLATFORMS,
    RuntimePackageValidationError,
    build_guardian_runtime_package_manifest,
    write_guardian_runtime_package,
)


def _load_public_key(path: Path) -> Ed25519PublicKey:
    try:
        details = path.lstat()
    except OSError as exc:
        raise RuntimePackageValidationError("Runtime signer public key is unavailable") from exc
    if (
        stat.S_ISLNK(details.st_mode)
        or not stat.S_ISREG(details.st_mode)
        or not 1 <= details.st_size <= 65_536
    ):
        raise RuntimePackageValidationError(
            "Runtime signer public key must be one bounded regular file"
        )
    try:
        key = serialization.load_pem_public_key(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise RuntimePackageValidationError(
            "Runtime signer public key could not be loaded"
        ) from exc
    if not isinstance(key, Ed25519PublicKey):
        raise RuntimePackageValidationError("Runtime signer public key must use Ed25519")
    return key


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare an unsigned, integrity-bound ROMVERSE Guardian runtime manifest"
    )
    parser.add_argument("--runtime-id", default="romverse.guardian-runtime")
    parser.add_argument("--runtime-version", required=True)
    parser.add_argument(
        "--created-at",
        default=datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    )
    parser.add_argument("--platform", choices=sorted(RUNTIME_PLATFORMS), required=True)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--runtime-signer-key-id", required=True)
    parser.add_argument("--runtime-public-key", required=True, type=Path)
    parser.add_argument("--adapter-id", required=True)
    parser.add_argument("--adapter-version", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    manifest = build_guardian_runtime_package_manifest(
        runtime_id=args.runtime_id,
        runtime_version=args.runtime_version,
        created_at=args.created_at,
        platform=args.platform,
        artifact_path=args.artifact,
        runtime_signer_key_id=args.runtime_signer_key_id,
        runtime_public_key=_load_public_key(args.runtime_public_key),
        adapter_id=args.adapter_id,
        adapter_version=args.adapter_version,
    )
    write_guardian_runtime_package(args.output, manifest)
    print(f"UNSIGNED ROMVERSE Guardian runtime manifest prepared: {args.output}")
    print("It grants no execution authority and contains no private signing key.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
