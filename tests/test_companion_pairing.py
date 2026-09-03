import hashlib
import json
import os
import stat
from datetime import UTC, datetime

from romverse.companion.pairing import (
    PairingSessionBroker,
    create_pairing_code,
    verify_pairing_code,
)


def test_pairing_code_is_six_digits_and_not_expired() -> None:
    pairing = create_pairing_code()
    assert len(pairing.code) == 6
    assert pairing.code.isdigit()
    assert not pairing.expired
    assert datetime.fromisoformat(pairing.expires_at).tzinfo == UTC


def test_pairing_ttl_is_clamped_to_at_least_one_minute() -> None:
    pairing = create_pairing_code(0)
    assert datetime.fromisoformat(pairing.expires_at) > datetime.fromisoformat(pairing.created_at)


def test_pairing_code_verifier_accepts_spaced_code_and_rejects_wrong_shape() -> None:
    pairing = create_pairing_code()
    assert verify_pairing_code(pairing, f"{pairing.code[:3]} {pairing.code[3:]}")
    assert not verify_pairing_code(pairing, pairing.code[:-1])
    assert not verify_pairing_code(pairing, "abcdef")


def test_session_broker_requires_request_then_approval_and_token() -> None:
    pairing = create_pairing_code()
    broker = PairingSessionBroker()

    request_id = broker.request(pairing, pairing.code)
    assert request_id
    assert broker.pending
    assert broker.status("wrong-request").state == "rejected"
    assert broker.status(request_id).state == "pending"
    assert not broker.authorize("not-a-token")

    assert broker.approve()
    approved = broker.status(request_id)
    assert approved.state == "approved"
    assert approved.expires_in_seconds > 0
    assert broker.authorize(approved.session_token)


def test_session_broker_reset_revokes_the_approved_token() -> None:
    pairing = create_pairing_code()
    broker = PairingSessionBroker()
    request_id = broker.request(pairing, pairing.code)
    assert broker.approve()
    token = broker.status(request_id).session_token

    broker.reset()

    assert not broker.pending
    assert not broker.approved
    assert not broker.authorize(token)
    assert broker.status(request_id).state == "rejected"


def test_session_broker_expires_tokens() -> None:
    now = [100.0]
    pairing = create_pairing_code()
    broker = PairingSessionBroker(ttl_seconds=60, clock=lambda: now[0])
    request_id = broker.request(pairing, pairing.code)
    assert broker.approve()
    token = broker.status(request_id).session_token

    now[0] += 61

    assert not broker.authorize(token)
    assert not broker.approved
    assert broker.status(request_id).state == "pending"


def test_session_broker_throttles_failures_per_client_then_recovers() -> None:
    now = [100.0]
    pairing = create_pairing_code()
    broker = PairingSessionBroker(clock=lambda: now[0])
    wrong_code = "999999" if pairing.code != "999999" else "888888"

    for _ in range(broker.MAX_FAILED_ATTEMPTS):
        assert broker.request(pairing, wrong_code, "attacker") == ""

    assert broker.request(pairing, pairing.code, "attacker") == ""
    assert broker.request(pairing, pairing.code, "trusted-phone")

    now[0] += broker.FAILURE_WINDOW_SECONDS + 1
    assert broker.request(pairing, pairing.code, "attacker")


