from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_complete_guided_recovery_journey_is_inert_and_persistent(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1]
    output = tmp_path / "guided-recovery"
    completed = subprocess.run(
        [
            sys.executable,
            str(source / "scripts" / "simulate_guided_recovery.py"),
            str(output),
        ],
        cwd=source,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    report = json.loads(completed.stdout)

    assert report["simulation_only"]
    assert not report["physical_phone_connected"]
    assert not report["physical_phone_changed"]
    assert not report["external_process_started"]
    assert not report["production_adapter_used"]
    assert not report["production_execution_enabled"]
    assert not report["test_trust_material_persisted"]
    assert not report["automatic_retry_allowed"]
    assert not report["bootloader_relock_allowed"]
    assert report["project_reopened"]
    assert report["adapter_invocation_count"] == 3
    assert report["adapter_action_ids"] == [
        "simulation.stock.adapter.restore",
        "simulation.stock.adapter.reboot",
        "simulation.stock.adapter.verify",
    ]

    journey = report["journey"]
    assert journey["scan"]["status"] == "completed"
    assert journey["match"]["status"] == "completed"
    assert journey["prepare"]["execution_authority"] == "none"
    assert journey["consent"]["consent_scope_only"]
    assert journey["consent"]["execution_authority"] == "none"
    assert journey["result"]["completed_step_count"] == 3
    assert journey["result"]["journal_entry_count"] == 3
    assert not journey["result"]["recovery_verified"]
    assert journey["reassessment"] == {
        "incident_state": "verifying",
        "recovered": False,
        "status": "waiting-for-android",
    }
    assert journey["verification"] == {
        "incident_state": "recovered",
        "recovered": True,
        "status": "verified",
        "verified_reboot": True,
    }

    persisted = json.loads((output / "guided-recovery-report.json").read_text(encoding="utf-8"))
    assert persisted == report
    durable_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in (output / "workspace").rglob("*")
        if path.is_file()
    )
    assert "ROMVERSE-INERT-0001" not in durable_text
