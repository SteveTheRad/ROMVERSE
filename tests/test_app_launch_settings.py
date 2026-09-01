import inspect

from romverse import app as app_module
from romverse.app import build_parser, launch_settings, persist_scan_interval
from romverse.core.settings import AppSettings, SettingsStore


class ConfigHost:
    name = "Test"

    def __init__(self, root):
        self.root = root

    def config_dir(self):
        return self.root / "config"


def test_desktop_launch_opens_without_a_custom_splash_sequence() -> None:
    source = inspect.getsource(app_module.main)

    assert "BrandSplash" not in source
    assert "splash_path" not in source


def test_cli_workspace_override_is_ephemeral_and_never_persisted(tmp_path) -> None:
    current = AppSettings(
        onboarding_complete=True,
        workspace_path="/persistent/romverse/workspace",
        scan_interval_seconds=12,
    )
    args = build_parser().parse_args(["--workspace", str(tmp_path / "release-smoke")])

    assert args.workspace == tmp_path / "release-smoke"
    assert (
        launch_settings(
            current,
            args.workspace,
            ephemeral_workspace=True,
        )
        is None
    )


def test_normal_launch_persists_the_verified_workspace_and_preferences(tmp_path) -> None:
    current = AppSettings(scan_interval_seconds=14, mask_device_serials=False)
    workspace = (tmp_path / "workspace").resolve()

    updated = launch_settings(current, workspace, ephemeral_workspace=False)

    assert updated is not None
    assert updated.onboarding_complete
    assert updated.workspace_path == str(workspace)
    assert updated.scan_interval_seconds == 14
    assert updated.mask_device_serials


def test_scan_interval_change_is_persisted_without_overwriting_other_preferences(tmp_path) -> None:
    store = SettingsStore(ConfigHost(tmp_path))
    current = AppSettings(
        onboarding_complete=True,
        workspace_path="/persistent/workspace",
        scan_interval_seconds=8,
        mask_device_serials=True,
    )

    updated = persist_scan_interval(store, current, 45)

    assert updated.scan_interval_seconds == 45
    assert store.load() == updated
    assert store.load().workspace_path == "/persistent/workspace"
