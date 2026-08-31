import json

from romverse.core.workspace import WORKSPACE_DIRECTORIES, WorkspaceInitializer


def test_workspace_initialization_is_idempotent(tmp_path):
    initializer = WorkspaceInitializer()
    first = initializer.initialize(tmp_path / "studio")
    second = initializer.initialize(tmp_path / "studio")
    assert all((first.root / name).is_dir() for name in WORKSPACE_DIRECTORIES)
    assert json.loads(first.manifest.read_text())["schema_version"] == 1
    assert second.created == ()
