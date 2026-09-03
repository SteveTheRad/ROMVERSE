from __future__ import annotations

import hashlib
import json
import os
import stat
from contextlib import suppress
from pathlib import Path
from uuid import uuid4


class LocalStoreError(OSError):
    """A local evidence file failed a bounded filesystem or JSON contract."""


class LocalStoreConflictError(LocalStoreError):
    """An exclusive evidence record already exists and must not be replaced."""


def atomic_write_json(
    path: Path,
    payload: dict[str, object],
    *,
    boundary: Path,
    maximum_bytes: int,
) -> None:
    encoded = (
        json.dumps(
            payload,
            ensure_ascii=True,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    if not 0 < len(encoded) <= maximum_bytes:
        raise LocalStoreError("JSON evidence exceeds its size boundary")
    atomic_write_bytes(path, encoded, boundary=boundary, maximum_bytes=maximum_bytes)


def atomic_write_bytes(
    path: Path,
    payload: bytes,
    *,
    boundary: Path,
    maximum_bytes: int,
) -> None:
    """Atomically persist bounded opaque evidence as a private regular file."""

    if not isinstance(payload, bytes) or not 0 < len(payload) <= maximum_bytes:
        raise LocalStoreError("Binary evidence exceeds its size boundary")
    if os.name == "nt":
        _atomic_write_bytes_portable(path, payload, boundary=boundary)
        return
    parent_fd = _open_parent(path, boundary=boundary, create=True)
    temporary_name = f".{path.name}.{uuid4().hex}.tmp"
    try:
        _reject_non_regular_target(parent_fd, path.name)
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary_name, flags, 0o600, dir_fd=parent_fd)
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            with suppress(OSError):
                os.close(descriptor)
            raise
        os.replace(
            temporary_name,
            path.name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        os.fsync(parent_fd)
    except (OSError, TypeError, ValueError) as exc:
        raise LocalStoreError(f"Local evidence write failed: {exc}") from exc
    finally:
        with suppress(OSError):
            os.unlink(temporary_name, dir_fd=parent_fd)
        os.close(parent_fd)


def exclusive_create_json(
    path: Path,
    payload: dict[str, object],
    *,
    boundary: Path,
    maximum_bytes: int,
) -> None:
    """Persist one bounded JSON object exactly once without replacing a prior record."""

    encoded = (
        json.dumps(
            payload,
            ensure_ascii=True,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    if not 0 < len(encoded) <= maximum_bytes:
        raise LocalStoreError("JSON evidence exceeds its size boundary")
    exclusive_create_bytes(
        path,
        encoded,
        boundary=boundary,
        maximum_bytes=maximum_bytes,
    )


def exclusive_create_bytes(
    path: Path,
    payload: bytes,
    *,
    boundary: Path,
    maximum_bytes: int,
) -> None:
    """Create a private regular file once; an existing entry is never replaced."""

    if not isinstance(payload, bytes) or not 0 < len(payload) <= maximum_bytes:
        raise LocalStoreError("Binary evidence exceeds its size boundary")
    if os.name == "nt":
        _exclusive_create_bytes_portable(path, payload, boundary=boundary)
        return
    parent_fd = _open_parent(path, boundary=boundary, create=True)
    created = False
    try:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path.name, flags, 0o600, dir_fd=parent_fd)
        except FileExistsError as exc:
            raise LocalStoreConflictError("Exclusive local evidence already exists") from exc
        created = True
        try:
            details = os.fstat(descriptor)
            if not stat.S_ISREG(details.st_mode):
                raise LocalStoreError("Exclusive local evidence is not a regular file")
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            with suppress(OSError):
                os.close(descriptor)
            raise
        os.fsync(parent_fd)
    except (OSError, TypeError, ValueError) as exc:
        if created:
            with suppress(OSError):
                os.unlink(path.name, dir_fd=parent_fd)
                os.fsync(parent_fd)
        if isinstance(exc, LocalStoreError):
            raise
        raise LocalStoreError(f"Exclusive local evidence write failed: {exc}") from exc
    finally:
        os.close(parent_fd)


def read_json_object(
    path: Path,
    *,
    boundary: Path,
    maximum_bytes: int,
) -> dict[str, object]:
    if os.name == "nt":
        return _read_json_object_portable(
            path,
            boundary=boundary,
            maximum_bytes=maximum_bytes,
        )
    parent_fd = _open_parent(path, boundary=boundary, create=False)
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path.name, flags, dir_fd=parent_fd)
        try:
            details = os.fstat(descriptor)
            if not stat.S_ISREG(details.st_mode):
                raise LocalStoreError("JSON evidence is not a regular file")
            if not 0 < details.st_size <= maximum_bytes:
                raise LocalStoreError("JSON evidence exceeds its size boundary")
            with os.fdopen(descriptor, "rb", closefd=True) as stream:
                encoded = stream.read(maximum_bytes + 1)
        except Exception:
            with suppress(OSError):
                os.close(descriptor)
            raise
        if len(encoded) > maximum_bytes:
            raise LocalStoreError("JSON evidence exceeds its size boundary")
        payload = json.loads(encoded.decode("utf-8"))
        if not isinstance(payload, dict):
            raise LocalStoreError("JSON evidence must be an object")
        return payload
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        if isinstance(exc, LocalStoreError):
            raise
        raise LocalStoreError(f"Local evidence read failed: {exc}") from exc
    finally:
        os.close(parent_fd)


def read_regular_bytes(
    path: Path,
    *,
    boundary: Path,
    maximum_bytes: int,
) -> bytes:
    """Read one bounded regular file without following links inside a trusted root."""

    if maximum_bytes < 1:
        raise ValueError("maximum_bytes must be positive")
    if os.name == "nt":
        parent = _validated_directory_path(path.parent, boundary=boundary, create=False)
        safe_path = parent / path.name
        try:
            details = safe_path.lstat()
            if not stat.S_ISREG(details.st_mode) or not 0 < details.st_size <= maximum_bytes:
                raise LocalStoreError("Binary evidence exceeds its size boundary")
            payload = safe_path.read_bytes()
        except OSError as exc:
            raise LocalStoreError(f"Local evidence read failed: {exc}") from exc
        if not 0 < len(payload) <= maximum_bytes:
            raise LocalStoreError("Binary evidence exceeds its size boundary")
        return payload

    parent_fd = _open_parent(path, boundary=boundary, create=False)
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path.name, flags, dir_fd=parent_fd)
        try:
            details = os.fstat(descriptor)
            if not stat.S_ISREG(details.st_mode):
                raise LocalStoreError("Binary evidence is not a regular file")
            if not 0 < details.st_size <= maximum_bytes:
                raise LocalStoreError("Binary evidence exceeds its size boundary")
            with os.fdopen(descriptor, "rb", closefd=True) as stream:
                payload = stream.read(maximum_bytes + 1)
        except Exception:
            with suppress(OSError):
                os.close(descriptor)
            raise
        if not 0 < len(payload) <= maximum_bytes:
            raise LocalStoreError("Binary evidence exceeds its size boundary")
        return payload
    except OSError as exc:
        if isinstance(exc, LocalStoreError):
            raise
        raise LocalStoreError(f"Local evidence read failed: {exc}") from exc
    finally:
        os.close(parent_fd)


def sha256_regular_file(
    path: Path,
    *,
    boundary: Path,
    maximum_bytes: int,
) -> tuple[str, int]:
    """Hash one stable regular file through a boundary-anchored descriptor."""

    if maximum_bytes < 1:
        raise ValueError("maximum_bytes must be positive")
    if os.name == "nt":
        parent = _validated_directory_path(path.parent, boundary=boundary, create=False)
        target: str | Path = parent / path.name
        directory_descriptor: int | None = None
    else:
        directory_descriptor = _open_parent(path, boundary=boundary, create=False)
        target = path.name
    try:
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        if directory_descriptor is None:
            descriptor = os.open(target, flags)
        else:
            descriptor = os.open(target, flags, dir_fd=directory_descriptor)
        try:
            with os.fdopen(descriptor, "rb", closefd=True) as stream:
                opened = os.fstat(stream.fileno())
                current = _stat_without_links(target, directory_descriptor)
                _validate_opened_regular_file(opened, current, maximum_bytes)
                digest = hashlib.sha256()
                read_bytes = 0
                while chunk := stream.read(1024 * 1024):
                    read_bytes += len(chunk)
                    if read_bytes > maximum_bytes:
                        raise LocalStoreError("Binary evidence exceeds its size boundary")
                    digest.update(chunk)
                final = os.fstat(stream.fileno())
                current = _stat_without_links(target, directory_descriptor)
                if (
                    read_bytes != opened.st_size
                    or final.st_size != opened.st_size
                    or final.st_mtime_ns != opened.st_mtime_ns
                    or not os.path.samestat(opened, final)
                    or not os.path.samestat(opened, current)
                ):
                    raise LocalStoreError("Binary evidence changed while it was being verified")
        except Exception:
            with suppress(OSError):
                os.close(descriptor)
            raise
        return digest.hexdigest(), read_bytes
    except OSError as exc:
        if isinstance(exc, LocalStoreError):
            raise
        raise LocalStoreError(f"Local evidence hash failed: {exc}") from exc
    finally:
        if directory_descriptor is not None:
            os.close(directory_descriptor)


def bounded_regular_files(
    directory: Path,
    pattern_suffix: str,
    *,
    boundary: Path,
    maximum_entries: int,
) -> tuple[Path, ...]:
    if maximum_entries < 1:
        raise ValueError("maximum_entries must be positive")
    if os.name == "nt":
        safe_directory = _validated_directory_path(
            directory,
            boundary=boundary,
            create=False,
        )
        names: list[str] = []
        with os.scandir(safe_directory) as entries:
            for entry in entries:
                if len(names) >= maximum_entries:
                    break
                try:
                    if entry.name.endswith(pattern_suffix) and entry.is_file(follow_symlinks=False):
                        names.append(entry.name)
                except OSError:
                    continue
        return tuple(safe_directory / name for name in sorted(names))
    directory_fd = _open_directory(directory, boundary=boundary, create=False)
    try:
        names: list[str] = []
        with os.scandir(directory_fd) as entries:
            for entry in entries:
                if len(names) >= maximum_entries:
                    break
                try:
                    if entry.name.endswith(pattern_suffix) and entry.is_file(follow_symlinks=False):
                        names.append(entry.name)
                except OSError:
                    continue
        return tuple(directory / name for name in sorted(names))
    finally:
        os.close(directory_fd)


def ensure_private_directory(directory: Path, *, boundary: Path) -> Path:
    """Create and validate a private directory without following workspace links."""

    if os.name == "nt":
        safe = _validated_directory_path(directory, boundary=boundary, create=True)
        with suppress(PermissionError):
            safe.chmod(0o700)
        return safe
    descriptor = _open_directory(directory, boundary=boundary, create=True)
    try:
        with suppress(PermissionError):
            os.fchmod(descriptor, 0o700)
        return Path(os.path.abspath(directory))
    finally:
        os.close(descriptor)


def remove_regular_file(
    path: Path,
    *,
    boundary: Path,
    missing_ok: bool = True,
) -> bool:
    """Remove one contained regular file without following directory or target links."""

    if os.name == "nt":
        try:
            parent = _validated_directory_path(path.parent, boundary=boundary, create=False)
            target = parent / path.name
            try:
                details = target.lstat()
            except FileNotFoundError:
                if missing_ok:
                    return False
                raise LocalStoreError("Local evidence file is unavailable") from None
            if not stat.S_ISREG(details.st_mode):
                raise LocalStoreError("Local evidence target is not a regular file")
            target.unlink()
            return True
        except (OSError, TypeError, ValueError) as exc:
            if isinstance(exc, LocalStoreError):
                raise
            raise LocalStoreError(f"Local evidence removal failed: {exc}") from exc

    parent_fd = _open_parent(path, boundary=boundary, create=False)
    try:
        try:
            details = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            if missing_ok:
                return False
            raise LocalStoreError("Local evidence file is unavailable") from None
        if not stat.S_ISREG(details.st_mode):
            raise LocalStoreError("Local evidence target is not a regular file")
        os.unlink(path.name, dir_fd=parent_fd)
        os.fsync(parent_fd)
        return True
    except (OSError, TypeError, ValueError) as exc:
        if isinstance(exc, LocalStoreError):
            raise
        raise LocalStoreError(f"Local evidence removal failed: {exc}") from exc
    finally:
        os.close(parent_fd)


def _reject_non_regular_target(parent_fd: int, name: str) -> None:
    try:
        details = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if not stat.S_ISREG(details.st_mode):
        raise LocalStoreError("Local evidence target is not a regular file")


def _stat_without_links(target: str | Path, directory_descriptor: int | None) -> os.stat_result:
    if directory_descriptor is None:
        return os.stat(target, follow_symlinks=False)
    return os.stat(
        target,
        dir_fd=directory_descriptor,
        follow_symlinks=False,
    )


def _validate_opened_regular_file(
    opened: os.stat_result,
    current: os.stat_result,
    maximum_bytes: int,
) -> None:
    if (
        not stat.S_ISREG(opened.st_mode)
        or not stat.S_ISREG(current.st_mode)
        or not os.path.samestat(opened, current)
    ):
        raise LocalStoreError("Binary evidence is not a stable regular file")
    if not 0 < opened.st_size <= maximum_bytes:
        raise LocalStoreError("Binary evidence exceeds its size boundary")


def _atomic_write_bytes_portable(path: Path, payload: bytes, *, boundary: Path) -> None:
    parent = _validated_directory_path(path.parent, boundary=boundary, create=True)
    target = parent / path.name
    temporary = parent / f".{path.name}.{uuid4().hex}.tmp"
    try:
        try:
            details = target.lstat()
        except FileNotFoundError:
            details = None
        if details is not None and not stat.S_ISREG(details.st_mode):
            raise LocalStoreError("Local evidence target is not a regular file")
        descriptor = os.open(
            temporary,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            with suppress(OSError):
                os.close(descriptor)
            raise
        os.replace(temporary, target)
        with suppress(PermissionError):
            target.chmod(0o600)
        with suppress(OSError):
            directory_fd = os.open(parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    except (OSError, TypeError, ValueError) as exc:
        if isinstance(exc, LocalStoreError):
            raise
        raise LocalStoreError(f"Local evidence write failed: {exc}") from exc
    finally:
        with suppress(OSError):
            temporary.unlink(missing_ok=True)


def _exclusive_create_bytes_portable(path: Path, payload: bytes, *, boundary: Path) -> None:
    parent = _validated_directory_path(path.parent, boundary=boundary, create=True)
    target = parent / path.name
    created = False
    try:
        flags = (
            os.O_CREAT
            | os.O_EXCL
            | os.O_WRONLY
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            descriptor = os.open(target, flags, 0o600)
        except FileExistsError as exc:
            raise LocalStoreConflictError("Exclusive local evidence already exists") from exc
        created = True
        try:
            details = os.fstat(descriptor)
            if not stat.S_ISREG(details.st_mode):
                raise LocalStoreError("Exclusive local evidence is not a regular file")
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            with suppress(OSError):
                os.close(descriptor)
            raise
        with suppress(PermissionError):
            target.chmod(0o600)
        with suppress(OSError):
            directory_fd = os.open(parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    except (OSError, TypeError, ValueError) as exc:
        if created:
            with suppress(OSError):
                target.unlink(missing_ok=True)
        if isinstance(exc, LocalStoreError):
            raise
        raise LocalStoreError(f"Exclusive local evidence write failed: {exc}") from exc


def _read_json_object_portable(
    path: Path,
    *,
    boundary: Path,
    maximum_bytes: int,
) -> dict[str, object]:
    parent = _validated_directory_path(path.parent, boundary=boundary, create=False)
    target = parent / path.name
    try:
        details = target.lstat()
        if not stat.S_ISREG(details.st_mode):
            raise LocalStoreError("JSON evidence is not a regular file")
        if not 0 < details.st_size <= maximum_bytes:
            raise LocalStoreError("JSON evidence exceeds its size boundary")
        with target.open("rb") as stream:
            encoded = stream.read(maximum_bytes + 1)
        if len(encoded) > maximum_bytes:
            raise LocalStoreError("JSON evidence exceeds its size boundary")
        payload = json.loads(encoded.decode("utf-8"))
        if not isinstance(payload, dict):
            raise LocalStoreError("JSON evidence must be an object")
        return payload
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        if isinstance(exc, LocalStoreError):
            raise
        raise LocalStoreError(f"Local evidence read failed: {exc}") from exc


def _validated_directory_path(directory: Path, *, boundary: Path, create: bool) -> Path:
    root = boundary.resolve(strict=True)
    candidate = Path(os.path.abspath(directory))
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise LocalStoreError("Local evidence path escapes its workspace boundary") from exc
    if any(part in {"", ".", ".."} for part in relative.parts):
        raise LocalStoreError("Local evidence path is invalid")
    current = root
    for part in relative.parts:
        current /= part
        if create:
            with suppress(FileExistsError):
                current.mkdir(mode=0o700)
        try:
            details = current.lstat()
        except OSError as exc:
            raise LocalStoreError(
                f"Local evidence directory is unsafe or unavailable: {exc}"
            ) from exc
        is_junction = bool(getattr(current, "is_junction", lambda: False)())
        if not stat.S_ISDIR(details.st_mode) or current.is_symlink() or is_junction:
            raise LocalStoreError("Local evidence directory is unsafe or unavailable")
    return current


def _open_parent(path: Path, *, boundary: Path, create: bool) -> int:
    if not path.name or path.name in {".", ".."}:
        raise LocalStoreError("Local evidence filename is invalid")
    return _open_directory(path.parent, boundary=boundary, create=create)


def _open_directory(directory: Path, *, boundary: Path, create: bool) -> int:
    root = boundary.resolve(strict=True)
    candidate = Path(os.path.abspath(directory))
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise LocalStoreError("Local evidence path escapes its workspace boundary") from exc
    parts = relative.parts
    if any(part in {"", ".", ".."} for part in parts):
        raise LocalStoreError("Local evidence path is invalid")

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(root, flags)
    except OSError as exc:
        raise LocalStoreError(f"Workspace boundary is unavailable: {exc}") from exc
    try:
        for part in parts:
            if create:
                with suppress(FileExistsError):
                    os.mkdir(part, 0o700, dir_fd=descriptor)
            next_descriptor = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except OSError as exc:
        os.close(descriptor)
        raise LocalStoreError(f"Local evidence directory is unsafe or unavailable: {exc}") from exc
