from __future__ import annotations

import hashlib
import inspect
import json
import os
import stat
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from romverse.device.models import DeviceState
from romverse.guardian.execution_result_receipt import GuardianRuntimeTrust
from romverse.guardian.final_consent import (
    ConsentDataAction,
    FinalConsentValidationError,
    GuardianFinalConsentReceiptService,
)
from romverse.guardian.flash_handoff import FlashMode
from romverse.guardian.live_target_receipt import GuardianLiveTargetReceiptService
from tests.test_guardian_execution_gateway_contract import _service as gateway_service
from tests.test_guardian_execution_plan import (
    _prepared_with_transition_recovery,
)
from tests.test_guardian_live_target_receipt import _AdbFixture, _FastbootFixture

_LIVE_AT = datetime(2026, 9, 3, 21, 0, tzinfo=UTC)
_CONSENT_AT = _LIVE_AT + timedelta(seconds=30)


def _trust(private_key: Ed25519PrivateKey, gateway) -> GuardianRuntimeTrust:
    raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return GuardianRuntimeTrust(
        key_id="guardian-runtime-fixture-2026",
        public_key_sha256=hashlib.sha256(raw).hexdigest(),
        adapter_id="fixture.fastboot.runtime",
        adapter_version=1,
        adapter_sha256="9" * 64,
        device_pack_id=gateway.device_pack_id,
        device_pack_sha256=gateway.device_pack_sha256,
        write_contract_id=gateway.write_contract_id,
        write_contract_version=gateway.write_contract_version,
        write_attestation_sha256=gateway.write_attestation_sha256,
        transition_recovery_contract_digest=gateway.transition_recovery_contract_digest,
    )


@pytest.fixture
def consent_context(tmp_path, monkeypatch):
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
    service = GuardianFinalConsentReceiptService(
        plans.store,
        plans,
        live_service,
        clock=lambda: _CONSENT_AT,
    )
    return service, plan, gateway, live, reviewed, trust, private_key


def _issue(context):
    service, plan, gateway, live, reviewed, trust, private_key = context
    return service.issue(
        gateway,
        plan,
        live,
        reviewed,
        trust,
        private_key.public_key(),
        service.required_acknowledgements(plan, gateway),
        service.confirmation_phrase(plan, live),
    )


