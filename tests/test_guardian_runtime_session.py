from __future__ import annotations

import base64
import hashlib
import inspect
import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from romverse.device.models import DeviceState
from romverse.guardian.consent_capability import (
    ConsentCapabilityReservationError,
    GuardianConsentCapabilityReservationService,
)
from romverse.guardian.final_consent import GuardianFinalConsentReceiptService
from romverse.guardian.live_target_receipt import GuardianLiveTargetReceiptService
from romverse.guardian.runtime_session import (
    GuardianRuntimeSessionService,
    RuntimeSessionValidationError,
)
from tests.test_guardian_execution_gateway_contract import _service as gateway_service
from tests.test_guardian_execution_plan import _prepared_with_transition_recovery
from tests.test_guardian_final_consent import _trust
from tests.test_guardian_live_target_receipt import _AdbFixture, _FastbootFixture

_LIVE_AT = datetime(2026, 9, 3, 22, 0, tzinfo=UTC)
_SESSION_AT = _LIVE_AT + timedelta(seconds=15)
_CONSENT_AT = _LIVE_AT + timedelta(seconds=25)
_RESERVE_AT = _LIVE_AT + timedelta(seconds=30)


@pytest.fixture
def runtime_context(tmp_path, monkeypatch):
    plans, project, report, device, *_rest = _prepared_with_transition_recovery(
        tmp_path,
        monkeypatch,
    )
    reviewed = replace(
        device,
        state=DeviceState.DEVICE,
        build_id="CURRENT.BUILD",
        build_fingerprint="test/product/current-build:user/release-keys",
    )
    plan = plans.compile(project.project_id, report, reviewed)
    gateway = gateway_service(plans).compile(project.project_id, report, reviewed)
    live_service = GuardianLiveTargetReceiptService(
        plans.store,
        _AdbFixture(),
        _FastbootFixture(),
        clock=lambda: _LIVE_AT,
    )
    live = live_service.observe(gateway, reviewed)
    private_key = Ed25519PrivateKey.generate()
    trust = _trust(private_key, gateway)
    session_clock = [_SESSION_AT]
    sessions = GuardianRuntimeSessionService(
        plans.store,
        live_service,
        clock=lambda: session_clock[0],
    )
    consents = GuardianFinalConsentReceiptService(
        plans.store,
        plans,
        live_service,
        clock=lambda: _CONSENT_AT,
    )
    reservations = GuardianConsentCapabilityReservationService(
        plans.store,
        consents,
        sessions,
        clock=lambda: _RESERVE_AT,
    )
    return {
        "plans": plans,
        "plan": plan,
        "gateway": gateway,
        "live": live,
        "reviewed": reviewed,
        "private_key": private_key,
        "trust": trust,
        "sessions": sessions,
        "session_clock": session_clock,
        "consents": consents,
        "reservations": reservations,
    }


