from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path, PurePosixPath

REQUIRED_FILES = frozenset(
    {
        "romverse/app.py",
        "romverse/device/dna.py",
        "romverse/infrastructure/local_store.py",
        "romverse/infrastructure/provisioning.py",
        "romverse/intelligence/action_evidence.py",
        "romverse/repair/host.py",
        "romverse/rom/inspection.py",
        "romverse/ui/main_window.py",
        "romverse/ui/rom_studio.py",
        "romverse/assets/product-family.png",
        "romverse/assets/radforge-labs-official-logo-transparent.png",
        "romverse/assets/romverse-app-icon.png",
        "romverse/assets/romverse-mark.svg",
        "romverse/assets/device_pack_trust/index.json",
        "romverse/assets/device_packs/index.json",
    }
)
SOURCE_PACKAGE = Path(__file__).resolve().parents[1] / "src" / "romverse"


def source_runtime_files(source_package: Path = SOURCE_PACKAGE) -> dict[str, Path]:
    """Return every source-controlled module and runtime asset that the wheel must preserve."""

    expected: dict[str, Path] = {}
    for path in source_package.rglob("*"):
        if (
            not path.is_file()
            or path.is_symlink()
            or "__pycache__" in path.parts
            or path.suffix in {".pyc", ".pyo"}
        ):
            continue
        relative = path.relative_to(source_package).as_posix()
        if path.suffix == ".py" or relative.startswith("assets/"):
            expected[f"romverse/{relative}"] = path
    return expected


def verify_wheel(path: Path) -> tuple[int, int]:
    if not path.is_file() or path.suffix != ".whl":
        raise ValueError("Select one built ROMVERSE wheel")
    with zipfile.ZipFile(path) as archive:
        names = tuple(archive.namelist())
        members = set(names)
        unsafe = tuple(
            name
            for name in names
            if PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts
        )
        if unsafe:
            raise ValueError(f"Wheel contains unsafe paths: {', '.join(unsafe[:3])}")
        expected_runtime = source_runtime_files()
        missing = sorted((REQUIRED_FILES | expected_runtime.keys()) - members)
        if missing:
            raise ValueError(f"Wheel is missing required runtime files: {', '.join(missing)}")
        if any(name.endswith((".pyc", ".pyo")) or "/__pycache__/" in name for name in names):
            raise ValueError("Wheel contains generated Python cache files")
        changed = tuple(
            name
            for name, source in expected_runtime.items()
            if archive.read(name) != source.read_bytes()
        )
        if changed:
            raise ValueError(
                "Wheel runtime content differs from the source tree: " + ", ".join(changed[:3])
            )

        index_name = "romverse/assets/device_packs/index.json"
        index = json.loads(archive.read(index_name))
        if index.get("schema_version") != 1 or not isinstance(index.get("packs"), list):
            raise ValueError("Packaged Device Pack index is invalid")
        seen: set[str] = set()
        for entry in index["packs"]:
            if not isinstance(entry, dict):
                raise ValueError("Packaged Device Pack entry is invalid")
            filename = str(entry.get("file", ""))
            expected = str(entry.get("sha256", ""))
            if (
                not filename.endswith(".json")
                or "/" in filename
                or "\\" in filename
                or filename in seen
            ):
                raise ValueError(f"Packaged Device Pack filename is unsafe: {filename}")
            seen.add(filename)
            member = f"romverse/assets/device_packs/{filename}"
            if member not in members:
                raise ValueError(f"Indexed Device Pack is absent from wheel: {filename}")
            actual = hashlib.sha256(archive.read(member)).hexdigest()
            if actual != expected:
                raise ValueError(f"Packaged Device Pack failed SHA-256: {filename}")
        if len(seen) < 1:
            raise ValueError("Wheel contains no indexed Device Packs")
        return len(names), len(seen)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a built ROMVERSE wheel")
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    members, packs = verify_wheel(args.wheel.resolve())
    print(f"ROMVERSE wheel verified: {members} members, {packs} Device Packs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
