from pathlib import Path
from unittest.mock import patch

import pytest

from romverse.guardian.audit import AuditIntegrityError, GuardianAuditStore
from romverse.guardian.gateway import ExecutionGateway
from romverse.guardian.models import GuardianDeniedError, OperationClass, OperationRequest
from romverse.guardian.policy import MilestoneOnePolicy
from romverse.infrastructure.process import CommandResult


class RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def run(self, args, timeout=10):
        self.calls.append(tuple(args))
        return CommandResult(tuple(args), 0, "uid=2000(shell)", "")


def device_request(serial: str = "PRIVATE-SERIAL-ABC") -> OperationRequest:
    return OperationRequest(
        "adb.identity",
        OperationClass.READ_ONLY,
        "/usr/bin/adb",
        ("-s", serial, "shell", "id"),
        "Read device identity",
        serial,
    )


def test_audit_chain_records_result_and_redacts_device_identifier(tmp_path):
    runner = RecordingRunner()
    audit = GuardianAuditStore(tmp_path)
    gateway = ExecutionGateway(MilestoneOnePolicy(), runner, audit)
    request = device_request()
    gateway.execute(request)

    verification = audit.verify()
    assert verification.valid
    assert verification.total_entries == 1
    serialized = audit.path.read_text()
    assert request.target not in serialized
    assert "<redacted-device>" in serialized
    record = audit.read_recent()[0]
    assert record["allowed"] is True
    assert record["result"]["returncode"] == 0
    assert record["executable"] == "adb"


def test_audit_redacts_usb_link_one_time_code() -> None:
    arguments = (
        "-s",
        "PRIVATE-SERIAL",
        "shell",
        "am",
        "start",
        "--es",
        "romverse_link_code",
        "123456",
    )

    redacted = GuardianAuditStore._redacted_arguments(arguments)

    assert "PRIVATE-SERIAL" not in redacted
    assert "123456" not in redacted
    assert "<redacted-device>" in redacted
    assert "<redacted-one-time-code>" in redacted


def test_denied_operation_is_audited_without_execution(tmp_path):
    runner = RecordingRunner()
    audit = GuardianAuditStore(tmp_path)
    gateway = ExecutionGateway(MilestoneOnePolicy(), runner, audit)
    request = OperationRequest(
        "adb.reboot",
        OperationClass.STATE_CHANGING,
        "adb",
        ("reboot", "bootloader"),
        "Reboot device",
        "PRIVATE-SERIAL-ABC",
    )
    with pytest.raises(GuardianDeniedError):
        gateway.execute(request)
    assert runner.calls == []
    assert audit.read_recent()[0]["allowed"] is False


def test_tampering_is_detected_and_blocks_next_process(tmp_path):
    runner = RecordingRunner()
    audit = GuardianAuditStore(tmp_path)
    gateway = ExecutionGateway(MilestoneOnePolicy(), runner, audit)
    gateway.execute(device_request())
    original_calls = len(runner.calls)

    tampered = audit.path.read_text().replace('"allowed":true', '"allowed":false', 1)
    audit.path.write_text(tampered)
    assert not audit.verify().valid
    with pytest.raises(AuditIntegrityError):
        gateway.execute(device_request("ANOTHER-PRIVATE-SERIAL"))
    assert len(runner.calls) == original_calls


def test_audit_file_is_under_workspace_logs(tmp_path):
    audit = GuardianAuditStore(tmp_path)
    assert audit.path == Path(tmp_path) / "logs" / "guardian-audit.jsonl"


def test_verified_tail_cache_avoids_rehashing_the_full_chain_per_probe(tmp_path):
    runner = RecordingRunner()
    audit = GuardianAuditStore(tmp_path)
    gateway = ExecutionGateway(MilestoneOnePolicy(), runner, audit)

    with patch.object(audit, "_load", wraps=audit._load) as full_load:
        for _index in range(40):
            gateway.execute(device_request())
        assert full_load.call_count == 1

    verification = audit.verify()
    assert verification.valid
    assert verification.total_entries == 40


def test_verified_tail_cache_rechecks_external_appends_and_preserves_one_chain(tmp_path):
    runner = RecordingRunner()
    first = GuardianAuditStore(tmp_path)
    second = GuardianAuditStore(tmp_path)
    first_gateway = ExecutionGateway(MilestoneOnePolicy(), runner, first)
    second_gateway = ExecutionGateway(MilestoneOnePolicy(), runner, second)

    first_gateway.execute(device_request("FIRST"))
    second_gateway.execute(device_request("SECOND"))
    first_gateway.execute(device_request("THIRD"))

    verification = first.verify()
    assert verification.valid
    assert verification.total_entries == 3
    assert [item["sequence"] for item in reversed(first.read_recent())] == [1, 2, 3]


def test_audit_symlink_is_rejected(tmp_path):
    outside = tmp_path / "outside.jsonl"
    outside.write_text("{}\n", encoding="utf-8")
    audit = GuardianAuditStore(tmp_path / "workspace")
    audit.path.parent.mkdir(parents=True)
    audit.path.symlink_to(outside)

    verification = audit.verify()
    assert not verification.valid
    assert "regular local file" in verification.reason


def test_audit_rejects_oversized_file_before_parsing(tmp_path):
    audit = GuardianAuditStore(tmp_path)
    audit.path.parent.mkdir(parents=True)
    with audit.path.open("wb") as stream:
        stream.truncate(audit.MAX_FILE_BYTES + 1)

    verification = audit.verify()

    assert not verification.valid
    assert verification.total_entries == 0
    assert "bounded file size" in verification.reason