def _canonical(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _digest(payload: object) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _signed_envelope(context, challenge, **changes):
    gateway = context["gateway"]
    live = context["live"]
    trust = context["trust"]
    payload = {
        "schema_version": 1,
        "session_id": "a" * 32,
        "responded_at": (_SESSION_AT + timedelta(seconds=1)).isoformat(),
        "expires_at": challenge.expires_at,
        "challenge_id": challenge.challenge_id,
        "challenge_digest": challenge.challenge_digest,
        "project_id": gateway.project_id,
        "gateway_contract_digest": gateway.contract_digest,
        "live_target_receipt_digest": live.receipt_digest,
        "device_key": gateway.device_key,
        "runtime_trust_digest": _digest(asdict(trust)),
        "runtime_signer_key_id": trust.key_id,
        "runtime_public_key_sha256": trust.public_key_sha256,
        "runtime_adapter_id": trust.adapter_id,
        "runtime_adapter_version": trust.adapter_version,
        "runtime_adapter_sha256": trust.adapter_sha256,
        "runtime_platform": "linux",
        "runtime_architecture": "x86_64",
        "runtime_protocol_version": 1,
        "result_receipt_schema_version": gateway.result_receipt_schema_version,
        "runtime_instance_nonce_sha256": hashlib.sha256(b"fixture-instance").hexdigest(),
        "accepts_exact_gateway": True,
        "accepts_forward_scope_only": True,
        "automatic_recovery_enabled": False,
        "automatic_wipe_enabled": False,
        "bootloader_relock_enabled": False,
        "execution_authority": "none",
        "device_access_opened": False,
        "phone_changed": False,
    }
    payload.update(changes)
    payload["attestation_digest"] = _digest(payload)
    encoded = _canonical(payload)
    private_key = context["private_key"]
    return {
        "format": context["sessions"].SESSION_FORMAT,
        "schema_version": 1,
        "algorithm": "ed25519",
        "key_id": context["trust"].key_id,
        "attestation_sha256": hashlib.sha256(encoded).hexdigest(),
        "attestation": payload,
        "signature": base64.b64encode(
            private_key.sign(context["sessions"].DOMAIN + encoded)
        ).decode("ascii"),
    }


def _issue_session(context):
    sessions = context["sessions"]
    challenge = sessions.issue_challenge(
        context["gateway"],
        context["live"],
        context["reviewed"],
        context["trust"],
        context["private_key"].public_key(),
    )
    envelope = _signed_envelope(context, challenge)
    context["session_clock"][0] = _SESSION_AT + timedelta(seconds=2)
    session = sessions.accept(
        envelope,
        challenge,
        context["gateway"],
        context["live"],
        context["reviewed"],
        context["trust"],
        context["private_key"].public_key(),
    )
    return challenge, envelope, session


def _issue_consent(context):
    service = context["consents"]
    return service.issue(
        context["gateway"],
        context["plan"],
        context["live"],
        context["reviewed"],
        context["trust"],
        context["private_key"].public_key(),
        service.required_acknowledgements(context["plan"], context["gateway"]),
        service.confirmation_phrase(context["plan"], context["live"]),
    )


def test_runtime_session_binds_exact_challenge_target_gateway_and_runtime(
    runtime_context,
) -> None:
    challenge, _envelope, session = _issue_session(runtime_context)
    attestation = session.attestation

    assert challenge.execution_authority == "none"
    assert not challenge.runtime_invoked
    assert not challenge.phone_changed
    assert attestation.challenge_digest == challenge.challenge_digest
    assert attestation.gateway_contract_digest == runtime_context["gateway"].contract_digest
    assert attestation.live_target_receipt_digest == runtime_context["live"].receipt_digest
    assert attestation.runtime_trust_digest == _digest(asdict(runtime_context["trust"]))
    assert attestation.accepts_exact_gateway
    assert attestation.accepts_forward_scope_only
    assert not attestation.device_access_opened
    assert not attestation.phone_changed
    assert session.challenge_claimed_once
    assert (
        runtime_context["sessions"].load(
            runtime_context["gateway"],
            runtime_context["live"],
            runtime_context["reviewed"],
            runtime_context["trust"],
            runtime_context["private_key"].public_key(),
            now=_SESSION_AT + timedelta(seconds=3),
        )
        == session
    )

    root = (
        runtime_context["plans"].store.projects_root
        / runtime_context["gateway"].project_id
        / "guardian"
    )
    saved = "\n".join(
        path.read_text(encoding="utf-8")
        for path in root.glob("runtime-*.romverse")
        if path.is_file()
    )
    assert runtime_context["reviewed"].serial not in saved


def test_runtime_session_rejects_resigned_unsafe_claim_wrong_key_and_extra_field(
    runtime_context,
) -> None:
    sessions = runtime_context["sessions"]
    challenge = sessions.issue_challenge(
        runtime_context["gateway"],
        runtime_context["live"],
        runtime_context["reviewed"],
        runtime_context["trust"],
        runtime_context["private_key"].public_key(),
    )
    runtime_context["session_clock"][0] = _SESSION_AT + timedelta(seconds=2)

    unsafe = _signed_envelope(runtime_context, challenge, device_access_opened=True)
    with pytest.raises(RuntimeSessionValidationError, match="safety validation"):
        sessions.accept(
            unsafe,
            challenge,
            runtime_context["gateway"],
            runtime_context["live"],
            runtime_context["reviewed"],
            runtime_context["trust"],
            runtime_context["private_key"].public_key(),
        )

    wrong_key = Ed25519PrivateKey.generate()
    envelope = _signed_envelope(runtime_context, challenge)
    encoded = _canonical(envelope["attestation"])
    envelope["signature"] = base64.b64encode(wrong_key.sign(sessions.DOMAIN + encoded)).decode(
        "ascii"
    )
    with pytest.raises(RuntimeSessionValidationError, match="signature verification"):
        sessions.accept(
            envelope,
            challenge,
            runtime_context["gateway"],
            runtime_context["live"],
            runtime_context["reviewed"],
            runtime_context["trust"],
            runtime_context["private_key"].public_key(),
        )

    envelope = _signed_envelope(runtime_context, challenge)
    envelope["unexpected"] = True
    with pytest.raises(RuntimeSessionValidationError, match="fields do not match"):
        sessions.accept(
            envelope,
            challenge,
            runtime_context["gateway"],
            runtime_context["live"],
            runtime_context["reviewed"],
            runtime_context["trust"],
            runtime_context["private_key"].public_key(),
        )


def test_runtime_session_accepts_only_one_concurrent_response(runtime_context) -> None:
    sessions = runtime_context["sessions"]
    challenge = sessions.issue_challenge(
        runtime_context["gateway"],
        runtime_context["live"],
        runtime_context["reviewed"],
        runtime_context["trust"],
        runtime_context["private_key"].public_key(),
    )
    envelope = _signed_envelope(runtime_context, challenge)
    runtime_context["session_clock"][0] = _SESSION_AT + timedelta(seconds=2)

    def attempt(_number: int) -> str:
        try:
            sessions.accept(
                envelope,
                challenge,
                runtime_context["gateway"],
                runtime_context["live"],
                runtime_context["reviewed"],
                runtime_context["trust"],
                runtime_context["private_key"].public_key(),
            )
            return "accepted"
        except RuntimeSessionValidationError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=12) as pool:
        outcomes = tuple(pool.map(attempt, range(24)))
    assert outcomes.count("accepted") == 1
    assert outcomes.count("rejected") == 23


