import hashlib
import json
import os
import stat
from dataclasses import replace

import pytest

from romverse.device.models import AndroidDevice, DeviceState
from romverse.guardian.flash_handoff import (
    FlashMode,
    GuardianFlashHandoffService,
    assert_never_relocks,
)
from romverse.guardian.invariants import contains_bootloader_relock
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.rom.readiness import BuildGate, BuildReadinessReport, GateStatus


def _prepared(tmp_path):
    source = tmp_path / "firmware.zip"
    source.write_bytes(b"exact firmware")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Guardian", "test.exact")
    project = store.import_original(project.project_id, source)
    gates = tuple(
        BuildGate(gate_id, gate_id, phase, GateStatus.PASS, "verified", "flash")
        for gate_id, phase in (
            ("device-pack-flash", "Recovery"),
            ("device", "Flash"),
            ("battery", "Flash"),
            ("boot", "Flash"),
            ("recovery", "Recovery"),
        )
    )
    report = BuildReadinessReport(
        1,
        "report",
        project.project_id,
        "2026-08-29T00:00:00+00:00",
        gates,
        True,
        True,
        True,
        True,
        True,
        (),
        (),
        "a" * 64,
    )
    device = AndroidDevice(
        "serial",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        model="2509FPN0BC",
        marketing_name="Xiaomi 17 Pro Max",
        product="popsicle",
        codename="popsicle",
    )
    return store, project, report, device


@pytest.mark.parametrize(
    ("mode", "preserve", "wipe"),
    (
        (FlashMode.DIRTY_KEEP_DATA, True, False),
        (FlashMode.CLEAN_WIPE_DATA, False, True),
    ),
)
def test_flash_handoff_binds_mode_source_device_and_never_authorizes_execution(
    tmp_path,
    mode,
    preserve,
    wipe,
):
    store, project, report, device = _prepared(tmp_path)
    service = GuardianFlashHandoffService(store)

    handoff = service.prepare(project.project_id, report, device, mode)
    loaded = service.load(project.project_id)

    assert loaded == handoff
    assert handoff.mode is mode
    assert handoff.preserve_user_data is preserve
    assert handoff.wipe_user_data is wipe
    assert not handoff.bootloader_relock
    assert not handoff.bootloader_relock_allowed
    assert not handoff.execution_authorized
    assert handoff.command_manifest == ()
    assert handoff.source_sha256 == project.original.sha256
    assert service.matches_current(project.project_id, handoff, device, report)
    assert not service.matches_current(
        project.project_id,
        handoff,
        AndroidDevice("other", DeviceState.DEVICE, model=device.model, codename=device.codename),
        report,
    )


def test_flash_handoff_matches_stable_readiness_facts_not_ephemeral_report_identity(tmp_path):
    store, project, report, device = _prepared(tmp_path)
    service = GuardianFlashHandoffService(store)
    handoff = service.prepare(project.project_id, report, device, FlashMode.DIRTY_KEEP_DATA)
    refreshed = replace(
        report,
        report_id="b" * 32,
        created_at="2026-08-30T01:02:03+00:00",
        report_digest="c" * 64,
    )

    assert service.matches_current(project.project_id, handoff, device, refreshed)

    changed_gate = replace(report.gates[0], evidence="changed current recovery evidence")
    changed = replace(
        refreshed,
        gates=(changed_gate, *refreshed.gates[1:]),
        report_digest="d" * 64,
    )
    assert not service.matches_current(project.project_id, handoff, device, changed)


def test_flash_handoff_rejects_incomplete_readiness(tmp_path):
    store, project, report, device = _prepared(tmp_path)
    report = BuildReadinessReport(
        report.schema_version,
        report.report_id,
        report.project_id,
        report.created_at,
        report.gates,
        report.workspace_ready,
        report.build_ready,
        report.local_candidate_ready,
        report.signing_ready,
        False,
        (),
        (),
        report.report_digest,
    )

    with pytest.raises(ProjectError, match="required readiness card"):
        GuardianFlashHandoffService(store).prepare(
            project.project_id,
            report,
            device,
            FlashMode.DIRTY_KEEP_DATA,
        )