def test_final_consent_binds_exact_target_gateway_runtime_and_every_consequence(
    consent_context,
) -> None:
    service, plan, gateway, live, reviewed, trust, private_key = consent_context
    grant = _issue(consent_context)
    receipt = grant.receipt

    assert receipt.gateway_contract_digest == gateway.contract_digest
    assert receipt.plan_digest == plan.plan_digest
    assert receipt.live_target_receipt_digest == live.receipt_digest
    assert receipt.device_key == gateway.device_key
    assert receipt.data_action is ConsentDataAction.KEEP_USER_DATA
    assert receipt.runtime_signer_key_id == trust.key_id
    assert receipt.runtime_adapter_id == trust.adapter_id
    assert (
        receipt.runtime_trust_digest
        == hashlib.sha256(
            json.dumps(asdict(trust), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    assert receipt.forward_step_count == gateway.step_count
    assert receipt.forward_phone_change_count == sum(step.phone_changes for step in gateway.steps)
    assert [item.operation_id for item in receipt.forward_consequences] == [
        step.operation_id for step in gateway.steps
    ]
    assert receipt.recovery_step_count == gateway.recovery_action_count
    assert [item.adapter_action_id for item in receipt.recovery_consequences] == [
        step.adapter_action_id for step in gateway.recovery_steps
    ]
    assert all(not item.separately_consented for item in receipt.recovery_consequences)
    assert receipt.final_consent_recorded
    assert receipt.forward_scope_only
    assert receipt.separate_recovery_consent_required
    assert receipt.separate_wipe_consent_required
    assert not receipt.recovery_consent_recorded
    assert not receipt.wipe_consent_recorded
    assert receipt.runtime_trust_bound
    assert not receipt.ephemeral_grant_token_persisted
    assert not receipt.bootloader_relock_allowed
    assert not receipt.automatic_recovery_allowed
    assert not receipt.automatic_wipe_allowed
    assert receipt.execution_authority == "none"
    assert not receipt.runtime_invoked
    assert not receipt.phone_changed
    assert datetime.fromisoformat(receipt.expires_at) == datetime.fromisoformat(live.expires_at)

    service.validate_grant(
        grant,
        gateway,
        plan,
        live,
        reviewed,
        trust,
        private_key.public_key(),
        now=_CONSENT_AT,
    )
    assert (
        service.load(
            gateway,
            plan,
            live,
            reviewed,
            trust,
            private_key.public_key(),
            now=_CONSENT_AT,
        )
        == receipt
    )


def test_final_consent_persists_no_serial_phrase_or_raw_ephemeral_token(
    consent_context,
) -> None:
    service, _plan, gateway, _live, reviewed, _trust_value, _private_key = consent_context
    grant = _issue(consent_context)
    path = service.store.projects_root / gateway.project_id / "guardian" / service.LATEST_NAME
    serialized = path.read_text(encoding="utf-8")

    assert reviewed.serial not in serialized
    assert grant.ephemeral_token not in serialized
    assert service.confirmation_phrase(consent_context[1], consent_context[3]) not in serialized
    assert grant.receipt.ephemeral_grant_token_sha256 in serialized
    if os.name != "nt":
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_missing_acknowledgement_or_wrong_phrase_fails_closed_and_invalidates_prior(
    consent_context,
) -> None:
    service, plan, gateway, live, reviewed, trust, private_key = consent_context
    _issue(consent_context)
    missing = service.required_acknowledgements(plan, gateway) - {"bootloader-relock-prohibited"}

    with pytest.raises(FinalConsentValidationError, match="every required"):
        service.issue(
            gateway,
            plan,
            live,
            reviewed,
            trust,
            private_key.public_key(),
            missing,
            service.confirmation_phrase(plan, live),
        )

    assert (
        service.load(
            gateway,
            plan,
            live,
            reviewed,
            trust,
            private_key.public_key(),
            now=_CONSENT_AT,
        )
        is None
    )
    with pytest.raises(FinalConsentValidationError, match="typed final-consent phrase"):
        service.issue(
            gateway,
            plan,
            live,
            reviewed,
            trust,
            private_key.public_key(),
            service.required_acknowledgements(plan, gateway),
            "FLASH SOMETHING ELSE",
        )


def test_final_consent_requires_exact_pinned_runtime_identity(consent_context) -> None:
    service, plan, gateway, live, reviewed, trust, private_key = consent_context
    other_key = Ed25519PrivateKey.generate()
    wrong_adapter = replace(trust, adapter_sha256="8" * 64)

    with pytest.raises(FinalConsentValidationError, match="failed closed"):
        service.issue(
            gateway,
            plan,
            live,
            reviewed,
            trust,
            other_key.public_key(),
            service.required_acknowledgements(plan, gateway),
            service.confirmation_phrase(plan, live),
        )

    _issue(consent_context)
    assert (
        service.load(
            gateway,
            plan,
            live,
            reviewed,
            wrong_adapter,
            private_key.public_key(),
            now=_CONSENT_AT,
        )
        is None
    )


def test_final_consent_expires_with_live_target_and_wrong_token_is_unusable(
    consent_context,
) -> None:
    service, plan, gateway, live, reviewed, trust, private_key = consent_context
    grant = _issue(consent_context)
    wrong_token = replace(grant, ephemeral_token="0" * 64)

    with pytest.raises(FinalConsentValidationError, match="ephemeral token"):
        service.validate_grant(
            wrong_token,
            gateway,
            plan,
            live,
            reviewed,
            trust,
            private_key.public_key(),
            now=_CONSENT_AT,
        )

    after_expiry = datetime.fromisoformat(live.expires_at) + timedelta(microseconds=1)
    assert (
        service.load(
            gateway,
            plan,
            live,
            reviewed,
            trust,
            private_key.public_key(),
            now=after_expiry,
        )
        is None
    )
    with pytest.raises(FinalConsentValidationError, match="no longer current"):
        service.validate_grant(
            grant,
            gateway,
            plan,
            live,
            reviewed,
            trust,
            private_key.public_key(),
            now=after_expiry,
        )


def test_final_consent_rejects_changed_target_plan_or_gateway(consent_context) -> None:
    service, plan, gateway, live, reviewed, trust, private_key = consent_context
    _issue(consent_context)

    wrong_live = replace(live, receipt_digest="f" * 64)
    wrong_plan = replace(plan, device_name="Other Phone")
    wrong_gateway = replace(gateway, runtime_invoked=True)
    assert (
        service.load(
            gateway,
            plan,
            wrong_live,
            reviewed,
            trust,
            private_key.public_key(),
            now=_CONSENT_AT,
        )
        is None
    )
    assert (
        service.load(
            gateway,
            wrong_plan,
            live,
            reviewed,
            trust,
            private_key.public_key(),
            now=_CONSENT_AT,
        )
        is None
    )
    assert (
        service.load(
            wrong_gateway,
            plan,
            live,
            reviewed,
            trust,
            private_key.public_key(),
            now=_CONSENT_AT,
        )
        is None
    )


def test_final_consent_load_rejects_tamper_extra_duplicate_and_link(
    consent_context,
) -> None:
    service, plan, gateway, live, reviewed, trust, private_key = consent_context
    _issue(consent_context)
    path = service.store.projects_root / gateway.project_id / "guardian" / service.LATEST_NAME
    original = path.read_text(encoding="utf-8")

    def rejected() -> bool:
        return (
            service.load(
                gateway,
                plan,
                live,
                reviewed,
                trust,
                private_key.public_key(),
                now=_CONSENT_AT,
            )
            is None
        )

    data = json.loads(original)
    data["execution_authority"] = "device-write"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert rejected()

    data = json.loads(original)
    data["forward_consequences"][0]["phone_changes"] = 0
    path.write_text(json.dumps(data), encoding="utf-8")
    assert rejected()

    data = json.loads(original)
    data["unexpected"] = True
    path.write_text(json.dumps(data), encoding="utf-8")
    assert rejected()

    path.write_text(
        original.replace('"schema_version": 1,', '"schema_version": 1, "schema_version": 1,'),
        encoding="utf-8",
    )
    assert rejected()

    if os.name != "nt":
        ordinary = path.with_name("ordinary-consent.json")
        ordinary.write_text(original, encoding="utf-8")
        path.unlink()
        path.symlink_to(ordinary.name)
        assert rejected()


def test_data_specific_consent_acknowledgement_and_phrase_are_unambiguous(
    consent_context,
) -> None:
    service, plan, gateway, live, *_rest = consent_context
    clean_plan = replace(plan, mode=FlashMode.CLEAN_WIPE_DATA)

    assert "keep-data-risk-understood" in service.required_acknowledgements(plan, gateway)
    assert "erase-data-requires-separate-wipe-consent" in service.required_acknowledgements(
        clean_plan,
        gateway,
    )
    assert service.confirmation_phrase(plan, live).endswith("KEEP DATA")
    assert service.confirmation_phrase(clean_plan, live).endswith("ERASE DATA")
    assert service._data_action(clean_plan.mode) is ConsentDataAction.ERASE_USER_DATA


def test_final_consent_service_has_no_execution_or_signing_surface() -> None:
    names = set(dir(GuardianFinalConsentReceiptService))
    forbidden = {"execute", "flash", "reboot", "erase", "unlock", "relock", "sign", "consume"}

    assert names.isdisjoint(forbidden)
    source = inspect.getsource(GuardianFinalConsentReceiptService)
    assert "subprocess" not in source
    assert "Ed25519PrivateKey" not in source