def test_runtime_session_stale_tampered_duplicate_or_linked_evidence_fails_closed(
    runtime_context,
) -> None:
    challenge, _envelope, _session = _issue_session(runtime_context)
    sessions = runtime_context["sessions"]
    root = (
        runtime_context["plans"].store.projects_root
        / runtime_context["gateway"].project_id
        / "guardian"
    )
    session_path = root / sessions.SESSION_NAME
    original = session_path.read_text(encoding="utf-8")
    claim_path = root / f"runtime-handshake-claim-{challenge.challenge_id}.romverse"
    original_claim = claim_path.read_text(encoding="utf-8")

    claim_data = json.loads(original_claim)
    claim_data["exclusive_claim_recorded"] = False
    claim_unsigned = dict(claim_data)
    claim_unsigned.pop("format")
    claim_unsigned.pop("claim_digest")
    claim_data["claim_digest"] = _digest(claim_unsigned)
    claim_path.write_text(json.dumps(claim_data), encoding="utf-8")
    assert (
        sessions.load(
            runtime_context["gateway"],
            runtime_context["live"],
            runtime_context["reviewed"],
            runtime_context["trust"],
            runtime_context["private_key"].public_key(),
            now=_SESSION_AT + timedelta(seconds=3),
        )
        is None
    )
    claim_path.write_text(original_claim, encoding="utf-8")

    data = json.loads(original)
    data["attestation"]["phone_changed"] = True
    session_path.write_text(json.dumps(data), encoding="utf-8")
    assert (
        sessions.load(
            runtime_context["gateway"],
            runtime_context["live"],
            runtime_context["reviewed"],
            runtime_context["trust"],
            runtime_context["private_key"].public_key(),
            now=_SESSION_AT + timedelta(seconds=3),
        )
        is None
    )

    session_path.write_text(
        original.replace('"schema_version": 1,', '"schema_version": 1, "schema_version": 1,'),
        encoding="utf-8",
    )
    assert (
        sessions.load(
            runtime_context["gateway"],
            runtime_context["live"],
            runtime_context["reviewed"],
            runtime_context["trust"],
            runtime_context["private_key"].public_key(),
            now=_SESSION_AT + timedelta(seconds=3),
        )
        is None
    )

    if os.name != "nt":
        ordinary = root / "ordinary-runtime-session.json"
        ordinary.write_text(original, encoding="utf-8")
        session_path.unlink()
        session_path.symlink_to(ordinary.name)
        assert (
            sessions.load(
                runtime_context["gateway"],
                runtime_context["live"],
                runtime_context["reviewed"],
                runtime_context["trust"],
                runtime_context["private_key"].public_key(),
                now=_SESSION_AT + timedelta(seconds=3),
            )
            is None
        )

    runtime_context["session_clock"][0] = datetime.fromisoformat(challenge.expires_at) + timedelta(
        microseconds=1
    )
    with pytest.raises(RuntimeSessionValidationError, match="no longer current"):
        sessions.accept(
            _signed_envelope(runtime_context, challenge),
            challenge,
            runtime_context["gateway"],
            runtime_context["live"],
            runtime_context["reviewed"],
            runtime_context["trust"],
            runtime_context["private_key"].public_key(),
        )


