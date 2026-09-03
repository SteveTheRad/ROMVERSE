from __future__ import annotations

import argparse
import os
import stat
import subprocess
from pathlib import Path


def smoke_frozen_desktop(executable: Path, workspace: Path) -> None:
    try:
        details = executable.lstat()
    except OSError as exc:
        raise ValueError("Frozen ROMVERSE executable is unavailable") from exc
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode) or details.st_size < 1:
        raise ValueError("Frozen ROMVERSE executable must be one non-empty regular file")
    workspace.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.setdefault("QT_QPA_PLATFORM", "offscreen")
    completed = subprocess.run(
        [
            str(executable.resolve()),
            "--workspace",
            str(workspace.resolve()),
            "--skip-onboarding",
            "--release-smoke",
        ],
        check=False,
        env=environment,
        timeout=60,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Frozen ROMVERSE smoke failed with exit code {completed.returncode}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Open and cleanly close the frozen ROMVERSE Desktop release candidate"
    )
    parser.add_argument("executable", type=Path)
    parser.add_argument("workspace", type=Path)
    args = parser.parse_args()
    smoke_frozen_desktop(args.executable, args.workspace)
    print("Frozen ROMVERSE Desktop launch smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
