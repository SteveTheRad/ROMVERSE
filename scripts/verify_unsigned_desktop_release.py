from __future__ import annotations

import argparse
from pathlib import Path

from romverse.release import load_release_json, validate_release_manifest, verify_release_artifacts


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect an unsigned ROMVERSE Desktop candidate without granting release trust"
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--artifact-directory", required=True, type=Path)
    args = parser.parse_args()

    manifest = validate_release_manifest(load_release_json(args.manifest))
    count, total_bytes = verify_release_artifacts(manifest, args.artifact_directory)
    print(
        f"UNSIGNED ROMVERSE Desktop candidate verified structurally: "
        f"{manifest.release_id}; {count} artifact(s), {total_bytes} bytes"
    )
    print("No signing trust or update authority was granted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