def test_session_broker_remembers_only_a_token_digest_across_restart(tmp_path) -> None:
    now = [1_788_000_000.0]
    state_path = tmp_path / "remembered-session.romverse"
    pairing = create_pairing_code()
    broker = PairingSessionBroker(
        ttl_seconds=600,
        clock=lambda: now[0],
        state_path=state_path,
    )
    request_id = broker.request(pairing, pairing.code)
    assert broker.approve()
    token = broker.status(request_id).session_token

    state_text = state_path.read_text(encoding="utf-8")
    assert token not in state_text
    if os.name != "nt":
        assert state_path.stat().st_mode & 0o777 == 0o600
        assert stat.S_IMODE(state_path.parent.stat().st_mode) == 0o700
    document = json.loads(state_text)
    assert document["schema_version"] == broker.STATE_SCHEMA_VERSION
    unsigned = {key: value for key, value in document.items() if key != "record_digest"}
    assert (
        document["record_digest"]
        == hashlib.sha256(
            json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )

    restarted = PairingSessionBroker(
        ttl_seconds=600,
        clock=lambda: now[0],
        state_path=state_path,
    )
    assert restarted.approved
    assert restarted.authorize(token)
    assert not restarted.authorize("not-the-token")


def test_session_broker_remembered_session_expires_and_reset_revokes(tmp_path) -> None:
    now = [1_788_000_000.0]
    state_path = tmp_path / "remembered-session.romverse"
    pairing = create_pairing_code()
    broker = PairingSessionBroker(
        ttl_seconds=60,
        clock=lambda: now[0],
        state_path=state_path,
    )
    request_id = broker.request(pairing, pairing.code)
    assert broker.approve()
    token = broker.status(request_id).session_token
    assert state_path.is_file()

    now[0] += 61
    restarted = PairingSessionBroker(
        ttl_seconds=60,
        clock=lambda: now[0],
        state_path=state_path,
    )
    assert not restarted.authorize(token)
    assert not state_path.exists()

    now[0] -= 61
    replacement = PairingSessionBroker(
        ttl_seconds=60,
        clock=lambda: now[0],
        state_path=state_path,
    )
    replacement_request = replacement.request(pairing, pairing.code)
    assert replacement.approve()
    assert replacement.status(replacement_request).session_token
    replacement.reset()
    assert not state_path.exists()


def test_remembered_session_rejects_oversize_links_redirects_and_redigested_types(
    tmp_path,
) -> None:
    now = [1_788_000_000.0]
    state_root = tmp_path / "link-state"
    state_path = state_root / "remembered-session.romverse"
    pairing = create_pairing_code()
    broker = PairingSessionBroker(
        ttl_seconds=600,
        clock=lambda: now[0],
        state_path=state_path,
        state_boundary=tmp_path,
    )
    request_id = broker.request(pairing, pairing.code)
    assert broker.approve()
    token = broker.status(request_id).session_token
    original = state_path.read_bytes()

    hostile = json.loads(original)
    hostile["expires_at_epoch_seconds"] = True
    unsigned = {key: value for key, value in hostile.items() if key != "record_digest"}
    hostile["record_digest"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    state_path.write_text(json.dumps(hostile), encoding="utf-8")
    rejected = PairingSessionBroker(
        ttl_seconds=600,
        clock=lambda: now[0],
        state_path=state_path,
        state_boundary=tmp_path,
    )
    assert not rejected.authorize(token)
    assert not state_path.exists()

    state_path.write_bytes(original)
    with state_path.open("r+b") as stream:
        stream.truncate(broker.MAX_STATE_BYTES + 1)
    rejected = PairingSessionBroker(
        ttl_seconds=600,
        clock=lambda: now[0],
        state_path=state_path,
        state_boundary=tmp_path,
    )
    assert not rejected.authorize(token)
    assert not state_path.exists()

    outside_record = tmp_path / "outside-remembered-session.romverse"
    outside_record.write_bytes(original)
    state_path.symlink_to(outside_record)
    rejected = PairingSessionBroker(
        ttl_seconds=600,
        clock=lambda: now[0],
        state_path=state_path,
        state_boundary=tmp_path,
    )
    assert not rejected.authorize(token)
    assert state_path.is_symlink()
    assert outside_record.read_bytes() == original
    state_path.unlink()

    state_path.write_bytes(original)
    saved_root = tmp_path / "link-state-saved"
    state_root.rename(saved_root)
    redirected = tmp_path / "outside-directory"
    redirected.mkdir()
    redirected_record = redirected / state_path.name
    redirected_record.write_bytes(original)
    state_root.symlink_to(redirected, target_is_directory=True)
    rejected = PairingSessionBroker(
        ttl_seconds=600,
        clock=lambda: now[0],
        state_path=state_path,
        state_boundary=tmp_path,
    )
    assert not rejected.authorize(token)
    assert redirected_record.read_bytes() == original


def test_legacy_remembered_session_migrates_to_private_strict_schema_two(tmp_path) -> None:
    now = [1_788_000_000.0]
    token = "legacy-token-" + "x" * 32
    state_path = tmp_path / "remembered-session.romverse"
    state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
                "expires_at_epoch_seconds": now[0] + 300,
            }
        ),
        encoding="utf-8",
    )

    broker = PairingSessionBroker(
        ttl_seconds=600,
        clock=lambda: now[0],
        state_path=state_path,
    )

    assert broker.authorize(token)
    migrated = json.loads(state_path.read_text(encoding="utf-8"))
    assert set(migrated) == {
        "schema_version",
        "token_sha256",
        "expires_at_epoch_seconds",
        "record_digest",
    }
    assert migrated["schema_version"] == 2
    if os.name != "nt":
        assert stat.S_IMODE(state_path.stat().st_mode) == 0o600


def test_linked_remembered_session_target_cannot_capture_new_approval(tmp_path) -> None:
    state_path = tmp_path / "remembered-session.romverse"
    outside = tmp_path / "outside-target.romverse"
    outside.write_text("do not overwrite", encoding="utf-8")
    state_path.symlink_to(outside)
    pairing = create_pairing_code()
    broker = PairingSessionBroker(state_path=state_path, state_boundary=tmp_path)
    broker.request(pairing, pairing.code)

    assert not broker.approve()
    assert outside.read_text(encoding="utf-8") == "do not overwrite"
    assert state_path.is_symlink()
