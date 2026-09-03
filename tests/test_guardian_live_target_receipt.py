from __future__ import annotations

import hashlib
import inspect
import json
import os
import stat
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from romverse.device.models import DeviceState
from romverse.guardian.live_target_receipt import (
    GuardianLiveTargetReceiptService,
    LiveTargetValidationError,
)
from romverse.guardian.models import OperationClass, OperationRequest
from romverse.guardian.policy import MilestoneOnePolicy
from romverse.infrastructure.process import CommandResult
from tests.test_guardian_execution_gateway_contract import _service as gateway_service
from tests.test_guardian_execution_plan import _prepared_with_transition_recovery


class _AdbFixture:
    def __init__(self, outputs: tuple[str, ...] = ("List of devices attached\n",)) -> None:
        self.outputs = outputs
        self.calls = 0

    def devices(self) -> CommandResult:
        output = self.outputs[min(self.calls, len(self.outputs) - 1)]
        self.calls += 1
        return CommandResult(("adb", "devices", "-l"), 0, output, "")


class _FastbootFixture:
    def __init__(
        self,
        *,
        discovery: tuple[str, ...] = ("private-serial\tfastboot usb:1-2\n",),
        values: dict[str, str | tuple[str, ...]] | None = None,
        fail_variable: str = "",
    ) -> None:
        self.discovery = discovery
        self.values = values or {
            "product": "product",
            "unlocked": "yes",
            "is-userspace": "no",
        }
        self.fail_variable = fail_variable
        self.discovery_calls = 0
        self.getvar_calls: list[str] = []
        self.variable_calls: dict[str, int] = {}

    def devices(self) -> CommandResult:
        output = self.discovery[min(self.discovery_calls, len(self.discovery) - 1)]
        self.discovery_calls += 1
        return CommandResult(("fastboot", "devices", "-l"), 0, output, "")

    def getvar(self, serial: str, variable: str, timeout: float = 4) -> CommandResult:
        assert serial == "private-serial"
        assert timeout == 4
        self.getvar_calls.append(variable)
        call = self.variable_calls.get(variable, 0)
        self.variable_calls[variable] = call + 1
        if variable == self.fail_variable:
            return CommandResult(("fastboot", "getvar", variable), 1, "", "failed")
        source = self.values[variable]
        value = source[min(call, len(source) - 1)] if isinstance(source, tuple) else source
        return CommandResult(
            ("fastboot", "getvar", variable),
            0,
            "",
            f"(bootloader) {variable}: {value}\nOKAY",
        )


@pytest.fixture
def live_context(tmp_path, monkeypatch):
    plans, project, report, device, *_rest = _prepared_with_transition_recovery(
        tmp_path, monkeypatch
    )
    reviewed = replace(
        device,
        state=DeviceState.DEVICE,
        build_id="CURRENT.BUILD",
        build_fingerprint="test/product/current-build:user/release-keys",
    )
    plans.compile(project.project_id, report, reviewed)
    gateway = gateway_service(plans).compile(project.project_id, report, reviewed)
    return plans.store, reviewed, gateway


def _receipt(live_context, *, adb=None, fastboot=None, when=None):
    store, reviewed, gateway = live_context

    def clock():
        return when or datetime(2026, 9, 3, 21, 0, tzinfo=UTC)

    service = GuardianLiveTargetReceiptService(
        store,
        adb or _AdbFixture(),
        fastboot or _FastbootFixture(),
        clock=clock,
    )
    return service, service.observe(gateway, reviewed)