def test_consent_capability_reservation_binds_grant_to_exact_runtime_session(
    runtime_context,
) -> None:
    _challenge, _envelope, session = _issue_session(runtime_context)
    grant = _issue_consent(runtime_context)
    service = runtime_context["reservations"]
    reservation = service.reserve(
        grant,
        session,
        runtime_context["gateway"],
        runtime_context["plan"],
        runtime_context["live"],
        runtime_context["reviewed"],
        runtime_context["trust"],
        runtime_context["private_key"].public_key(),
    )

    assert reservation.final_consent_receipt_digest == grant.receipt.receipt_digest
    assert (
        reservation.ephemeral_grant_token_sha256
        == hashlib.sha256(grant.ephemeral_token.encode("utf-8")).hexdigest()
    )
    assert reservation.runtime_session_id == session.attestation.session_id
    assert reservation.exclusive_reservation_recorded
    assert not reservation.ephemeral_grant_token_persisted
    assert not reservation.runtime_consumption_completed
    assert not reservation.execution_grant_issued
    assert reservation.execution_authority == "none"
    assert not reservation.device_access_opened
    assert not reservation.runtime_invoked
    assert not reservation.phone_changed
    assert (
        service.load(
            grant,
            session,
            runtime_context["gateway"],
            runtime_context["plan"],
            runtime_context["live"],
            runtime_context["reviewed"],
            runtime_context["trust"],
            runtime_context["private_key"].public_key(),
            now=_RESERVE_AT + timedelta(seconds=1),
        )
        == reservation
    )

    path = (
        runtime_context["plans"].store.projects_root
        / runtime_context["gateway"].project_id
        / "guardian"
        / f"consent-capability-reservation-{grant.receipt.consent_id}.romverse"
    )
    saved = path.read_text(encoding="utf-8")
    assert grant.ephemeral_token not in saved
    assert grant.receipt.ephemeral_grant_token_sha256 in saved
    assert runtime_context["reviewed"].serial not in saved


