from __future__ import annotations

import argparse
from pathlib import Path

from romverse.guardian.runtime_package import (
    RUNTIME_PLATFORMS,
    load_guardian_runtime_package,
    load_guardian_runtime_public_key,
    verify_guardian_runtime_package,
)


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
        release_public_key=load_guardian_runtime_public_key(args.release_public_key),
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
