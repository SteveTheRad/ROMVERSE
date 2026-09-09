from __future__ import annotations

import argparse
import sys
from pathlib import Path


def pyinstaller_arguments(
    repository: Path, output_directory: Path, work_directory: Path
) -> list[str]:
    package_root = repository / "src" / "romverse"
    assets = package_root / "assets"
    asset_arguments = [
        f"--add-data={path}:romverse/assets/{path.relative_to(assets).parent.as_posix()}"
        for path in sorted(assets.rglob("*"))
        if path.is_file() and not path.is_symlink() and path.suffix not in {".py", ".pyc"}
    ]
    icon = assets / (
        "romverse-app-icon.ico" if sys.platform == "win32" else "romverse-app-icon.png"
    )
    return [
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onedir",
        "--name=ROMVERSE",
        f"--icon={icon}",
        f"--paths={repository / 'src'}",
        # ``--collect-data=romverse`` resolves the importable package and can silently
        # collect stale assets from a different editable checkout. Bind data explicitly
        # to the same repository root as the entry point and source import path.
        *asset_arguments,
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
