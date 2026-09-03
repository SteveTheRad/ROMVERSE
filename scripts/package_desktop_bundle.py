from __future__ import annotations

import argparse
import hashlib
import os
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

MAX_BUNDLE_FILES = 20_000
MAX_BUNDLE_BYTES = 4_294_967_296
PLATFORMS = frozenset({"linux-x86_64", "windows-x86_64"})


def _bundle_files(root: Path, platform: str) -> tuple[tuple[Path, Path], ...]:
    if platform not in PLATFORMS:
        raise ValueError("Unsupported ROMVERSE Desktop bundle platform")
    try:
        root_details = root.lstat()
    except OSError as exc:
        raise ValueError("ROMVERSE Desktop bundle directory is unavailable") from exc
    if stat.S_ISLNK(root_details.st_mode) or not stat.S_ISDIR(root_details.st_mode):
        raise ValueError("ROMVERSE Desktop bundle must be one regular directory, not a link")
    files: list[tuple[Path, Path]] = []
    total_bytes = 0
    for path in sorted(root.rglob("*")):
        details = path.lstat()
        if stat.S_ISLNK(details.st_mode):
            try:
                resolved = path.resolve(strict=True)
                resolved_details = resolved.stat()
            except OSError as exc:
                raise ValueError("ROMVERSE Desktop bundle contains a broken link") from exc
            if not resolved.is_relative_to(root) or not stat.S_ISREG(resolved_details.st_mode):
                raise ValueError("ROMVERSE Desktop bundle link escapes its regular-file boundary")
            files.append((path, resolved))
            total_bytes += resolved_details.st_size
            if len(files) > MAX_BUNDLE_FILES or total_bytes > MAX_BUNDLE_BYTES:
                raise ValueError("ROMVERSE Desktop bundle exceeds the safe packaging limit")
            continue
        if stat.S_ISDIR(details.st_mode):
            continue
        if not stat.S_ISREG(details.st_mode):
            raise ValueError("ROMVERSE Desktop bundle contains a non-regular file")
        files.append((path, path))
        total_bytes += details.st_size
        if len(files) > MAX_BUNDLE_FILES or total_bytes > MAX_BUNDLE_BYTES:
            raise ValueError("ROMVERSE Desktop bundle exceeds the safe packaging limit")
    executable = root / ("ROMVERSE.exe" if platform == "windows-x86_64" else "ROMVERSE")
    if (
        executable not in {archive_path for archive_path, _source_path in files}
        or executable.stat().st_size < 1
    ):
        raise ValueError("ROMVERSE Desktop bundle is missing its platform executable")
    return tuple(files)


def package_bundle(root: Path, platform: str, output: Path) -> tuple[str, int, int]:
    bundle_root = root.expanduser().resolve()
    output_path = output.expanduser().resolve()
    if output_path.suffix.casefold() != ".zip":
        raise ValueError("ROMVERSE Desktop bundle output must be a ZIP archive")
    if output_path.is_relative_to(bundle_root):
        raise ValueError("ROMVERSE Desktop bundle output must be outside the source directory")
    if output_path.is_symlink():
        raise ValueError("ROMVERSE Desktop bundle output must not replace a link")
    files = _bundle_files(bundle_root, platform)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.", suffix=".zip", dir=output_path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            for archive_path, source_path in files:
                relative = archive_path.relative_to(bundle_root)
                archive.write(
                    source_path, (PurePosixPath("ROMVERSE") / relative.as_posix()).as_posix()
                )
        temporary.chmod(0o644)
        os.replace(temporary, output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return verify_bundle_archive(output_path, platform)


def verify_bundle_archive(path: Path, platform: str) -> tuple[str, int, int]:
    if platform not in PLATFORMS:
        raise ValueError("Unsupported ROMVERSE Desktop bundle platform")
    if path.is_symlink() or not path.is_file():
        raise ValueError("ROMVERSE Desktop bundle archive must be one regular file")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if not 1 <= len(members) <= MAX_BUNDLE_FILES:
            raise ValueError("ROMVERSE Desktop bundle archive has an invalid file count")
        seen: set[str] = set()
        total_bytes = 0
        for member in members:
            member_path = PurePosixPath(member.filename)
            mode = member.external_attr >> 16
            if (
                member.filename in seen
                or member_path.is_absolute()
                or not member_path.parts
                or member_path.parts[0] != "ROMVERSE"
                or ".." in member_path.parts
                or stat.S_ISLNK(mode)
                or member.is_dir()
            ):
                raise ValueError("ROMVERSE Desktop bundle archive contains an unsafe member")
            seen.add(member.filename)
            total_bytes += member.file_size
            if total_bytes > MAX_BUNDLE_BYTES:
                raise ValueError("ROMVERSE Desktop bundle archive exceeds the safe expanded limit")
        executable = (
            "ROMVERSE/ROMVERSE.exe" if platform == "windows-x86_64" else "ROMVERSE/ROMVERSE"
        )
        if executable not in seen:
            raise ValueError("ROMVERSE Desktop bundle archive is missing its executable")
        corrupt = archive.testzip()
        if corrupt is not None:
            raise ValueError(f"ROMVERSE Desktop bundle failed CRC validation: {corrupt}")
    return digest.hexdigest(), len(members), total_bytes


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Package and verify a self-contained ROMVERSE Desktop application directory"
    )
    parser.add_argument("bundle_directory", type=Path)
    parser.add_argument("--platform", choices=sorted(PLATFORMS), required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    digest, members, total_bytes = package_bundle(args.bundle_directory, args.platform, args.output)
    print(
        f"ROMVERSE Desktop {args.platform} bundle verified: {members} files, "
        f"{total_bytes} expanded bytes, SHA-256 {digest}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
