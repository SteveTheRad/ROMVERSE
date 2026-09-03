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

from romverse.guardian.runtime_execution_claim import (
    GuardianRuntimeExecutionClaimService,
    RuntimeExecutionClaimError,
)
from tests.test_guardian_runtime_authorization import (
    _CONSUME_AT,
    _consume,
    _prepared,
)

pytest_plugins = ("tests.test_guardian_runtime_session",)

_CLAIM_AT = _CONSUME_AT + timedelta(seconds=1)


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


def _ready(context):
    authorizations, grant, reservation, session = _prepared(context)
    runtime_grant = _consume(authorizations, context, grant, reservation, session)
    claims = GuardianRuntimeExecutionClaimService(
        context["plans"].store,
        authorizations,
        clock=lambda: _CLAIM_AT,
    )
    return claims, runtime_grant, grant, reservation, session


def _claim(claims, context, runtime_grant, grant, reservation, session):
    return claims.claim(
        runtime_grant,
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


def _load(
    claims,
    context,
    runtime_grant,
    grant,
    reservation,
    session,
    *,
    now=_CLAIM_AT,
):
    return claims.load(
        runtime_grant,
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


def _path(context, runtime_grant):
    execution_grant_id = runtime_grant.verified_consumption.consumption.execution_grant_id
    return (
        context["plans"].store.projects_root
        / context["gateway"].project_id
        / "guardian"
        / f"runtime-execution-claim-{execution_grant_id}.romverse"
    )


def test_execution_grant_claim_is_exact_private_and_memory_only(runtime_context) -> None:
    claims, runtime_grant, grant, reservation, session = _ready(runtime_context)

    permit = _claim(claims, runtime_context, runtime_grant, grant, reservation, session)
    claim = permit.verified_claim.claim
    gateway = runtime_context["gateway"]
    live = runtime_context["live"]

    assert claim.gateway_contract_digest == gateway.contract_digest
    assert claim.runtime_consumption_digest == (
        runtime_grant.verified_consumption.consumption.consumption_digest
    )
    assert claim.execution_grant_claimed_once
    assert claim.exclusive_execution_claim_recorded
    assert claim.forward_step_count == gateway.step_count
    assert claim.forward_steps_digest == gateway.steps_digest
    assert claim.first_step_operation_id == gateway.steps[0].operation_id
    assert claim.first_step_transport == gateway.steps[0].transport.value
    assert claim.expected_entry_mode == live.observed_entry_mode
    assert claim.expected_product == live.observed_product
    assert claim.expected_unlocked
    assert claim.recorded_prewrite_slot == live.recorded_prewrite_slot
    assert claim.device_open_authority == "exact-reviewed-target-open-once"
    assert claim.forward_scope_only
    assert not claim.recovery_authority_granted
    assert not claim.wipe_authority_granted
    assert not claim.automatic_recovery_enabled
    assert not claim.automatic_wipe_enabled
    assert not claim.bootloader_relock_allowed
    assert not claim.device_access_opened
    assert not claim.first_forward_step_started
    assert not claim.phone_changed
    assert hashlib.sha256(permit.ephemeral_open_token.encode()).hexdigest() == (
        claim.device_open_permit_token_sha256
    )
    assert permit.ephemeral_open_token not in repr(permit)
    assert permit.target_serial not in repr(permit)

    claims.validate_in_memory_permit(
        permit,
        runtime_grant,
        grant,
        reservation,
        session,
        gateway,
        runtime_context["plan"],
        live,
        runtime_context["reviewed"],
        runtime_context["trust"],
        runtime_context["private_key"].public_key(),
        now=_CLAIM_AT,
    )
    assert (
        _load(
            claims,
            runtime_context,
            runtime_grant,
            grant,
            reservation,
            session,
        )
        == permit.verified_claim
    )

    saved = _path(runtime_context, runtime_grant).read_text(encoding="utf-8")
    assert runtime_grant.ephemeral_execution_token not in saved
    assert permit.ephemeral_open_token not in saved
    assert runtime_context["reviewed"].serial not in saved
    assert "private_key" not in saved
    assert claim.device_open_permit_token_sha256 in saved
    if os.name != "nt":
        assert stat.S_IMODE(_path(runtime_context, runtime_grant).stat().st_mode) == 0o600
        assert stat.S_IMODE(_path(runtime_context, runtime_grant).parent.stat().st_mode) == 0o700


def test_execution_grant_claim_has_one_concurrent_winner(runtime_context) -> None:
    claims, runtime_grant, grant, reservation, session = _ready(runtime_context)

    def attempt(_number: int) -> str:
        try:
            _claim(claims, runtime_context, runtime_grant, grant, reservation, session)
            return "claimed"
        except RuntimeExecutionClaimError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=12) as pool:
        outcomes = tuple(pool.map(attempt, range(24)))

    assert outcomes.count("claimed") == 1
    assert outcomes.count("rejected") == 23


def test_execution_claim_rejects_wrong_grant_token_and_private_key(runtime_context) -> None:
    claims, runtime_grant, grant, reservation, session = _ready(runtime_context)
    wrong_grant = replace(runtime_grant, ephemeral_execution_token="0" * 64)

    with pytest.raises(RuntimeExecutionClaimError, match="failed closed"):
        _claim(claims, runtime_context, wrong_grant, grant, reservation, session)
    assert not _path(runtime_context, runtime_grant).exists()

    with pytest.raises(RuntimeExecutionClaimError, match="does not match the enrolled runtime"):
        claims.claim(
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
            Ed25519PrivateKey.generate(),
        )
    assert not _path(runtime_context, runtime_grant).exists()

    _claim(claims, runtime_context, runtime_grant, grant, reservation, session)


def test_execution_claim_rejects_resigned_unsafe_tamper_duplicate_and_link(
    runtime_context,
) -> None:
    claims, runtime_grant, grant, reservation, session = _ready(runtime_context)
    permit = _claim(claims, runtime_context, runtime_grant, grant, reservation, session)
    path = _path(runtime_context, runtime_grant)
    original = path.read_text(encoding="utf-8")
    envelope = json.loads(original)
    payload = envelope["claim"]
    payload["device_access_opened"] = True
    unsigned = dict(payload)
    unsigned.pop("claim_digest")
    payload["claim_digest"] = _digest(unsigned)
    encoded = _canonical(payload)
    envelope["claim_sha256"] = hashlib.sha256(encoded).hexdigest()
    envelope["signature"] = base64.b64encode(
        runtime_context["private_key"].sign(claims.DOMAIN + encoded)
    ).decode("ascii")
    path.write_text(json.dumps(envelope), encoding="utf-8")

    assert (
        _load(
            claims,
            runtime_context,
            runtime_grant,
            grant,
            reservation,
            session,
        )
        is None
    )
    with pytest.raises(RuntimeExecutionClaimError, match="no longer current"):
        claims.validate_in_memory_permit(
            permit,
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
            now=_CLAIM_AT,
        )

    path.write_text(original, encoding="utf-8")
    duplicate = original.replace(
        '"format": "romverse.guardian-runtime-execution-claim",',
        '"format": "romverse.guardian-runtime-execution-claim",\n  '
        '"format": "romverse.guardian-runtime-execution-claim",',
        1,
    )
    path.write_text(duplicate, encoding="utf-8")
    assert (
        _load(
            claims,
            runtime_context,
            runtime_grant,
            grant,
            reservation,
            session,
        )
        is None
    )

    if os.name != "nt":
        ordinary = path.with_name("ordinary-runtime-execution-claim.json")
        ordinary.write_text(original, encoding="utf-8")
        path.unlink()
        path.symlink_to(ordinary.name)
        assert (
            _load(
                claims,
                runtime_context,
                runtime_grant,
                grant,
                reservation,
                session,
            )
            is None
        )


def test_execution_claim_expires_and_has_no_device_runner_surface(runtime_context) -> None:
    claims, runtime_grant, grant, reservation, session = _ready(runtime_context)
    permit = _claim(claims, runtime_context, runtime_grant, grant, reservation, session)
    expired = permit.verified_claim.claim.expires_at.replace("Z", "+00:00")
    expired_at = datetime.fromisoformat(expired) + timedelta(microseconds=1)

    assert (
        _load(
            claims,
            runtime_context,
            runtime_grant,
            grant,
            reservation,
            session,
            now=expired_at,
        )
        is None
    )
    forbidden = {"execute", "flash", "reboot", "erase", "unlock", "relock", "run", "open"}
    assert set(dir(GuardianRuntimeExecutionClaimService)).isdisjoint(forbidden)
    source = inspect.getsource(GuardianRuntimeExecutionClaimService)
    assert "subprocess" not in source
    assert "CommandRunner" not in source
    assert not permit.verified_claim.claim.device_access_opened
    assert not permit.verified_claim.claim.phone_changed
