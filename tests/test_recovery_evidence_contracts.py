from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from romverse.core.recovery_contracts import (
    BootObservationReceipt,
    GuardianRecoveryExecutionResult,
    GuardianRecoveryPreparation,
    RecoveryBootEvidenceStore,
    RecoveryContractError,
    RecoveryExecutionResultEvidenceStore,
    RecoveryExecutionResultState,
    RecoveryIncident,
    RecoveryIncidentEvidenceStore,
    RecoveryStepOutcome,
    validate_recovery_boot_evidence,
    validate_recovery_execution_result_evidence,
)
from romverse.guardian.recovery_execution_result import (
    GuardianRecoveryExecutionResultService,
)
from romverse.guardian.recovery_preparation import (
    GuardianRecoveryPreparationError,
    GuardianRecoveryPreparationService,
)
from romverse.repair.autopilot import RecoveryAutopilotService
from romverse.rom.boot_observation import BootObservationService
from tests.test_guardian_recovery_adapter_runner import _runner_context
from tests.test_recovery_execution_reassessment import _complete, _results
from tests.test_recovery_execution_verification import (
    _completed_context,
    _stable_recovery_boot,
)

ROOT = Path(__file__).resolve().parents[1]


def _owner_imports(relative_path: str) -> set[str]:
    module = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(module):
        if isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
        elif isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
    return imports


def _module_graph() -> dict[str, set[str]]:
    sources = {
        ".".join(path.relative_to(ROOT / "src").with_suffix("").parts): path
        for path in (ROOT / "src" / "romverse").rglob("*.py")
    }
    return {
        name: {
            dependency
            for dependency in _owner_imports(str(path.relative_to(ROOT)))
            if dependency in sources
        }
        for name, path in sources.items()
    }


def _reachable(graph: dict[str, set[str]], source: str, target: str) -> bool:
    pending = [source]
    seen: set[str] = set()
    while pending:
        current = pending.pop()
        if current == target:
            return True
        if current in seen:
            continue
        seen.add(current)
        pending.extend(graph[current] - seen)
    return False


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _reseal_result(result: GuardianRecoveryExecutionResult, **changes):
    changed = replace(result, **changes, result_digest="")
    payload = asdict(changed)
    payload.pop("result_digest")
    return replace(changed, result_digest=_digest(payload))


def _reseal_boot(receipt: BootObservationReceipt, **changes):
    changed = replace(receipt, **changes, receipt_digest="")
    payload = asdict(changed)
    payload.pop("receipt_digest")
    return replace(changed, receipt_digest=_digest(payload))


def test_contract_module_is_dependency_neutral_and_owner_cycles_are_removed() -> None:
    neutral = _owner_imports("src/romverse/core/recovery_contracts.py")
    assert not any(
        name.startswith(("romverse.guardian", "romverse.repair", "romverse.rom", "romverse.ui"))
        for name in neutral
    )

    guardian_preparation = _owner_imports("src/romverse/guardian/recovery_preparation.py")
    repair = _owner_imports("src/romverse/repair/autopilot.py")
    boot = _owner_imports("src/romverse/rom/boot_observation.py")
    guardian_result = _owner_imports("src/romverse/guardian/recovery_execution_result.py")
    assert not any(name.startswith("romverse.repair") for name in guardian_preparation)
    assert not any(name.startswith("romverse.guardian") for name in repair)
    assert "romverse.rom.boot_observation" not in repair
    assert not any(name.startswith("romverse.guardian.recovery") for name in boot)
    assert not any(
        name.startswith(("romverse.repair", "romverse.rom.boot_observation"))
        for name in guardian_result
    )

    graph = _module_graph()
    for first, second in (
        ("romverse.guardian.recovery_preparation", "romverse.repair.autopilot"),
        ("romverse.guardian.recovery_execution_result", "romverse.repair.autopilot"),
        ("romverse.guardian.recovery_execution_result", "romverse.rom.boot_observation"),
    ):
        assert not (_reachable(graph, first, second) and _reachable(graph, second, first))


def test_legacy_imports_reexport_the_same_neutral_contract_types() -> None:
    from romverse.guardian.recovery_execution import RecoveryStepOutcome as LegacyOutcome
    from romverse.guardian.recovery_execution_result import (
        GuardianRecoveryExecutionResult as LegacyResult,
    )
    from romverse.guardian.recovery_preparation import (
        GuardianRecoveryPreparation as LegacyPreparation,
    )
    from romverse.repair.autopilot import RecoveryIncident as LegacyIncident
    from romverse.rom.boot_observation import BootObservationReceipt as LegacyBootReceipt

    assert LegacyPreparation is GuardianRecoveryPreparation
    assert LegacyOutcome is RecoveryStepOutcome
    assert LegacyResult is GuardianRecoveryExecutionResult
    assert LegacyIncident is RecoveryIncident
    assert LegacyBootReceipt is BootObservationReceipt


