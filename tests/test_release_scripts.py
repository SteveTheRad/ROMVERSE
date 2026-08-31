import zipfile
from pathlib import Path

import pytest

from scripts.verify_wheel import source_runtime_files, verify_wheel


def test_wheel_runtime_inventory_covers_every_module_and_asset() -> None:
    repository = Path(__file__).resolve().parents[1]
    package = repository / "src" / "romverse"
    inventory = source_runtime_files(package)
    expected_modules = {
        f"romverse/{path.relative_to(package).as_posix()}"
        for path in package.rglob("*.py")
        if "__pycache__" not in path.parts and not path.is_symlink()
    }
    expected_assets = {
        f"romverse/{path.relative_to(package).as_posix()}"
        for path in (package / "assets").rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and "__pycache__" not in path.parts
        and path.suffix not in {".pyc", ".pyo"}
    }

    assert set(inventory) == expected_modules | expected_assets
    assert "romverse/ui/ascension_protocol.py" in inventory
    assert "romverse/ascension/releases.py" in inventory
    assert "romverse/assets/dashboard-phone.png" in inventory
    assert "romverse/assets/sidebar-phone-white.png" in inventory
    assert "romverse/assets/origin-ambient.wav" in inventory
    assert not any("__pycache__" in name or name.endswith(".pyc") for name in inventory)


def test_wheel_verifier_rejects_runtime_module_content_drift(tmp_path: Path) -> None:
    inventory = source_runtime_files()
    wheel = tmp_path / "romverse-test-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, source in inventory.items():
            content = source.read_bytes()
            if name == "romverse/ascension/releases.py":
                content += b"\n# changed after wheel build\n"
            archive.writestr(name, content)

    with pytest.raises(ValueError, match="runtime content differs"):
        verify_wheel(wheel)
