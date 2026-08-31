from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from romverse.rom.debloat import DebloatRisk, DebloatService
from romverse.rom.projects import RomProjectStore
from romverse.ui.debloat_sequence import DebloatWorker, NebulaDebloatDialog


def _dialog(tmp_path):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "source.zip"
    source.write_bytes(b"protected")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Debloat UI")
    store.import_original(project.project_id, source)
    tree = store.working_root / project.project_id / "tree"
    for relative in (
        "system/app/FacebookStub/FacebookStub.apk",
        "product/app/Notes/Notes.apk",
        "system/priv-app/SystemUI/SystemUI.apk",
    ):
        target = tree / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(relative.encode())
    service = DebloatService(store)
    dialog = NebulaDebloatDialog(service, project.project_id, auto_start=False)
    return app, service, project, dialog


def test_nebula_debloat_renders_clear_safety_states(tmp_path):
    app, service, project, dialog = _dialog(tmp_path)

    dialog._scan_complete(service.scan(project.project_id))
    app.processEvents()
    by_risk = {row.candidate.risk: row for row in dialog.rows.values()}

    assert by_risk[DebloatRisk.SAFE].checkbox.isChecked()
    assert by_risk[DebloatRisk.SAFE].checkbox.isEnabled()
    assert not by_risk[DebloatRisk.CAUTION].checkbox.isChecked()
    assert by_risk[DebloatRisk.CAUTION].checkbox.isEnabled()
    assert not by_risk[DebloatRisk.PROTECTED].checkbox.isEnabled()
    assert dialog.safe_count.text() == "1 GREEN"
    assert dialog.caution_count.text() == "1 ORANGE"
    assert dialog.protected_count.text() == "1 RED"
    assert "3 APK files examined" in dialog.status.text()
    assert "3 system app groups" in dialog.status.text()
    assert "partitions: product, system" in dialog.status.text()
    dialog.search.setText("facebook")
    app.processEvents()
    assert sum(not row.isHidden() for row in dialog.rows.values()) == 1
    dialog.search.clear()
    dialog.risk_filter.setCurrentIndex(dialog.risk_filter.findData(DebloatRisk.PROTECTED.value))
    app.processEvents()
    assert sum(not row.isHidden() for row in dialog.rows.values()) == 1
    dialog.close()


def test_nebula_debloat_completion_is_explicit_and_verified(tmp_path):
    app, service, project, dialog = _dialog(tmp_path)
    scan = service.scan(project.project_id)
    dialog._scan_complete(scan)
    safe = next(item for item in scan.candidates if item.risk is DebloatRisk.SAFE)

    receipt = service.apply(service.create_plan(scan, (safe.candidate_id,)))
    dialog._apply_complete(receipt)
    app.processEvents()

    assert dialog.completed
    assert "NEBULA DEBLOAT COMPLETE" in dialog.status.text()
    assert "rollback verified" in dialog.status.text()
    assert dialog.apply_button.text() == "Continue Genesis Sequence"
    dialog.close()


def test_nebula_scan_and_apply_start_honestly_indeterminate(tmp_path, monkeypatch):
    _app, service, project, dialog = _dialog(tmp_path)
    workers: list[DebloatWorker] = []
    monkeypatch.setattr("romverse.ui.debloat_sequence.start_background", workers.append)

    dialog._start_scan()

    assert len(workers) == 1
    assert workers[0].plan is None
    assert dialog.progress.maximum() == 0
    assert not dialog.progress.isTextVisible()
    assert "Measured app-record progress" in dialog.status.text()

    dialog.worker = None
    dialog._scan_complete(service.scan(project.project_id))
    dialog._apply()

    assert len(workers) == 2
    assert workers[1].plan is not None
    assert dialog.progress.maximum() == 0
    assert not dialog.progress.isTextVisible()
    assert "no trustworthy total" in dialog.status.text()

    dialog.worker = None
    dialog.close()
