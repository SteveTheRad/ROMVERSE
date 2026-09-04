from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_user_journey_uses_real_ui_and_services_but_only_inert_transport(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1]
    output = tmp_path / "simulated-user"
    result = subprocess.run(
        [sys.executable, str(source / "scripts" / "simulate_expert_lifecycle.py"), str(output)],
        cwd=source,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    report = json.loads(result.stdout)
    assert report["simulation_only"] and not report["physical_phone_changed"]
    assert all(
        report[key]
        for key in (
            "decline_sent_no_reboot",
            "confirmed_mode_transition",
            "confirmed_image_write",
            "matching_hardware_region_variant",
            "bootloop_handoff",
            "audit_valid",
        )
    )
    assert report["measured_boot_window_seconds"] == 60
    for name in ("simulation-image-review.png", "simulation-stable-boot.png"):
        assert (output / name).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    boot_receipts = list((output / "workspace" / "guardian" / "local-boot").glob("*.json"))
    records = [json.loads(path.read_text()) for path in boot_receipts]
    assert {record["status"] for record in records} == {"stable", "attention"}
    assert all(record["flash_binding"] for record in records)
    assert all(
        not record["phone_changed"] and not record["production_certified"] for record in records
    )
