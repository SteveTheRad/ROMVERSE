"""Platform-stable regular-file identity used at descriptor/path boundaries."""

from __future__ import annotations

import os


def stable_file_identity(info: os.stat_result) -> tuple[int, ...]:
    """Return fields that are stable between handle and path stat calls.

    CPython's Windows handle-stat and path-stat implementations can expose the
    same NTFS creation time with different sub-millisecond rounding. Device and
    file indexes still prove same-file identity; size and mtime retain the
    content-race guard. POSIX hosts keep the stricter ctime comparison.
    """

    stable = info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns
    return stable if os.name == "nt" else (*stable, info.st_ctime_ns)