def test_tampered_handoff_or_bootloader_relock_command_fails_closed(tmp_path):
    store, project, report, device = _prepared(tmp_path)
    service = GuardianFlashHandoffService(store)
    service.prepare(project.project_id, report, device, FlashMode.DIRTY_KEEP_DATA)
    path = store.projects_root / project.project_id / "guardian" / service.LATEST_NAME
    document = json.loads(path.read_text(encoding="utf-8"))
    document["bootloader_relock_allowed"] = True
    _reseal(document)
    path.write_text(json.dumps(document), encoding="utf-8")

    assert service.load(project.project_id) is None
    for command in (
        ("fastboot", "flashing", "lock"),
        ("fastboot", "flashing", "lock_critical"),
        ("fastboot", "oem", "lock"),
        ("vendor-tool", "--relock"),
    ):
        with pytest.raises(ProjectError, match="permanently prohibits"):
            assert_never_relocks((command,))


def test_no_relock_invariant_does_not_misclassify_read_only_or_flash_tokens():
    assert_never_relocks(
        (
            ("fastboot", "getvar", "unlocked"),
            ("fastboot", "flash", "super", "super.img"),
        )
    )
    assert not contains_bootloader_relock((("fastboot", "getvar", "unlocked"),))


def test_flash_handoff_uses_private_bounded_strict_schema_two_storage(tmp_path):
    store, project, report, device = _prepared(tmp_path)
    service = GuardianFlashHandoffService(store)
    handoff = service.prepare(project.project_id, report, device, FlashMode.DIRTY_KEEP_DATA)
    root = store.projects_root / project.project_id / "guardian"
    latest = root / service.LATEST_NAME

    assert handoff.schema_version == 2
    assert len(handoff.readiness_evidence_digest) == 64
    if os.name != "nt":
        assert stat.S_IMODE(root.stat().st_mode) == 0o700
        assert stat.S_IMODE(latest.stat().st_mode) == 0o600

    document = json.loads(latest.read_text(encoding="utf-8"))
    document["unexpected"] = "field"
    latest.write_text(json.dumps(document), encoding="utf-8")
    assert service.load(project.project_id) is None


def test_flash_handoff_rejects_link_and_oversized_latest_record(tmp_path):
    store, project, report, device = _prepared(tmp_path)
    service = GuardianFlashHandoffService(store)
    handoff = service.prepare(project.project_id, report, device, FlashMode.CLEAN_WIPE_DATA)
    root = store.projects_root / project.project_id / "guardian"
    latest = root / service.LATEST_NAME
    history = root / f"flash-handoff-{handoff.handoff_id[:12]}.romverse"

    latest.unlink()
    latest.symlink_to(history)
    assert service.load(project.project_id) is None

    latest.unlink()
    latest.write_bytes(b"{" + b" " * service.MAX_RECEIPT_BYTES + b"}")
    assert service.load(project.project_id) is None


def test_legacy_flash_handoff_remains_readable_but_cannot_claim_current_authority(tmp_path):
    store, project, report, device = _prepared(tmp_path)
    service = GuardianFlashHandoffService(store)
    service.prepare(project.project_id, report, device, FlashMode.DIRTY_KEEP_DATA)
    latest = store.projects_root / project.project_id / "guardian" / service.LATEST_NAME
    document = json.loads(latest.read_text(encoding="utf-8"))
    document["schema_version"] = 1
    document.pop("readiness_evidence_digest")
    _reseal(document)
    latest.write_text(json.dumps(document), encoding="utf-8")

    legacy = service.load(project.project_id)

    assert legacy is not None and legacy.schema_version == 1
    assert legacy.readiness_evidence_digest == ""
    assert not service.matches_current(project.project_id, legacy, device, report)


def _reseal(document: dict[str, object]) -> None:
    payload = dict(document)
    payload.pop("format", None)
    payload.pop("handoff_digest", None)
    document["handoff_digest"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