def test_audit_rejects_an_oversized_record_line(tmp_path):
    audit = GuardianAuditStore(tmp_path)
    audit.path.parent.mkdir(parents=True)
    audit.path.write_text("x" * (audit.MAX_LINE_BYTES + 1) + "\n", encoding="utf-8")

    verification = audit.verify()

    assert not verification.valid
    assert verification.total_entries == 0
    assert "record size exceeded" in verification.reason


def test_audit_rejects_invalid_utf8_as_failed_integrity(tmp_path):
    audit = GuardianAuditStore(tmp_path)
    audit.path.parent.mkdir(parents=True)
    audit.path.write_bytes(b"\xff\xfe\n")

    verification = audit.verify()

    assert not verification.valid
    assert verification.total_entries == 0
    assert "UnicodeDecodeError" in verification.reason


def test_audit_capacity_rolls_over_without_losing_history(tmp_path):
    runner = RecordingRunner()
    audit = GuardianAuditStore(tmp_path)
    audit.MAX_RECORDS = 2
    gateway = ExecutionGateway(MilestoneOnePolicy(), runner, audit)
    gateway.execute(device_request("FIRST"))
    gateway.execute(device_request("SECOND"))

    gateway.execute(device_request("THIRD"))

    assert len(runner.calls) == 3
    assert audit.verify().valid
    assert audit.verify().total_entries == 2
    archive = next(audit.archive_dir.glob("guardian-audit-*.jsonl"))
    assert '"sequence":1' in archive.read_text(encoding="utf-8")
    records = tuple(reversed(audit.read_recent()))
    assert records[0]["operation_id"] == "guardian.audit.rollover"
    assert records[0]["rollover"]["archive_sha256"] == audit._file_sha256(archive)
    assert records[1]["operation_id"] == "adb.identity"


def test_assert_ready_losslessly_rolls_over_a_valid_legacy_oversized_ledger(tmp_path):
    runner = RecordingRunner()
    audit = GuardianAuditStore(tmp_path)
    gateway = ExecutionGateway(MilestoneOnePolicy(), runner, audit)
    for serial in ("FIRST", "SECOND", "THIRD"):
        gateway.execute(device_request(serial))
    original = audit.path.read_bytes()
    original_verification = audit.verify()
    audit.MAX_FILE_BYTES = len(original) - 1

    audit.assert_ready()

    archive = next(audit.archive_dir.glob("guardian-audit-*.jsonl"))
    assert archive.read_bytes() == original
    assert audit._file_sha256(archive) == audit.read_recent()[0]["rollover"]["archive_sha256"]
    assert audit.read_recent()[0]["rollover"]["archived_last_hash"] == (
        original_verification.last_hash
    )
    assert audit.verify().valid


def test_legacy_oversized_tampered_ledger_still_fails_closed(tmp_path):
    runner = RecordingRunner()
    audit = GuardianAuditStore(tmp_path)
    gateway = ExecutionGateway(MilestoneOnePolicy(), runner, audit)
    gateway.execute(device_request())
    audit.path.write_text(
        audit.path.read_text(encoding="utf-8").replace('"allowed":true', '"allowed":false'),
        encoding="utf-8",
    )
    audit.MAX_FILE_BYTES = audit.path.stat().st_size - 1

    with pytest.raises(AuditIntegrityError, match="failed verification"):
        audit.assert_ready()

    assert not audit.archive_dir.exists()


def test_archived_ledger_tampering_invalidates_the_live_chain_without_restart(tmp_path):
    runner = RecordingRunner()
    audit = GuardianAuditStore(tmp_path)
    audit.MAX_RECORDS = 2
    gateway = ExecutionGateway(MilestoneOnePolicy(), runner, audit)
    gateway.execute(device_request("FIRST"))
    gateway.execute(device_request("SECOND"))
    gateway.execute(device_request("THIRD"))
    archive = next(audit.archive_dir.glob("guardian-audit-*.jsonl"))
    archive.write_text(
        archive.read_text(encoding="utf-8").replace('"allowed":true', '"allowed":false', 1),
        encoding="utf-8",
    )

    verification = audit.verify()

    assert not verification.valid
    assert "archive digest mismatch" in verification.reason
    with pytest.raises(AuditIntegrityError, match="archive digest mismatch"):
        gateway.execute(device_request("FOURTH"))
    assert len(runner.calls) == 3


def test_multiple_rollovers_verify_the_oldest_archive_recursively(tmp_path):
    runner = RecordingRunner()
    audit = GuardianAuditStore(tmp_path)
    audit.MAX_RECORDS = 2
    gateway = ExecutionGateway(MilestoneOnePolicy(), runner, audit)
    for serial in ("FIRST", "SECOND", "THIRD", "FOURTH"):
        gateway.execute(device_request(serial))
    archives = sorted(audit.archive_dir.glob("guardian-audit-*.jsonl"))
    assert len(archives) == 2
    oldest = next(
        path
        for path in archives
        if '"operation_id":"guardian.audit.rollover"' not in path.read_text()
    )
    oldest.write_text(oldest.read_text().replace('"allowed":true', '"allowed":false', 1))

    verification = GuardianAuditStore(tmp_path).verify()

    assert not verification.valid
    assert "archive digest mismatch" in verification.reason
