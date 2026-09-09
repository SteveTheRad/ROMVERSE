from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from romverse.infrastructure.local_store import ensure_private_file
from romverse.platform.host import HostPlatform


class ExperienceMode(StrEnum):
    """Persisted complexity level without weakening Guardian policy."""

    GUIDED = "guided"
    EXPERT = "expert"


class DesktopTheme(StrEnum):
    """Persisted visual identity; themes never change workflow or Guardian policy."""

    NEBULA_FLOW = "nebula-flow"
    AURORA = "aurora"
    VIOLET_NIGHT = "violet-night"
    NEBULA_ROSE = "nebula-rose"
    DEEP_SPACE = "deep-space"
    SOLAR_FLARE = "solar-flare"
    QUANTUM_MINT = "quantum-mint"


@dataclass(slots=True)
class AppSettings:
    schema_version: int = 5
    onboarding_complete: bool = False
    workspace_path: str = ""
    experience_mode: ExperienceMode = ExperienceMode.GUIDED
    desktop_theme: DesktopTheme = DesktopTheme.NEBULA_FLOW
    scan_interval_seconds: int = 8
    mask_device_serials: bool = True
    online_intelligence_enabled: bool = True
    community_research_enabled: bool = True
    auto_download_verified_tools: bool = True
    synapse_contributions_enabled: bool = False
    ai_daily_reasoning_budget: int = 50_000
    ai_concurrency_limit: int = 2
    desktop_notifications_enabled: bool = True
    reduced_motion: bool = False
    backup_directory: str = ""
    update_channel: str = "stable"
    members_issuer: str = ""
    members_client_id: str = ""


class SettingsStore:
    MAXIMUM_BYTES = 64 * 1024

    def __init__(self, host: HostPlatform) -> None:
        self._path = host.config_dir() / "settings.json"

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> AppSettings:
        if self._path.is_symlink() or not self._path.is_file():
            return AppSettings()
        try:
            size = self._path.stat().st_size
            if size <= 0 or size > self.MAXIMUM_BYTES:
                return AppSettings()
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("schema_version", 1) not in (1, 2, 3, 4, 5):
                return AppSettings()
            return _validated_settings(data)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        normalized = _validated_settings(asdict(settings))
        temporary = self._path.with_name(f".{self._path.name}.{uuid4().hex}.tmp")
        try:
            content = json.dumps(asdict(normalized), indent=2, sort_keys=True) + "\n"
            with temporary.open("w", encoding="utf-8") as stream:
                ensure_private_file(temporary)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._path)
            ensure_private_file(self._path)
        finally:
            temporary.unlink(missing_ok=True)


def _validated_settings(data: dict[str, object]) -> AppSettings:
    defaults = AppSettings()
    onboarding = data.get("onboarding_complete")
    workspace = data.get("workspace_path")
    interval = data.get("scan_interval_seconds")
    experience_mode = data.get("experience_mode")
    desktop_theme = data.get("desktop_theme")
    mask_serials = data.get("mask_device_serials")
    backup_directory = data.get("backup_directory")
    update_channel = data.get("update_channel")
    members_issuer = data.get("members_issuer")
    members_client_id = data.get("members_client_id")
    reasoning_budget = data.get("ai_daily_reasoning_budget")
    concurrency_limit = data.get("ai_concurrency_limit")

    def preference(name: str, default: bool) -> bool:
        value = data.get(name)
        return value if isinstance(value, bool) else default

    def bounded_path(value: object) -> str:
        return (
            value if isinstance(value, str) and len(value) <= 4096 and "\x00" not in value else ""
        )

    def bounded_text(value: object, maximum: int) -> str:
        return value.strip() if isinstance(value, str) and len(value.strip()) <= maximum else ""

    return AppSettings(
        schema_version=5,
        onboarding_complete=(
            onboarding if isinstance(onboarding, bool) else defaults.onboarding_complete
        ),
        workspace_path=(
            workspace
            if isinstance(workspace, str) and len(workspace) <= 4096 and "\x00" not in workspace
            else defaults.workspace_path
        ),
        experience_mode=(
            ExperienceMode(experience_mode)
            if isinstance(experience_mode, str)
            and experience_mode in {mode.value for mode in ExperienceMode}
            else defaults.experience_mode
        ),
        desktop_theme=(
            DesktopTheme(desktop_theme)
            if isinstance(desktop_theme, str)
            and desktop_theme in {theme.value for theme in DesktopTheme}
            else defaults.desktop_theme
        ),
        scan_interval_seconds=(
            interval
            if isinstance(interval, int) and not isinstance(interval, bool) and 3 <= interval <= 300
            else defaults.scan_interval_seconds
        ),
        mask_device_serials=(
            mask_serials if isinstance(mask_serials, bool) else defaults.mask_device_serials
        ),
        online_intelligence_enabled=preference(
            "online_intelligence_enabled", defaults.online_intelligence_enabled
        ),
        community_research_enabled=preference(
            "community_research_enabled", defaults.community_research_enabled
        ),
        auto_download_verified_tools=preference(
            "auto_download_verified_tools", defaults.auto_download_verified_tools
        ),
        synapse_contributions_enabled=preference(
            "synapse_contributions_enabled", defaults.synapse_contributions_enabled
        ),
        ai_daily_reasoning_budget=(
            reasoning_budget
            if isinstance(reasoning_budget, int)
            and not isinstance(reasoning_budget, bool)
            and 1_000 <= reasoning_budget <= 1_000_000
            else defaults.ai_daily_reasoning_budget
        ),
        ai_concurrency_limit=(
            concurrency_limit
            if isinstance(concurrency_limit, int)
            and not isinstance(concurrency_limit, bool)
            and 1 <= concurrency_limit <= 8
            else defaults.ai_concurrency_limit
        ),
        desktop_notifications_enabled=preference(
            "desktop_notifications_enabled", defaults.desktop_notifications_enabled
        ),
        reduced_motion=preference("reduced_motion", defaults.reduced_motion),
        backup_directory=bounded_path(backup_directory),
        update_channel=(
            update_channel
            if isinstance(update_channel, str) and update_channel in {"stable", "preview"}
            else defaults.update_channel
        ),
        members_issuer=bounded_text(members_issuer, 2048),
        members_client_id=bounded_text(members_client_id, 200),
    )
