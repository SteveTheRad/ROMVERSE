from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QLabel, QSpinBox

from romverse.core.settings import AppSettings, DesktopTheme, ExperienceMode
from romverse.ui.main_window import SettingsDialog


def test_settings_dialog_exposes_only_runtime_backed_controls(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    settings = AppSettings(
        ai_daily_reasoning_budget=123_000,
        ai_concurrency_limit=4,
        desktop_notifications_enabled=False,
        desktop_theme=DesktopTheme.NEBULA_ROSE,
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
    assert "foreground alerts stay inside ROMVERSE" in labels
    assert "Verification and safe staging are ready" in labels
    assert "Publisher trust is unavailable" in labels
    assert "Show milestone and attention notifications" in checks
    assert " tokens/day" not in spin_suffixes
    assert "Guided Mode · ROMVERSE Arcana" in combo_text
    assert "Expert Mode · Architect workspace" in combo_text
    assert "Nebula Rose" in combo_text
    assert "Quantum Mint" in combo_text
    assert "Stable releases" in combo_text
    assert "Preview release candidates" in combo_text
    assert "header reachability monitor" in dialog.online_intelligence.toolTip()
    assert "official Android ID refresh" in dialog.online_intelligence.toolTip()

    dialog.experience_mode.setCurrentIndex(
        dialog.experience_mode.findData(ExperienceMode.EXPERT.value)
    )
    dialog.desktop_theme.setCurrentIndex(
        dialog.desktop_theme.findData(DesktopTheme.QUANTUM_MINT.value)
    )
    assert "Guided Guardian sequencing is off" in dialog.experience_note.text()
    assert "Exact target" in dialog.experience_note.text()

    saved = dialog.values()
    assert saved.ai_daily_reasoning_budget == 123_000
    assert saved.ai_concurrency_limit == 4
    assert not saved.desktop_notifications_enabled
    assert saved.update_channel == "preview"
    assert saved.experience_mode is ExperienceMode.EXPERT
    assert saved.desktop_theme is DesktopTheme.QUANTUM_MINT

    dialog.close()
