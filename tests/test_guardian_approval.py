import json
from datetime import UTC, datetime, timedelta

import pytest

from romverse.guardian.approval import ApprovalStore
from romverse.rom.models import ProjectError


def test_approval_store_binds_digest_and_target(tmp_path):
    store = ApprovalStore(tmp_path)
    record = store.issue("digest", "project")
    assert store.is_approved(record.plan_digest, record.target)
    assert not store.is_approved("other", record.target)
    assert store.read_recent(1)[0] == record


def test_approval_store_requires_scope(tmp_path):
    with pytest.raises(ProjectError):
        ApprovalStore(tmp_path).issue("", "project")


def test_approval_expires_after_ten_minutes(tmp_path):
    clock = [datetime(2026, 8, 30, 1, 2, 3, tzinfo=UTC)]
    store = ApprovalStore(tmp_path, lambda: clock[0])
    record = store.issue("digest", "project")

    assert store.is_approved(record.plan_digest, record.target)
    clock[0] += timedelta(minutes=10)
    assert not store.is_approved(record.plan_digest, record.target)
    assert store.verify().active_entries == 0


def test_approval_chain_rejects_tampering(tmp_path):
    store = ApprovalStore(tmp_path)
    store.issue("first", "project")
    store.issue("second", "project")
    lines = store.path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["target"] = "another-project"
    lines[0] = json.dumps(first, sort_keys=True, separators=(",", ":"))
    store.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    verification = store.verify()
    assert not verification.valid
    assert not store.is_approved("second", "project")
    assert store.read_recent() == ()
    with pytest.raises(ProjectError, match="failed integrity"):
        store.issue("third", "project")


def test_legacy_approval_is_audit_only_and_new_chain_preserves_it(tmp_path):
    issued = datetime(2026, 8, 29, 1, 2, 3, tzinfo=UTC).isoformat()
    store = ApprovalStore(tmp_path)
    store.path.parent.mkdir(parents=True)
    store.path.write_text(
        json.dumps(
            {
                "approval_id": "legacy-record",
                "plan_digest": "legacy-plan",
                "target": "project",
                "issued_at": issued,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    assert store.verify().legacy_entries == 1
    assert not store.is_approved("legacy-plan", "project")
    current = store.issue("current-plan", "project")
    assert store.is_approved(current.plan_digest, current.target)
    records = store.read_recent()
    assert records[0] == current
    assert records[1].legacy

    lines = store.path.read_text(encoding="utf-8").splitlines()
    legacy = json.loads(lines[0])
    legacy["plan_digest"] = "altered-legacy-plan"
    lines[0] = json.dumps(legacy, sort_keys=True)
    store.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert not store.verify().valid
