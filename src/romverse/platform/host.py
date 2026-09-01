from __future__ import annotations

import os
import platform
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


class HostPlatform(Protocol):
    name: str
    distribution_id: str

    def data_dir(self) -> Path: ...
    def config_dir(self) -> Path: ...
    def default_workspace(self) -> Path: ...
    def find_tool(self, name: str) -> Path | None: ...


def _linux_distribution_id() -> str:
    try:
        value = platform.freedesktop_os_release().get("ID", "")
    except OSError:
        return ""
    return str(value).casefold().strip()[:64]


@dataclass(frozen=True, slots=True)
class LinuxHost:
    name: str = "Linux"
    distribution_id: str = field(default_factory=_linux_distribution_id)

    def data_dir(self) -> Path:
        override = os.environ.get("ROMVERSE_HOME")
        return Path(override) if override else Path.home() / ".local" / "share" / "ROMVERSE"

    def config_dir(self) -> Path:
        return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "ROMVERSE"

    def default_workspace(self) -> Path:
        return self.data_dir() / "workspace"

    def find_tool(self, name: str) -> Path | None:
        found = shutil.which(name)
        return Path(found) if found else None


@dataclass(frozen=True, slots=True)
class WindowsHost:
    name: str = "Windows"
    distribution_id: str = "windows"

    def data_dir(self) -> Path:
        override = os.environ.get("ROMVERSE_HOME") or os.environ.get("LOCALAPPDATA")
        return (
            Path(override) / ("" if os.environ.get("ROMVERSE_HOME") else "ROMVERSE")
            if override
            else Path.home() / "AppData" / "Local" / "ROMVERSE"
        )

    def config_dir(self) -> Path:
        return self.data_dir() / "config"

    def default_workspace(self) -> Path:
        return self.data_dir() / "workspace"

    def find_tool(self, name: str) -> Path | None:
        found = shutil.which(name) or shutil.which(f"{name}.exe")
        return Path(found) if found else None


def current_host() -> HostPlatform:
    return WindowsHost() if sys.platform == "win32" else LinuxHost()
