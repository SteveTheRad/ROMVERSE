from __future__ import annotations

import base64
import hashlib
import inspect
import json
import os
import stat
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from romverse.guardian.runtime_authorization import (
    GuardianRuntimeAuthorizationService,
    RuntimeAuthorizationError,
)
from tests.test_guardian_runtime_session import (
    _RESERVE_AT,
    _issue_consent,
    _issue_session,
)

pytest_plugins = ("tests.test_guardian_runtime_session",)

_CONSUME_AT = _RESERVE_AT + timedelta(seconds=1)


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


def _prepared(context):
    _challenge, _envelope, session = _issue_session(context)
    grant = _issue_consent(context)
    reservation = context["reservations"].reserve(
        grant,
        session,
        context["gateway"],
        context["plan"],
        context["live"],
        context["reviewed"],
        context["trust"],
        context["private_key"].public_key(),
    )
    service = GuardianRuntimeAuthorizationService(
        context["plans"].store,
        context["reservations"],
        clock=lambda: _CONSUME_AT,
    )
    return service, grant, reservation, session


def _consume(service, context, grant, reservation, session):
    return service.consume(
        grant,
        reservation,
        session,
        context["gateway"],
        context["plan"],
        context["live"],
        context["reviewed"],
        context["trust"],
        context["private_key"].public_key(),
        context["private_key"],
    )


def _load(service, context, grant, reservation, session, *, now=_CONSUME_AT):
    return service.load(
        grant,
        reservation,
        session,
        context["gateway"],
        context["plan"],
        context["live"],
        context["reviewed"],
        context["trust"],
        context["private_key"].public_key(),
        now=now,
    )


def _path(context, grant):
    return (
        context["plans"].store.projects_root
        / context["gateway"].project_id
        / "guardian"
        / f"runtime-consent-consumption-{grant.receipt.consent_id}.romverse"
    )


def test_runtime_consumes_exact_consent_once_and_returns_only_memory_authority(
    runtime_context,
) -> None:
    service, grant, reservation, session = _prepared(runtime_context)

    runtime_grant = _consume(service, runtime_context, grant, reservation, session)
    consumption = runtime_grant.verified_consumption.consumption

    assert consumption.gateway_contract_digest == runtime_context["gateway"].contract_digest
    assert consumption.plan_digest == runtime_context["plan"].plan_digest
    assert consumption.live_target_receipt_digest == runtime_context["live"].receipt_digest
    assert consumption.final_consent_receipt_digest == grant.receipt.receipt_digest
    assert consumption.reservation_digest == reservation.reservation_digest
    assert consumption.runtime_session_id == session.attestation.session_id
    assert consumption.runtime_consumption_completed
    assert consumption.execution_grant_issued
    assert consumption.execution_authority == "exact-forward-gateway-once"
    assert consumption.forward_scope_only
    assert not consumption.recovery_authority_granted
    assert not consumption.wipe_authority_granted
    assert not consumption.automatic_recovery_enabled
    assert not consumption.automatic_wipe_enabled
    assert not consumption.bootloader_relock_allowed
    assert not consumption.device_access_opened
    assert consumption.runtime_invoked
    assert not consumption.phone_changed
    assert hashlib.sha256(runtime_grant.ephemeral_execution_token.encode()).hexdigest() == (
        consumption.execution_grant_token_sha256
    )
    assert runtime_grant.ephemeral_execution_token not in repr(runtime_grant)

    service.validate_in_memory_grant(
        runtime_grant,
        grant,
        reservation,
        session,
        runtime_context["gateway"],
        runtime_context["plan"],
        runtime_context["live"],
        runtime_context["reviewed"],
        runtime_context["trust"],
        runtime_context["private_key"].public_key(),
        now=_CONSUME_AT,
    )
    assert _load(service, runtime_context, grant, reservation, session) == (
        runtime_grant.verified_consumption
    )

    saved = _path(runtime_context, grant).read_text(encoding="utf-8")
    assert grant.ephemeral_token not in saved
    assert runtime_grant.ephemeral_execution_token not in saved
    assert runtime_context["reviewed"].serial not in saved
    assert "private_key" not in saved
    assert consumption.execution_grant_token_sha256 in saved
    if os.name != "nt":
        assert stat.S_IMODE(_path(runtime_context, grant).stat().st_mode) == 0o600
        assert stat.S_IMODE(_path(runtime_context, grant).parent.stat().st_mode) == 0o700


