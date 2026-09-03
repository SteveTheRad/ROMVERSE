from __future__ import annotations

import argparse
import sys
from pathlib import Path


def pyinstaller_arguments(
    repository: Path, output_directory: Path, work_directory: Path
) -> list[str]:
    icon = (
        repository
        / "src"
        / "romverse"
        / "assets"
        / ("romverse-app-icon.ico" if sys.platform == "win32" else "romverse-app-icon.png")
    )
    return [
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onedir",
        "--name=ROMVERSE",
        f"--icon={icon}",
        f"--paths={repository / 'src'}",
        "--collect-data=romverse",
        "--collect-submodules=romverse",
        f"--distpath={output_directory}",
        f"--workpath={work_directory / 'work'}",
        f"--specpath={work_directory / 'spec'}",
        str(repository / "src" / "romverse" / "__main__.py"),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the self-contained ROMVERSE Desktop application directory"
    )
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--work-directory", required=True, type=Path)
    args = parser.parse_args()

    repository = Path(__file__).resolve().parents[1]
    try:
        import PyInstaller.__main__
    except ImportError as exc:
        raise RuntimeError("Install the release build dependencies before packaging") from exc
    PyInstaller.__main__.run(
        pyinstaller_arguments(
            repository,
            args.output_directory.resolve(),
            args.work_directory.resolve(),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
