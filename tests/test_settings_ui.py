from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QLabel, QSpinBox

from romverse.core.settings import AppSettings, ExperienceMode
from romverse.ui.main_window import SettingsDialog


def test_settings_dialog_exposes_only_runtime_backed_controls(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    settings = AppSettings(
        ai_daily_reasoning_budget=123_000,
        ai_concurrency_limit=4,
        desktop_notifications_enabled=False,
        update_channel="preview",
    )
    dialog = SettingsDialog(tmp_path, settings)
    app.processEvents()

    labels = "\n".join(label.text() for label in dialog.findChildren(QLabel))
    checks = {check.text() for check in dialog.findChildren(QCheckBox)}
    spin_suffixes = {spin.suffix() for spin in dialog.findChildren(QSpinBox)}
    combo_text = {
        combo.itemText(index)
        for combo in dialog.findChildren(QComboBox)
        for index in range(combo.count())
    }

    assert "no public AI provider or client-side usage service" in labels
    assert "no Desktop notification service runs" in labels
    assert "signed automatic update infrastructure is not yet implemented" in labels
    assert "Show milestone and attention notifications" not in checks
    assert " tokens/day" not in spin_suffixes
    assert "Guided Mode · ROMVERSE Arcana" in combo_text
    assert "Expert Mode · Architect workspace" in combo_text

    dialog.experience_mode.setCurrentIndex(
        dialog.experience_mode.findData(ExperienceMode.EXPERT.value)
    )
    assert "Guardian remains active" in dialog.experience_note.text()

    saved = dialog.values()
    assert saved.ai_daily_reasoning_budget == 123_000
    assert saved.ai_concurrency_limit == 4
    assert not saved.desktop_notifications_enabled
    assert saved.update_channel == "preview"
    assert saved.experience_mode is ExperienceMode.EXPERT

    dialog.close()
