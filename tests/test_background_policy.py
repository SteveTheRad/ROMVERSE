from pathlib import Path


def test_ui_background_work_uses_the_supervised_worker_boundary() -> None:
    ui_root = Path(__file__).parents[1] / "src" / "romverse" / "ui"
    violations: list[str] = []
    for path in ui_root.glob("*.py"):
        if path.name == "background.py":
            continue
        source = path.read_text(encoding="utf-8")
        if "QThreadPool" in source or "QRunnable" in source:
            violations.append(path.name)

    assert violations == [], (
        "UI workers must use ManagedRunnable/start_background so PySide cannot auto-delete "
        f"live Python callbacks: {violations}"
    )
