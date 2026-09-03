from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from romverse.release import build_release_manifest, write_release_json


def _artifact(value: str) -> tuple[str, str, str, Path]:
    try:
        artifact_id, platform, kind, raw_path = value.split(":", 3)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use ARTIFACT_ID:PLATFORM:KIND:PATH") from exc
    if not raw_path:
        raise argparse.ArgumentTypeError("artifact path is empty")
    return artifact_id, platform, kind, Path(raw_path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare an unsigned, integrity-bound ROMVERSE Desktop release manifest"
    )
    parser.add_argument("--version", required=True)
    parser.add_argument("--channel", default="release-candidate")
    parser.add_argument("--release-id", required=True)
    parser.add_argument(
        "--published-at",
        default=datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    )
    parser.add_argument("--artifact", action="append", required=True, type=_artifact)
    parser.add_argument("--rollback-version", default="")
    parser.add_argument("--rollback-artifact-id", default="")
    parser.add_argument(
        "--rollback-reason",
        default="No previously signed public ROMVERSE Desktop release is available.",
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    manifest = build_release_manifest(
        version=args.version,
        channel=args.channel,
        release_id=args.release_id,
        published_at=args.published_at,
        artifacts=args.artifact,
        rollback_version=args.rollback_version,
        rollback_artifact_id=args.rollback_artifact_id,
        rollback_reason=args.rollback_reason,
    )
    write_release_json(args.output, manifest)
    print(f"UNSIGNED ROMVERSE Desktop manifest prepared: {args.output}")
    print("It is not a trusted release until the offline Ed25519 signing step succeeds.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
