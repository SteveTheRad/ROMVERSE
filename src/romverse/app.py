from __future__ import annotations

import argparse
import sys
import tempfile
from dataclasses import replace
from importlib.resources import as_file, files
from pathlib import Path

from PySide6.QtCore import QLockFile, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QDialog

from romverse.core.runtime_stability import GuiThreadGarbageCollector, RuntimeCrashGuard
from romverse.core.settings import AppSettings, SettingsStore
from romverse.core.workspace import WorkspaceInitializer
from romverse.device.adb import AdbClient
from romverse.device.engine import DeviceEngine
from romverse.device.fastboot import FastbootClient
from romverse.device_packs.attestations import (
    DevicePackAttestationStore,
    DevicePackAttestationVerifier,
    load_publisher_trust_keys,
)
from romverse.device_packs.registry import DevicePackRegistry
from romverse.guardian.audit import GuardianAuditStore
from romverse.guardian.gateway import ExecutionGateway
from romverse.guardian.policy import GuardianPolicy
from romverse.infrastructure.process import SubprocessRunner
from romverse.infrastructure.tools import ToolVerifier
from romverse.platform.host import current_host
from romverse.ui.main_window import MainWindow
from romverse.ui.setup_wizard import SetupWizard
from romverse.ui.theme import STYLESHEET, apply_dark_palette
from romverse.ui.toolchain_center import activate_verified_managed_tools


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ROMVERSE Studio")
    parser.add_argument(
        "--workspace",
        type=Path,
        help="Temporarily override the ROMVERSE workspace for this launch only",
    )
    parser.add_argument("--skip-onboarding", action="store_true", help="Skip the first-run wizard")
    parser.add_argument("--release-smoke", action="store_true", help=argparse.SUPPRESS)
    return parser


def launch_settings(
    current: AppSettings,
    workspace: Path,
    *,
    ephemeral_workspace: bool,
) -> AppSettings | None:
    """Build persistent launch settings without leaking CLI test paths.

    ``--workspace`` is deliberately a one-launch override. Release smoke tests and
    development sessions often point it at a temporary filesystem; persisting that
    value could strand real projects in volatile storage on the next normal launch.
    """

    if ephemeral_workspace:
        return None
    return replace(
        current,
        onboarding_complete=True,
        workspace_path=str(workspace),
        # Masking is a safety invariant for normal launches. The setting remains
        # explicit so future export-specific controls can be added without ever
        # exposing a device identifier by accident.
        mask_device_serials=True,
    )


def persist_scan_interval(
    store: SettingsStore,
    current: AppSettings,
    interval_seconds: int,
) -> AppSettings:
    """Persist the bounded desktop scan preference without changing other settings."""
    updated = replace(current, scan_interval_seconds=interval_seconds)
    store.save(updated)
    return updated


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv[:1])
    app.setApplicationName("ROMVERSE")
    app.setOrganizationName("RadForge Labs")
    app.setStyle("Fusion")
    apply_dark_palette(app)
    app.setStyleSheet(STYLESHEET)
    lock_name = "romverse-release-smoke.lock" if args.release_smoke else "romverse-studio.lock"
    instance_lock = QLockFile(str(Path(tempfile.gettempdir()) / lock_name))
    # A killed/aborted GUI can leave lock metadata behind. Qt can safely
    # remove it only when the recorded owner is no longer alive; a live
    # second instance still prevents startup.
    if not instance_lock.tryLock(100) and (
        not instance_lock.removeStaleLockFile() or not instance_lock.tryLock(100)
    ):
        return 2

    host = current_host()
    runner = SubprocessRunner()
    store = SettingsStore(host)
    settings = store.load()
    default_workspace = args.workspace or (
        Path(settings.workspace_path) if settings.workspace_path else host.default_workspace()
    )
    tools = ToolVerifier(host, runner).verify_extended()

    with (
        as_file(files("romverse.assets").joinpath("romverse-mark.svg")) as logo_path,
        as_file(files("romverse.assets").joinpath("romverse-brand.png")) as brand_path,
        as_file(files("romverse.assets").joinpath("romverse-r.png")) as r_path,
        as_file(files("romverse.assets").joinpath("romverse-app-icon.png")) as app_icon_path,
        as_file(files("romverse.assets").joinpath("device_pack_trust")) as trust_root,
    ):
        app.setWindowIcon(QIcon(str(app_icon_path)))
        if not settings.onboarding_complete and not args.skip_onboarding:
            wizard = SetupWizard(logo_path, default_workspace, tools)
            if wizard.exec() != QDialog.DialogCode.Accepted:
                return 0
            default_workspace = wizard.selected_workspace

        workspace = WorkspaceInitializer().initialize(default_workspace).root
        # Managed executables are never trusted merely because they exist. Activate only
        # receipt-verified directories, then rebuild the authoritative startup inventory.
        activate_verified_managed_tools(workspace)
        tools = ToolVerifier(host, runner).verify_extended()
        persistent_settings = launch_settings(
            settings,
            workspace,
            ephemeral_workspace=args.workspace is not None,
        )
        if persistent_settings is not None:
            settings = persistent_settings
            store.save(settings)

        adb_status = next((status for status in tools if status.name == "ADB"), None)
        fastboot_status = next((status for status in tools if status.name == "Fastboot"), None)
        engine = None
        gateway = None
        adb_executable = None
        fastboot_executable = None
        audit_store = GuardianAuditStore(workspace)
        pack_registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
        openssl = host.find_tool("openssl")
        attestation_store = (
            DevicePackAttestationStore(
                workspace,
                DevicePackAttestationVerifier(
                    openssl,
                    runner,
                    load_publisher_trust_keys(trust_root),
                ),
            )
            if openssl is not None
            else None
        )
        if adb_status is not None and adb_status.available and adb_status.path:
            adb_executable = Path(adb_status.path)
        if fastboot_status is not None and fastboot_status.available and fastboot_status.path:
            fastboot_executable = Path(fastboot_status.path)
        if adb_executable is not None or fastboot_executable is not None:
            gateway = ExecutionGateway(GuardianPolicy(workspace), runner, audit_store)
            engine = DeviceEngine(
                AdbClient(adb_executable, gateway) if adb_executable is not None else None,
                FastbootClient(fastboot_executable, gateway)
                if fastboot_executable is not None
                else None,
            )
        with GuiThreadGarbageCollector(app), RuntimeCrashGuard(workspace):
            window = MainWindow(
                engine,
                logo_path,
                workspace,
                settings.scan_interval_seconds,
                audit_store,
                pack_registry,
                brand_path,
                r_path,
                host,
                runner,
                tools,
                app_icon_path=app_icon_path,
                gateway=gateway,
                adb_executable=adb_executable,
                fastboot_executable=fastboot_executable,
                attestation_store=attestation_store,
                app_settings=settings,
            )
            window.settings_changed.connect(store.save)
            window.show()
            if args.release_smoke:
                QTimer.singleShot(250, app.quit)
            return app.exec()