def test_runtime_consumption_has_exactly_one_winner_under_concurrency(runtime_context) -> None:
    service, grant, reservation, session = _prepared(runtime_context)

    def attempt(_number: int) -> str:
        try:
            _consume(service, runtime_context, grant, reservation, session)
            return "consumed"
        except RuntimeAuthorizationError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=12) as pool:
        outcomes = tuple(pool.map(attempt, range(24)))

    assert outcomes.count("consumed") == 1
    assert outcomes.count("rejected") == 23


def test_runtime_consumption_rejects_wrong_token_or_signing_identity(runtime_context) -> None:
    service, grant, reservation, session = _prepared(runtime_context)
    wrong_grant = replace(grant, ephemeral_token="0" * 64)

    with pytest.raises(RuntimeAuthorizationError, match="current exact consent reservation"):
        _consume(service, runtime_context, wrong_grant, reservation, session)
    assert not _path(runtime_context, grant).exists()

    wrong_private_key = Ed25519PrivateKey.generate()
    with pytest.raises(RuntimeAuthorizationError, match="does not match the enrolled runtime"):
        service.consume(
            grant,
            reservation,
            session,
            runtime_context["gateway"],
            runtime_context["plan"],
            runtime_context["live"],
            runtime_context["reviewed"],
            runtime_context["trust"],
            runtime_context["private_key"].public_key(),
            wrong_private_key,
        )
    assert not _path(runtime_context, grant).exists()

    _consume(service, runtime_context, grant, reservation, session)


def test_runtime_consumption_rejects_resigned_unsafe_claim_tamper_and_link(
    runtime_context,
) -> None:
    service, grant, reservation, session = _prepared(runtime_context)
    runtime_grant = _consume(service, runtime_context, grant, reservation, session)
    path = _path(runtime_context, grant)
    original = path.read_text(encoding="utf-8")
    envelope = json.loads(original)
    payload = envelope["consumption"]
    payload["recovery_authority_granted"] = True
    unsigned = dict(payload)
    unsigned.pop("consumption_digest")
    payload["consumption_digest"] = _digest(unsigned)
    encoded = _canonical(payload)
    envelope["consumption_sha256"] = hashlib.sha256(encoded).hexdigest()
    envelope["signature"] = base64.b64encode(
        runtime_context["private_key"].sign(service.DOMAIN + encoded)
    ).decode("ascii")
    path.write_text(json.dumps(envelope), encoding="utf-8")

    assert _load(service, runtime_context, grant, reservation, session) is None
    with pytest.raises(RuntimeAuthorizationError, match="no longer current"):
        service.validate_in_memory_grant(
            runtime_grant,
            grant,
            reservation,
            session,
            runtime_context["gateway"],
            runtime_context["plan"],
            runtime_context["live"],
            runtime_context["reviewed"],
            runtime_context["trust"],
            runtime_context["private_key"].public_key(),
            now=_CONSUME_AT,
        )

    path.write_text(original, encoding="utf-8")
    duplicate = original.replace(
        '"format": "romverse.guardian-runtime-consent-consumption",',
        '"format": "romverse.guardian-runtime-consent-consumption",\n  '
        '"format": "romverse.guardian-runtime-consent-consumption",',
        1,
    )
    path.write_text(duplicate, encoding="utf-8")
    assert _load(service, runtime_context, grant, reservation, session) is None

    if os.name != "nt":
        ordinary = path.with_name("ordinary-runtime-consumption.json")
        ordinary.write_text(original, encoding="utf-8")
        path.unlink()
        path.symlink_to(ordinary.name)
        assert _load(service, runtime_context, grant, reservation, session) is None


def test_runtime_consumption_expires_with_session_and_has_no_device_runner_surface(
    runtime_context,
) -> None:
    service, grant, reservation, session = _prepared(runtime_context)
    runtime_grant = _consume(service, runtime_context, grant, reservation, session)
    expired = runtime_grant.verified_consumption.consumption.expires_at.replace("Z", "+00:00")
    expired_at = datetime.fromisoformat(expired) + timedelta(microseconds=1)
    assert (
        _load(
            service,
            runtime_context,
            grant,
            reservation,
            session,
            now=expired_at,
        )
        is None
    )

    forbidden = {"execute", "flash", "reboot", "erase", "unlock", "relock", "run"}
    assert set(dir(GuardianRuntimeAuthorizationService)).isdisjoint(forbidden)
    source = inspect.getsource(GuardianRuntimeAuthorizationService)
    assert "subprocess" not in source
    assert "CommandRunner" not in source
    assert "adb" not in source.casefold()
    assert "fastboot" not in source.casefold()
    assert "Ed25519PrivateKey" in source
    assert not runtime_grant.verified_consumption.consumption.device_access_opened