def test_evidence_readers_are_nominal_and_expose_no_command_or_retry_surface() -> None:
    assert issubclass(RecoveryAutopilotService, RecoveryIncidentEvidenceStore)
    assert issubclass(
        GuardianRecoveryExecutionResultService,
        RecoveryExecutionResultEvidenceStore,
    )
    assert issubclass(BootObservationService, RecoveryBootEvidenceStore)
    for boundary in (
        RecoveryIncidentEvidenceStore,
        RecoveryExecutionResultEvidenceStore,
        RecoveryBootEvidenceStore,
    ):
        assert not {
            "execute",
            "dispatch",
            "approve",
            "consent",
            "retry",
            "migrate",
            "write",
        } & set(dir(boundary))

    class DuckIncidentReader:
        workspace = Path("/")

        def load(self, _incident_id):
            return None

        def validate_route_handoff(self, *_args, **_kwargs):
            return None

    assert not isinstance(DuckIncidentReader(), RecoveryIncidentEvidenceStore)
    with pytest.raises(GuardianRecoveryPreparationError, match="nominal incident evidence"):
        GuardianRecoveryPreparationService(object(), object(), DuckIncidentReader())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("execution_authority", "forged-authority"),
        ("automatic_retry_allowed", True),
        ("bootloader_relock_allowed", True),
        ("same_incident_preserved", False),
        ("device_repaired", True),
        ("device_key", "0" * 20),
        ("incident_record_digest", "0" * 64),
    ],
)
def test_result_contract_rejects_self_consistent_safety_forgery(
    tmp_path,
    monkeypatch,
    field,
    value,
) -> None:
    runner, executions, grant, prepared, adapter, *_ = _runner_context(tmp_path, monkeypatch)
    _complete(runner, grant, prepared, adapter)
    aggregate = _results(executions).record(prepared)
    validate_recovery_execution_result_evidence(prepared, aggregate)

    forged = _reseal_result(aggregate, **{field: value})
    with pytest.raises(RecoveryContractError, match="failed closed"):
        validate_recovery_execution_result_evidence(prepared, forged)


def test_result_contract_preserves_unknown_and_rejects_relock_action(tmp_path, monkeypatch) -> None:
    runner, executions, grant, prepared, adapter, *_ = _runner_context(tmp_path, monkeypatch)
    adapter.raise_error = True
    runner.execute_next(grant, prepared, adapter)
    aggregate = _results(executions).record(prepared)

    assert aggregate.state is RecoveryExecutionResultState.UNKNOWN_AWAITING_RECONSTRUCTION
    assert not aggregate.automatic_retry_allowed
    validate_recovery_execution_result_evidence(prepared, aggregate)

    relock_entry = replace(
        aggregate.journal_entries[-1],
        adapter_action_id="radforge.relock_bootloader",
    )
    entries = (*aggregate.journal_entries[:-1], relock_entry)
    forged = _reseal_result(
        aggregate,
        journal_entries=entries,
        journal_digest=_digest({"entries": [asdict(entry) for entry in entries]}),
    )
    with pytest.raises(RecoveryContractError, match="failed closed"):
        validate_recovery_execution_result_evidence(prepared, forged)


def test_boot_contract_rejects_self_consistent_phone_change_and_exposes_minimal_project_identity(
    tmp_path,
    monkeypatch,
) -> None:
    executions, grant, prepared, results, _aggregate, _reassessed, autopilot = _completed_context(
        tmp_path,
        monkeypatch,
    )
    observations, _device, receipt = _stable_recovery_boot(
        executions,
        autopilot,
        grant,
        prepared,
        results,
    )
    validate_recovery_boot_evidence(receipt)
    project = observations.project_evidence(prepared.project_id)
    assert asdict(project) == {
        "project_id": prepared.project_id,
        "device_pack_id": prepared.device_pack_id,
        "source_original_sha256": prepared.source_original_sha256,
    }

    forged = _reseal_boot(receipt, phone_changed=True)
    with pytest.raises(RecoveryContractError, match="failed closed"):
        validate_recovery_boot_evidence(forged)
