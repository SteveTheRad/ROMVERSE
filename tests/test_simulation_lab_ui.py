from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from romverse.core.settings import ExperienceMode
from romverse.rom.simulation import (
    DigitalTwinPartition,
    PartitionIntent,
    RollbackRehearsal,
    RomSimulationReceipt,
    SimulatedOperation,
    SimulationFinding,
    SimulationSeverity,
)
from romverse.ui.simulation_lab import DigitalTwinDialog


def _receipt(*, successful: bool = True) -> RomSimulationReceipt:
    return RomSimulationReceipt(
        1,
        "a" * 32,
        "test-project",
        "2026-09-05T00:00:00+00:00",
        "b" * 64,
        "c" * 64,
        "test.pack",
        "d" * 64,
        "Test Phone",
        "test-device",
        "TEST.1",
        "TEST.2",
        "UPGRADE CANDIDATE • TEST.1 → TEST.2",
        (
            DigitalTwinPartition(
                "super",
                "physical container",
                "dynamic",
                8192,
                4096,
                "none",
                PartitionIntent.WRITE,
                "super.img",
                "fastbootd",
                SimulationSeverity.VERIFIED,
                "Artifact fits.",
            ),
            DigitalTwinPartition(
                "system",
                "dynamic_a",
                "erofs",
                4096,
                2048,
                "unchanged",
                PartitionIntent.PRESERVE,
                "",
                "none",
                SimulationSeverity.VERIFIED,
                "Preserved.",
            ),
        ),
        (
            SimulatedOperation(
                1,
                "write:1:super",
                "write",
                "Write super from super.img",
                "super",
                "none",
                "fastbootd",
                "super.img",
                4096,
                3,
                "REHEARSED",
            ),
        ),
        (
            SimulationFinding(
                "source-contract",
                SimulationSeverity.VERIFIED,
                "Exact source contract",
                "The source and pack agree.",
                "No action required.",
            ),
        ),
        RollbackRehearsal(
            True,
            "recorded_slot_then_stock_package",
            ("Backup verified", "Stock recovery verified"),
            (),
        ),
        4096,
        16384,
        32768,
        3,
        50,
        92,
        92,
        "HIGH",
        (
            "USB stability cannot be proven by simulation.",
            "First boot must be observed on hardware.",
        ),
        (),
        "",
        successful,
        successful,
        False,
        "none",
        "e" * 64,
    )


def test_simulation_lab_presents_phone_model_limits_and_mission_state():
    app = QApplication.instance() or QApplication([])
    service = SimpleNamespace()
    dialog = DigitalTwinDialog(
        service,
        _receipt(),
        ExperienceMode.GUIDED,
    )
    dialog.resize(1280, 820)
    dialog.show()
    app.processEvents()

    labels = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert "Rehearse the entire operation before touching hardware" in labels
    assert "Test Phone" in labels
    assert "PHONE CHANGED: NO" in dialog.footer_status.text()
    assert dialog.mission_button.isEnabled()
    assert not dialog.expert_button.isEnabled()
    assert dialog.phone.receipt.partitions[0].name == "super"
    dialog.close()


def test_simulation_lab_expert_editor_is_available_only_with_operations():
    QApplication.instance() or QApplication([])
    service = SimpleNamespace()
    dialog = DigitalTwinDialog(
        service,
        _receipt(),
        ExperienceMode.EXPERT,
    )

    assert dialog.expert_button.isEnabled()
    assert dialog.mission_button.text() == "Continue as ROM Studio mission"
    dialog.close()