def test_consent_capability_can_be_reserved_exactly_once_under_concurrency(
    runtime_context,
) -> None:
    _challenge, _envelope, session = _issue_session(runtime_context)
    grant = _issue_consent(runtime_context)
    service = runtime_context["reservations"]

    def attempt(_number: int) -> str:
        try:
            service.reserve(
                grant,
                session,
                runtime_context["gateway"],
                runtime_context["plan"],
                runtime_context["live"],
                runtime_context["reviewed"],
                runtime_context["trust"],
                runtime_context["private_key"].public_key(),
            )
            return "reserved"
        except ConsentCapabilityReservationError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=12) as pool:
        outcomes = tuple(pool.map(attempt, range(24)))
    assert outcomes.count("reserved") == 1
    assert outcomes.count("rejected") == 23


def test_consent_capability_rejects_wrong_token_session_tamper_and_link(runtime_context) -> None:
    _challenge, _envelope, session = _issue_session(runtime_context)
    grant = _issue_consent(runtime_context)
    service = runtime_context["reservations"]

    with pytest.raises(ConsentCapabilityReservationError, match="failed closed"):
        service.reserve(
            replace(grant, ephemeral_token="0" * 64),
            session,
            runtime_context["gateway"],
            runtime_context["plan"],
            runtime_context["live"],
            runtime_context["reviewed"],
            runtime_context["trust"],
            runtime_context["private_key"].public_key(),
        )

    with pytest.raises(ConsentCapabilityReservationError, match="failed closed"):
        service.reserve(
            grant,
            replace(session, signer_key_id="different-runtime"),
            runtime_context["gateway"],
            runtime_context["plan"],
            runtime_context["live"],
            runtime_context["reviewed"],
            runtime_context["trust"],
            runtime_context["private_key"].public_key(),
        )

    reservation = service.reserve(
        grant,
        session,
        runtime_context["gateway"],
        runtime_context["plan"],
        runtime_context["live"],
        runtime_context["reviewed"],
        runtime_context["trust"],
        runtime_context["private_key"].public_key(),
    )
    path = (
        runtime_context["plans"].store.projects_root
        / runtime_context["gateway"].project_id
        / "guardian"
        / f"consent-capability-reservation-{grant.receipt.consent_id}.romverse"
    )
    original = path.read_text(encoding="utf-8")
    data = json.loads(original)
    data["execution_authority"] = "device-write"
    unsigned = dict(data)
    unsigned.pop("format")
    unsigned.pop("reservation_digest")
    data["reservation_digest"] = _digest(unsigned)
    path.write_text(json.dumps(data), encoding="utf-8")
    assert (
        service.load(
            grant,
            session,
            runtime_context["gateway"],
            runtime_context["plan"],
            runtime_context["live"],
            runtime_context["reviewed"],
            runtime_context["trust"],
            runtime_context["private_key"].public_key(),
            now=_RESERVE_AT + timedelta(seconds=1),
        )
        is None
    )

    if os.name != "nt":
        ordinary = path.with_name("ordinary-reservation.json")
        ordinary.write_text(original, encoding="utf-8")
        path.unlink()
        path.symlink_to(ordinary.name)
        assert (
            service.load(
                grant,
                session,
                runtime_context["gateway"],
                runtime_context["plan"],
                runtime_context["live"],
                runtime_context["reviewed"],
                runtime_context["trust"],
                runtime_context["private_key"].public_key(),
                now=_RESERVE_AT + timedelta(seconds=1),
            )
            is None
        )

    assert reservation.execution_authority == "none"


def test_runtime_session_and_reservation_have_no_execution_or_signing_surface() -> None:
    forbidden = {
        "execute",
        "flash",
        "reboot",
        "erase",
        "unlock",
        "relock",
        "sign",
        "consume",
        "run",
    }
    for service in (
        GuardianRuntimeSessionService,
        GuardianConsentCapabilityReservationService,
    ):
        assert set(dir(service)).isdisjoint(forbidden)
        source = inspect.getsource(service)
        assert "subprocess" not in source
        assert "Ed25519PrivateKey" not in source
