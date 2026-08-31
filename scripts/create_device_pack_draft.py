#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from romverse.device_packs.drafts import DevicePackDraftService


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Create a content-addressed, non-activating exact-model Device Pack draft "
            "from reviewed source metadata."
        )
    )
    parser.add_argument("request", type=Path, help="UTF-8 JSON draft request")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("device_pack_drafts"),
        help="Directory for the review-only draft (default: device_pack_drafts)",
    )
    args = parser.parse_args()
    service = DevicePackDraftService()
    exported = service.export(service.load_request(args.request), args.output_dir)
    print(
        f"created {exported.output_path}  •  SHA-256 {exported.sha256}  •  "
        "publication status: draft  •  execution authority: none"
    )


if __name__ == "__main__":
    main()
