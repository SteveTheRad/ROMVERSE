from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def test_guided_simulation_uses_production_dialogs_and_no_physical_transport(tmp_path):
    source = Path(__file__).resolve().parents[1]
    script = source / "scripts" / "simulate_project_installation.py"
    output = tmp_path / "guided-simulation"
    arguments = [sys.executable, str(script), str(output)]
    environment = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    result = subprocess.run(
        arguments,
        cwd=source,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report == json.loads((output / "simulation-report.json").read_text())
    assert report["simulation_only"]
    assert not report["physical_phone_changed"]
    assert not report["production_certified"]
    assert not report["full_firmware_install"]
    assert "accelerated simulation" in report["clock"]
    assert report["protected_source_explicitly_selected"]
    assert report["destination_initially_blank"]
    assert report["destination_manually_entered"] == "boot_a"
    assert report["decline_sent_no_write"]
    assert report["confirmed_image_write_count"] == 1
    assert report["confirmed_android_arrival"]
    assert report["observed_boot_status"] == "stable"
    assert report["simulated_boot_window_seconds"] == 60
    assert report["boot_sample_count"] >= 11
    assert report["source_unchanged"] and report["flash_receipt_unchanged"]
    assert report["audit_valid"]
    assert report["compact_layout_readable"]
    for name in ("preparation", "image-review", "stable-boot"):
        assert (
            (output / f"simulation-project-{name}.png")
            .read_bytes()
            .startswith(b"\x89PNG\r\n\x1a\n")
        )
    journals = output / "workspace" / "guardian"
    flashes = list((journals / "local-flash").glob("*.json"))
    assert len(flashes) == 1
    assert hashlib.sha256(flashes[0].read_bytes()).hexdigest() == report["flash_receipt_sha256"]
    flash = json.loads(flashes[0].read_text())
    assert not flash["boot_verified"] and not flash["readback_verified"]
    assert not flash["external_certification"]
    records = [json.loads(path.read_text()) for path in (journals / "local-boot").glob("*.json")]
    assert len(records) == 1
    assert records[0]["status"] == "stable" and records[0]["flash_binding"]
    assert not records[0]["production_certified"] and not records[0]["subsystems_verified"]
    original_report = (output / "simulation-report.json").read_bytes()
    rerun = subprocess.run(
        arguments, cwd=source, env=environment, capture_output=True, timeout=10, check=False
    )
    assert rerun.returncode != 0
    assert (output / "simulation-report.json").read_bytes() == original_report