def test_live_target_receipt_reidentifies_one_stable_exact_device(live_context) -> None:
    adb = _AdbFixture()
    fastboot = _FastbootFixture()
    service, receipt = _receipt(live_context, adb=adb, fastboot=fastboot)
    store, reviewed, gateway = live_context

    assert receipt.gateway_contract_digest == gateway.contract_digest
    assert receipt.device_key == gateway.device_key
    assert receipt.expected_entry_mode == "bootloader"
    assert receipt.observed_entry_mode == "bootloader"
    assert receipt.observed_product == "product"
    assert receipt.observed_unlocked
    assert receipt.recorded_prewrite_slot == ""
    assert receipt.discovery_pass_count == 3
    assert len(set(receipt.discovery_pass_digests)) == 1
    assert receipt.probe_round_count == 2
    assert [item.variable for item in receipt.probe_results] == [
        "product",
        "unlocked",
        "is-userspace",
    ] * 2
    assert all(item.matched for item in receipt.probe_results)
    assert (
        receipt.reviewed_build_id_sha256 == hashlib.sha256(reviewed.build_id.encode()).hexdigest()
    )
    assert (
        receipt.reviewed_build_fingerprint_sha256
        == hashlib.sha256(reviewed.build_fingerprint.encode()).hexdigest()
    )
    assert receipt.identity_verified
    assert not receipt.cryptographic_device_attestation
    assert not receipt.final_consent_available
    assert receipt.execution_authority == "none"
    assert not receipt.runtime_invoked
    assert not receipt.phone_changed
    assert adb.calls == 3
    assert fastboot.discovery_calls == 3
    assert fastboot.getvar_calls == ["product", "unlocked", "is-userspace"] * 2
    assert service.load(gateway, reviewed, now=datetime(2026, 9, 3, 21, 1, tzinfo=UTC)) == receipt

    path = store.projects_root / gateway.project_id / "guardian" / service.LATEST_NAME
    serialized = path.read_text(encoding="utf-8")
    assert reviewed.serial not in serialized
    assert reviewed.build_fingerprint not in serialized
    assert "flash" not in serialized
    assert "reboot" not in serialized
    if os.name != "nt":
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"product": "wrong", "unlocked": "yes", "is-userspace": "no"}, "product"),
        ({"product": "product", "unlocked": "no", "is-userspace": "no"}, "unlocked"),
        ({"product": "product", "unlocked": "yes", "is-userspace": "yes"}, "is-userspace"),
    ],
)
def test_live_target_receipt_fails_closed_on_identity_or_mode_mismatch(
    live_context,
    values,
    message,
) -> None:
    store, reviewed, gateway = live_context
    service = GuardianLiveTargetReceiptService(
        store,
        _AdbFixture(),
        _FastbootFixture(values=values),
    )

    with pytest.raises(LiveTargetValidationError, match=message):
        service.observe(gateway, reviewed)

    assert not (
        store.projects_root / gateway.project_id / "guardian" / service.LATEST_NAME
    ).exists()


def test_live_target_receipt_rejects_swap_ambiguity_and_probe_failure(live_context) -> None:
    store, reviewed, gateway = live_context
    swapped = _FastbootFixture(
        discovery=(
            "private-serial\tfastboot usb:1-2\n",
            "other-serial\tfastboot usb:1-3\n",
        )
    )
    service = GuardianLiveTargetReceiptService(store, _AdbFixture(), swapped)
    with pytest.raises(LiveTargetValidationError, match="not the reviewed device"):
        service.observe(gateway, reviewed)

    ambiguous_adb = _AdbFixture(("List of devices attached\nother\tdevice usb:1-3\n",))
    service = GuardianLiveTargetReceiptService(store, ambiguous_adb, _FastbootFixture())
    with pytest.raises(LiveTargetValidationError, match="exactly one Fastboot"):
        service.observe(gateway, reviewed)

    service = GuardianLiveTargetReceiptService(
        store,
        _AdbFixture(),
        _FastbootFixture(fail_variable="unlocked"),
    )
    with pytest.raises(LiveTargetValidationError, match="probe failed: unlocked"):
        service.observe(gateway, reviewed)

    reconnected = _FastbootFixture(
        discovery=(
            "private-serial\tfastboot usb:1-2\n",
            "private-serial\tfastboot usb:1-7\n",
            "private-serial\tfastboot usb:1-7\n",
        )
    )
    service = GuardianLiveTargetReceiptService(store, _AdbFixture(), reconnected)
    with pytest.raises(LiveTargetValidationError, match="USB transport changed"):
        service.observe(gateway, reviewed)


def test_live_target_receipt_rejects_probe_drift_and_incomplete_reviewed_build(
    live_context,
) -> None:
    store, reviewed, gateway = live_context
    changed = _FastbootFixture(
        values={
            "product": ("product", "other"),
            "unlocked": "yes",
            "is-userspace": "no",
        }
    )
    service = GuardianLiveTargetReceiptService(store, _AdbFixture(), changed)
    with pytest.raises(LiveTargetValidationError, match="product"):
        service.observe(gateway, reviewed)

    no_build = replace(reviewed, build_fingerprint="")
    untouched_adb = _AdbFixture()
    untouched_fastboot = _FastbootFixture()
    service = GuardianLiveTargetReceiptService(store, untouched_adb, untouched_fastboot)
    with pytest.raises(LiveTargetValidationError, match="complete reviewed Android build"):
        service.observe(gateway, no_build)
    assert untouched_adb.calls == 0
    assert untouched_fastboot.discovery_calls == 0


