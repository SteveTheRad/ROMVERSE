import json
import stat
from pathlib import Path

from romverse.core.settings import AppSettings, DesktopTheme, ExperienceMode, SettingsStore


class FakeHost:
    name = "Test"

    def __init__(self, root: Path) -> None:
        self.root = root

    def config_dir(self) -> Path:
        return self.root / "config"

    def data_dir(self) -> Path:
        return self.root / "data"

    def default_workspace(self) -> Path:
        return self.root / "workspace"

    def find_tool(self, _name: str) -> Path | None:
        return None


def test_settings_store_round_trips_bounded_private_preferences(tmp_path) -> None:
    store = SettingsStore(FakeHost(tmp_path))
    expected = AppSettings(
        onboarding_complete=True,
        workspace_path=str(tmp_path / "workspace"),
        experience_mode=ExperienceMode.EXPERT,
        desktop_theme=DesktopTheme.SOLAR_FLARE,
        scan_interval_seconds=27,
        mask_device_serials=False,
        online_intelligence_enabled=False,
        community_research_enabled=False,
        auto_download_verified_tools=False,
        synapse_contributions_enabled=True,
        ai_daily_reasoning_budget=120_000,
        ai_concurrency_limit=3,
        desktop_notifications_enabled=False,
        reduced_motion=True,
        backup_directory=str(tmp_path / "backups"),
        update_channel="preview",
        members_issuer="https://members.example.test",
        members_client_id="desktop-client",
    )

    store.save(expected)

    assert store.load() == expected
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    assert not list(store.path.parent.glob(".*.tmp"))


def test_settings_store_normalizes_invalid_fields_without_trusting_types(tmp_path) -> None:
    store = SettingsStore(FakeHost(tmp_path))
    store.path.parent.mkdir(parents=True)
    store.path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "onboarding_complete": "yes",
                "workspace_path": "unsafe\u0000path",
                "scan_interval_seconds": True,
                "mask_device_serials": "no",
                "backup_directory": "bad\u0000path",
                "update_channel": "dangerous-nightly",
                "members_issuer": 123,
                "members_client_id": "x" * 500,
                "unknown_future_field": "ignored",
            }
        ),
        encoding="utf-8",
    )

    assert store.load() == AppSettings()


def test_settings_store_migrates_schema_one_without_losing_old_preferences(tmp_path) -> None:
    store = SettingsStore(FakeHost(tmp_path))
    store.path.parent.mkdir(parents=True)
    store.path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "onboarding_complete": True,
                "workspace_path": "/legacy/workspace",
                "scan_interval_seconds": 31,
                "mask_device_serials": False,
            }
        ),
        encoding="utf-8",
    )

    migrated = store.load()

    assert migrated.schema_version == 5
    assert migrated.onboarding_complete
    assert migrated.workspace_path == "/legacy/workspace"
    assert migrated.scan_interval_seconds == 31
    assert not migrated.mask_device_serials
    assert migrated.experience_mode is ExperienceMode.GUIDED
    assert migrated.desktop_theme is DesktopTheme.NEBULA_FLOW


def test_settings_store_rejects_unknown_experience_mode_without_losing_other_fields(
    tmp_path,
) -> None:
    store = SettingsStore(FakeHost(tmp_path))
    store.path.parent.mkdir(parents=True)
    store.path.write_text(
        json.dumps(
            {
                "schema_version": 4,
                "experience_mode": "unsafe-developer-bypass",
                "desktop_theme": "guardian-bypass-red",
                "scan_interval_seconds": 41,
            }
        ),
        encoding="utf-8",
    )

    loaded = store.load()

    assert loaded.experience_mode is ExperienceMode.GUIDED
    assert loaded.desktop_theme is DesktopTheme.NEBULA_FLOW
    assert loaded.scan_interval_seconds == 41


def test_settings_store_rejects_unknown_schema_oversize_and_symlink(tmp_path) -> None:
    store = SettingsStore(FakeHost(tmp_path))
    store.path.parent.mkdir(parents=True)
    store.path.write_text('{"schema_version": 99}', encoding="utf-8")
    assert store.load() == AppSettings()

    store.path.write_bytes(b"x" * (SettingsStore.MAXIMUM_BYTES + 1))
    assert store.load() == AppSettings()

    target = tmp_path / "outside.json"
    target.write_text(
        json.dumps({"schema_version": 1, "scan_interval_seconds": 99}),
        encoding="utf-8",
    )
    store.path.unlink()
    store.path.symlink_to(target)
    assert store.load() == AppSettings()
