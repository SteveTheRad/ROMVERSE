from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


class CommandRunner(Protocol):
    def run(
        self,
        args: Sequence[str],
        timeout: float = 10,
        cwd: Path | None = None,
    ) -> CommandResult: ...


class SubprocessRunner:
    """Shell-free, bounded subprocess adapter."""

    def run(
        self,
        args: Sequence[str],
        timeout: float = 10,
        cwd: Path | None = None,
    ) -> CommandResult:
        safe_args = tuple(str(part) for part in args)
        try:
            completed = subprocess.run(
                safe_args,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=timeout,
                check=False,
                shell=False,
                cwd=str(cwd) if cwd is not None else None,
            )
            return CommandResult(
                safe_args,
                completed.returncode,
                completed.stdout[-2_000_000:],
                completed.stderr[-200_000:],
            )
        except subprocess.TimeoutExpired as exc:
            stdout = (
                exc.stdout.decode(errors="replace")
                if isinstance(exc.stdout, bytes)
                else exc.stdout or ""
            )
            stderr = (
                exc.stderr.decode(errors="replace")
                if isinstance(exc.stderr, bytes)
                else exc.stderr or ""
            )
            return CommandResult(safe_args, 124, stdout, stderr, timed_out=True)
        except OSError as exc:
            return CommandResult(safe_args, 127, "", str(exc))
