from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from importlib.resources import files
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QLockFile, Qt
from PySide6.QtWidgets import QApplication

from romverse import app as romverse_app
from romverse.device_packs.registry import DevicePackRegistry
from romverse.guardian.runtime_authorization import GuardianRuntimeAuthorizationService
from romverse.guardian.runtime_execution_claim import GuardianRuntimeExecutionClaimService
from romverse.knowledge.archives import CANONICAL_ROUTES, KNOWN_FIXES
from romverse.knowledge.lookup import OfflineKnowledgeService
from romverse.knowledge.models import KnowledgeQuery
from romverse.legal import (
    PRIVACY_STATUS,
    TERMS_STATUS,
    load_privacy_document,
    load_terms_document,
)
from romverse.rom.projects import RomProjectStore
from romverse.ui import main_window as main_window_module
from romverse.ui.backup_center import BackupCenter
from romverse.ui.knowledge_center import ARCHIVE_ARTICLES, KnowledgeCenter
from romverse.ui.theme import STYLESHEET, apply_dark_palette
from romverse.ui.workspace_shell import NAVIGATION_GROUPS


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test an installed ROMVERSE desktop wheel")
    parser.add_argument("workspace", type=Path)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    smoke_lock = workspace.parent / f".{workspace.name}.romverse-smoke.lock"

    QApplication.exec = lambda _self: 0  # type: ignore[method-assign]

    def launch() -> int:
        # A developer may be exercising the real Desktop while CI validates an installed
        # wheel. Preserve production's single-instance lock and redirect only this
        # in-process smoke launch to a unique lock beside its disposable workspace.
        with (
            patch.object(
                romverse_app,
                "QLockFile",
                side_effect=lambda _production_path: QLockFile(str(smoke_lock)),
            ),
            # The smoke replaces QApplication.exec, so a real asynchronous device scan
            # would outlive the temporary MainWindow. Production launches retain the
            # managed worker; this harness validates startup without orphaning it.
            patch.object(main_window_module, "start_background"),
        ):
            result = romverse_app.main(
                ["--workspace", str(workspace), "--skip-onboarding"],
            )
            launched_app = QApplication.instance()
            if launched_app is not None:
                for widget in launched_app.topLevelWidgets():
                    widget.close()
                launched_app.processEvents()
        return result

    result = launch()
    if result != 0 or not (workspace / ".romverse-workspace.json").is_file():
        raise RuntimeError("Installed desktop did not initialize a fresh workspace")

    assets = files("romverse.assets")
    registry = DevicePackRegistry.load(assets.joinpath("device_packs"))
    if registry.issues or not registry.packs:
        raise RuntimeError("Installed desktop could not verify packaged Device Packs")
    for name in ("product-family.png", "romverse-mark.svg", "romverse-app-icon.png"):
        if not assets.joinpath(name).is_file():
            raise RuntimeError(f"Installed desktop asset is missing: {name}")
    terms = load_terms_document()
    if terms.status != TERMS_STATUS or "Australian Consumer Law" not in terms.text:
        raise RuntimeError("Installed desktop Terms draft is missing or incomplete")
    privacy = load_privacy_document()
    if privacy.status != PRIVACY_STATUS or "Privacy Act 1988" not in privacy.text:
        raise RuntimeError("Installed desktop Privacy draft is missing or incomplete")
    required_handoffs = {
        "time-machine-empty-state-dead-end",
        "command-console-no-trusted-result",
        "health-timeline-comparison-unavailable",
        "members-service-unavailable-or-unconfigured",
        "galaxy-local-publishing-boundary",
        "nexus-current-evidence-route-unavailable",
        "command-palette-nested-feature-missing",
        "live-console-source-opens-owner-not-feature",
        "synapse-evidence-opens-wrong-workspace",
        "nexus-intelligence-feature-opens-generic-page",
        "architect-mode-does-not-change-desktop",
        "fastboot-identity-only",
        "device-build-requirements-blueprint",
        "device-dna-source-blueprint-disagreement",
        "guardian-runtime-consent-consumed-or-expired",
    }
    installed_handoffs = {item.key for item in KNOWN_FIXES}
    if missing := required_handoffs - installed_handoffs:
        raise RuntimeError(f"Installed Archives are missing recovery handoffs: {sorted(missing)}")
    desktop_routes = {route for group in NAVIGATION_GROUPS for route in group.routes}
    archive_routes = {article.route for article in ARCHIVE_ARTICLES}
    if desktop_routes - CANONICAL_ROUTES or desktop_routes - archive_routes:
        raise RuntimeError("Installed Archives do not cover every desktop route")
    if set(dir(GuardianRuntimeAuthorizationService)) & {
        "execute",
        "flash",
        "reboot",
        "erase",
        "unlock",
        "relock",
        "run",
    }:
        raise RuntimeError("Installed Guardian authorization unexpectedly exposes device execution")
    if set(dir(GuardianRuntimeExecutionClaimService)) & {
        "execute",
        "flash",
        "reboot",
        "erase",
        "unlock",
        "relock",
        "run",
        "open",
    }:
        raise RuntimeError("Installed Guardian execution claim unexpectedly opens a device")

    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    apply_dark_palette(app)
    app.setStyleSheet(STYLESHEET)
    offline = OfflineKnowledgeService(workspace)
    archive = offline.store.ensure_seeded()
    if len(archive.records) < 199 or len(archive.sources) < 111:
        raise RuntimeError("Installed offline Archives corpus is missing packaged evidence")
    failure_lookup = offline.lookup(
        KnowledgeQuery(
            error_codes=("HASH_MISMATCH(3)",),
            finding_ids=("security.verified_boot", "boot.incomplete"),
            symptoms=("ODIN MODE (AVB FAIL) vbmeta HASH_MISMATCH(3)",),
        ),
        trigger="release-smoke",
        limit=4,
    )
    if (
        not failure_lookup.matches
        or failure_lookup.matches[0].record.record_id != "core.verified-boot-red-triage"
        or failure_lookup.execution_authority != "none"
    ):
        raise RuntimeError("Installed offline Archives could not rank exact boot-failure evidence")
    archives_center = KnowledgeCenter(offline_service=offline)
    archives_center.resize(1_200, 760)
    archives_center.show()
    archives_center.search.setText("HASH_MISMATCH(3)")
    app.processEvents()
    try:
        has_structured_result = any(
            str(archives_center.list.item(row).data(Qt.ItemDataRole.UserRole)).startswith(
                "offline:"
            )
            for row in range(archives_center.list.count())
        )
        if (
            "OFFLINE BRAIN READY" not in archives_center.offline_archive_status.text()
            or not has_structured_result
        ):
            raise RuntimeError("Installed Archives UI did not expose structured offline evidence")
    finally:
        archives_center.close()
    time_machine = BackupCenter(workspace)
    requested: list[str] = []
    time_machine.rom_studio_setup_requested.connect(requested.append)
    time_machine.resize(1_200, 760)
    time_machine.show()
    app.processEvents()
    try:
        if (
            not time_machine.local_setup.isVisibleTo(time_machine)
            or not time_machine.local_setup_button.isEnabled()
        ):
            raise RuntimeError("Installed Time Machine has no fresh-workspace recovery route")
        time_machine.local_setup_button.click()
        if requested != [""]:
            raise RuntimeError("Installed Time Machine did not preserve empty project identity")
        viewport = time_machine.snapshot_list.viewport().grab().toImage()
        if viewport.pixelColor(8, 8).lightness() >= 64:
            raise RuntimeError("Installed Time Machine inherited a light host viewport")
    finally:
        time_machine.close()

    # Reopen a real populated workspace and prove startup preserves the exact
    # project, immutable original, working copy, and Time Machine snapshot.
    source = workspace.parent / "romverse-installed-smoke-source.bin"
    source.write_bytes(b"ROMVERSE installed desktop preservation evidence\n" * 32)
    store = RomProjectStore(workspace)
    project = store.import_original(store.create("Installed smoke project").project_id, source)
    working = store.create_working_copy(project.project_id)
    snapshot = store.create_snapshot(project.project_id)
    tracked = (
        workspace / ".romverse-workspace.json",
        store.projects_root / project.project_id / store.MANIFEST_NAME,
        workspace / project.original.workspace_path,
        store.projects_root / project.project_id / "working-copy.romverse",
        workspace / working.workspace_path,
        store.snapshots_root / project.project_id / f"{snapshot.snapshot_id}.romverse",
        workspace / snapshot.workspace_path,
    )
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in tracked}
    reopened = subprocess.run(
        (
            sys.executable,
            "-m",
            "romverse",
            "--workspace",
            str(workspace),
            "--skip-onboarding",
            "--release-smoke",
        ),
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if reopened.returncode != 0:
        detail = (reopened.stderr or reopened.stdout).strip()[-1_000:]
        raise RuntimeError(
            f"Installed desktop did not reopen an existing workspace: {detail or reopened.returncode}"
        )
    after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in tracked}
    if after != before or not store.verify_original(project.project_id).valid:
        raise RuntimeError("Installed desktop changed protected existing-workspace evidence")
    print(
        f"Installed ROMVERSE desktop smoke passed with {len(registry.packs)} Device Packs, "
        f"{len(KNOWN_FIXES)} known fixes, {len(archive.records)} offline evidence records, "
        f"{len(desktop_routes)} covered desktop routes, "
        "a connected dark Time Machine empty state, and byte-exact populated-workspace reopening"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
