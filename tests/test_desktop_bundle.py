from __future__ import annotations

import os
import tomllib
import zipfile
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from romverse import DISPLAY_VERSION, PACKAGE_VERSION, __version__
from romverse.app import build_parser, development_simulated_device
from romverse.ui.main_window import DESKTOP_SIDEBAR_VERSION, DESKTOP_WINDOW_TITLE
from scripts.build_desktop_executable import pyinstaller_arguments
from scripts.package_desktop_bundle import package_bundle, verify_bundle_archive
from scripts.smoke_frozen_desktop import smoke_frozen_desktop


def test_release_extra_contains_frontend_backend_and_native_bundler() -> None:
    repository = Path(__file__).resolve().parents[1]
    document = tomllib.loads((repository / "pyproject.toml").read_text(encoding="utf-8"))
    release = document["project"]["optional-dependencies"]["release"]

    assert any(item.startswith("build>=") for item in release)
    assert any(item.startswith("hatchling>=") for item in release)
    assert any(item.startswith("pyinstaller>=") for item in release)


def test_alpha_package_runtime_and_visible_desktop_identity_match() -> None:
    repository = Path(__file__).resolve().parents[1]
    document = tomllib.loads((repository / "pyproject.toml").read_text(encoding="utf-8"))

    assert document["project"]["version"] == PACKAGE_VERSION == __version__ == "0.2.0a1"
    assert DISPLAY_VERSION == "0.2.0-alpha.1"
    assert DESKTOP_WINDOW_TITLE == "ROMVERSE Studio 0.2.0-alpha.1"
    assert DESKTOP_SIDEBAR_VERSION == "ROMVERSE  0.2.0-alpha.1"


def _bundle(tmp_path: Path) -> Path:
    root = tmp_path / "ROMVERSE"
    (root / "_internal" / "romverse" / "assets").mkdir(parents=True)
    executable = root / "ROMVERSE"
    executable.write_bytes(b"executable")
    executable.chmod(0o755)
    (root / "_internal" / "romverse" / "assets" / "romverse-brand.png").write_bytes(b"brand")
    return root


def test_desktop_bundle_packages_and_verifies_exact_tree(tmp_path: Path) -> None:
    root = _bundle(tmp_path)
    output = tmp_path / "ROMVERSE-Desktop-0.2.0-alpha.1-linux-x86_64.zip"

    digest, count, total = package_bundle(root, "linux-x86_64", output)

    assert len(digest) == 64
    assert count == 2
    assert total == len(b"executable") + len(b"brand")
    assert verify_bundle_archive(output, "linux-x86_64") == (digest, count, total)
    if os.name != "nt":
        assert output.stat().st_mode & 0o777 == 0o644


def test_desktop_bundle_materializes_internal_file_link(tmp_path: Path) -> None:
    root = _bundle(tmp_path)
    (root / "executable-alias").symlink_to("ROMVERSE")

    _digest, count, total = package_bundle(root, "linux-x86_64", tmp_path / "linked.zip")

    assert count == 3
    assert total == len(b"executable") * 2 + len(b"brand")
    with zipfile.ZipFile(tmp_path / "linked.zip") as archive:
        assert archive.read("ROMVERSE/executable-alias") == b"executable"


def test_desktop_bundle_rejects_escaping_link_and_missing_executable(tmp_path: Path) -> None:
    root = _bundle(tmp_path)
    outside = tmp_path / "outside"
    outside.write_bytes(b"outside")
    (root / "linked").symlink_to(outside)
    with pytest.raises(ValueError, match="escapes its regular-file boundary"):
        package_bundle(root, "linux-x86_64", tmp_path / "linked.zip")

    (root / "linked").unlink()
    (root / "ROMVERSE").unlink()
    with pytest.raises(ValueError, match="missing its platform executable"):
        package_bundle(root, "linux-x86_64", tmp_path / "missing.zip")


def test_desktop_bundle_rejects_unsafe_archive_member(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("ROMVERSE/ROMVERSE", b"executable")
        output.writestr("../outside", b"unsafe")

    with pytest.raises(ValueError, match="unsafe member"):
        verify_bundle_archive(archive, "linux-x86_64")


def test_pyinstaller_build_binds_package_data_and_submodules_to_checkout(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[1]
    arguments = pyinstaller_arguments(repository, tmp_path / "dist", tmp_path / "build")
    assets = repository / "src" / "romverse" / "assets"

    assert "--windowed" in arguments
    assert "--onedir" in arguments
    assert "--collect-data=romverse" not in arguments
    assert (
        f"--add-data={assets / 'knowledge_archive_popsicle_fastboot_seed.json'}:romverse/assets/."
        in arguments
    )
    assert all("__pycache__" not in argument for argument in arguments)
    assert "--collect-submodules=romverse" in arguments
    assert str(repository / "src" / "romverse" / "__main__.py") == arguments[-1]


def test_release_smoke_flag_is_explicit_and_phone_neutral() -> None:
    args = build_parser().parse_args(["--release-smoke", "--skip-onboarding"])

    assert args.release_smoke is True
    assert args.skip_onboarding is True
    assert args.workspace is None


def test_development_device_simulation_is_explicit_and_inert() -> None:
    args = build_parser().parse_args(["--development-device-simulation"])
    device = development_simulated_device()

    assert args.development_device_simulation is True
    assert device.is_simulated
    assert device.connection_note == "SIMULATION ONLY • NOT HARDWARE VERIFIED"
    assert device.codename == "popsicle"


def test_frozen_smoke_uses_bounded_release_mode(tmp_path: Path, monkeypatch) -> None:
    executable = tmp_path / "ROMVERSE"
    executable.write_bytes(b"executable")
    recorded: dict[str, object] = {}

    def fake_run(command, **kwargs):
        recorded.update(command=command, kwargs=kwargs)
        return CompletedProcess(command, 0)

    monkeypatch.setattr("scripts.smoke_frozen_desktop.subprocess.run", fake_run)
    workspace = tmp_path / "workspace"

    smoke_frozen_desktop(executable, workspace)

    assert recorded["command"] == [
        str(executable.resolve()),
        "--workspace",
        str(workspace.resolve()),
        "--skip-onboarding",
        "--release-smoke",
    ]
    assert recorded["kwargs"]["timeout"] == 60
    assert recorded["kwargs"]["check"] is False
