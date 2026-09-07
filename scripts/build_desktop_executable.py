from __future__ import annotations

import argparse
import os
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


def windows_build_path(path_value: str, system_root: Path) -> str:
    """Remove only non-system PATH entries that shadow Windows' ICU API shim."""

    system32 = (system_root / "System32").resolve()
    retained: list[str] = []
    for entry in path_value.split(";"):
        if not entry:
            continue
        directory = Path(entry)
        try:
            shadows_icu = (directory / "icuuc.dll").is_file()
            is_system32 = directory.resolve() == system32
        except OSError:
            shadows_icu = False
            is_system32 = False
        if shadows_icu and not is_system32:
            continue
        retained.append(entry)
    return ";".join(retained)


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
    original_path = os.environ.get("PATH", "")
    if sys.platform == "win32":
        system_root = Path(os.environ.get("SYSTEMROOT", r"C:\Windows"))
        os.environ["PATH"] = windows_build_path(original_path, system_root)
    try:
        PyInstaller.__main__.run(
            pyinstaller_arguments(
                repository,
                args.output_directory.resolve(),
                args.work_directory.resolve(),
            )
        )
    finally:
        os.environ["PATH"] = original_path
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