def test_failed_recheck_invalidates_the_previous_short_lived_receipt(live_context) -> None:
    service, receipt = _receipt(live_context)
    _store, reviewed, gateway = live_context
    assert (
        service.load(gateway, reviewed, now=datetime.fromisoformat(receipt.completed_at)) == receipt
    )

    service.fastboot = _FastbootFixture(
        values={"product": "other", "unlocked": "yes", "is-userspace": "no"}
    )
    with pytest.raises(LiveTargetValidationError, match="product"):
        service.observe(gateway, reviewed)

    assert service.load(gateway, reviewed, now=datetime.fromisoformat(receipt.completed_at)) is None


def test_live_target_receipt_load_rejects_expiry_tamper_extra_duplicate_and_link(
    live_context,
) -> None:
    service, receipt = _receipt(live_context)
    store, reviewed, gateway = live_context
    path = store.projects_root / gateway.project_id / "guardian" / service.LATEST_NAME

    assert (
        service.load(gateway, reviewed, now=datetime.fromisoformat(receipt.expires_at)) == receipt
    )
    assert (
        service.load(
            gateway,
            replace(reviewed, build_id="OTHER.BUILD"),
            now=datetime.fromisoformat(receipt.completed_at),
        )
        is None
    )
    assert (
        service.load(
            gateway,
            reviewed,
            now=datetime.fromisoformat(receipt.expires_at) + timedelta(microseconds=1),
        )
        is None
    )

    original = path.read_text(encoding="utf-8")
    data = json.loads(original)
    data["identity_verified"] = False
    path.write_text(json.dumps(data), encoding="utf-8")
    assert service.load(gateway, reviewed, now=datetime.fromisoformat(receipt.completed_at)) is None

    data = json.loads(original)
    data["unexpected"] = True
    path.write_text(json.dumps(data), encoding="utf-8")
    assert service.load(gateway, reviewed, now=datetime.fromisoformat(receipt.completed_at)) is None

    duplicate = original.replace(
        '"schema_version": 1,',
        '"schema_version": 1, "schema_version": 1,',
        1,
    )
    path.write_text(duplicate, encoding="utf-8")
    assert service.load(gateway, reviewed, now=datetime.fromisoformat(receipt.completed_at)) is None

    if os.name != "nt":
        target = path.with_name("ordinary-receipt.json")
        target.write_text(original, encoding="utf-8")
        path.unlink()
        path.symlink_to(target.name)
        assert (
            service.load(gateway, reviewed, now=datetime.fromisoformat(receipt.completed_at))
            is None
        )


def test_partition_has_slot_probe_is_narrowly_allowlisted() -> None:
    policy = MilestoneOnePolicy()
    request = OperationRequest(
        operation_id="fastboot.getvar.has-slot:system_a",
        category=OperationClass.READ_ONLY,
        executable="fastboot",
        arguments=("-s", "serial", "getvar", "has-slot:system_a"),
        purpose="Verify the signed partition slot contract",
        target="serial",
    )

    assert policy.assess(request).allowed
    assert not policy.assess(
        replace(
            request,
            operation_id="fastboot.getvar.all",
            arguments=("-s", "serial", "getvar", "all"),
        )
    ).allowed
    assert not policy.assess(
        replace(
            request,
            arguments=("-s", "serial", "getvar", "has-slot:../../userdata"),
        )
    ).allowed


def test_live_target_probe_contract_captures_required_prewrite_slot(live_context) -> None:
    store, reviewed, gateway = live_context
    gateway_needing_slot = replace(gateway, recovery_require_prewrite_slot_capture=True)
    specs = GuardianLiveTargetReceiptService._probe_specs(
        gateway_needing_slot,
        "bootloader",
    )
    fastboot = _FastbootFixture(
        values={
            "product": "product",
            "unlocked": "yes",
            "is-userspace": "no",
            "current-slot": "_a",
        }
    )
    service = GuardianLiveTargetReceiptService(store, _AdbFixture(), fastboot)

    first = service._probe_round(reviewed.serial, specs, 1, 0)
    second = service._probe_round(reviewed.serial, specs, 2, len(first))
    observed = service._validate_probe_rounds(specs, (*first, *second), "bootloader")

    assert specs[-1].variable == "current-slot"
    assert observed["current-slot"] == "a"


def test_live_target_receipt_has_no_mutation_or_runtime_surface() -> None:
    names = set(dir(GuardianLiveTargetReceiptService))
    forbidden = {"execute", "flash", "reboot", "erase", "unlock", "relock", "sign", "consent"}

    assert names.isdisjoint(forbidden)
    source = inspect.getsource(GuardianLiveTargetReceiptService)
    assert "subprocess" not in source
