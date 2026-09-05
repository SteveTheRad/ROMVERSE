# ROMVERSE neutral Recovery evidence contracts

ROMVERSE exchanges consequential Recovery evidence through the dependency-neutral contracts in
`romverse.core.recovery_contracts`. The module contains immutable evidence records, conservative
validators, and nominal read-only owner boundaries. It imports no Guardian, Repair, ROM, UI, or
storage service.

## Ownership boundary

- Recovery orchestration owns incident history and implements `RecoveryIncidentEvidenceStore`.
- Guardian owns preparation, consent, execution, and aggregate-result persistence. Its aggregate
  reader implements `RecoveryExecutionResultEvidenceStore`.
- Boot observation owns read-only post-operation evidence and implements
  `RecoveryBootEvidenceStore`.
- Callers may exchange evidence through these interfaces, but no interface exposes a command,
  adapter dispatch, consent, approval, retry, migration, or write method.

The legacy import locations continue to re-export the same class objects. This preserves current
Python callers and the byte-level JSON schemas while removing the former owner-to-owner type
dependency. No retained record is rewritten by this extraction.

## Trust rule

A reader's nominal type is necessary but not sufficient. Consumers independently validate the
sealed preparation, aggregate result, and boot receipt before acting on the evidence. Validation
binds the same preparation, incident, route, project, pseudonymous device, source, Device Pack,
transition, action sequence, journal, and digest.

The neutral aggregate contract preserves these state distinctions:

- `SEQUENCE_COMPLETED_AWAITING_REASSESSMENT` proves only that every prepared adapter action has a
  durable exact success. It does not prove Recovery.
- `FAILED_AWAITING_REASSESSMENT` preserves a known failed terminal step.
- `UNKNOWN_AWAITING_RECONSTRUCTION` preserves an uncertain terminal step, including durable intent
  without a provable result.

Both failure and `UNKNOWN` prohibit automatic retry. All aggregate evidence remains audit-only,
with `execution_authority = "none"`, `device_repaired = false`, and
`recovery_verified = false`. Independent fresh boot verification remains a separate boundary.

## Absolute invariants

- Historical identity never grants current target authority.
- Same-model/different-device evidence cannot satisfy exact-device binding.
- Incident identity and journal outcomes remain immutable and digest-bound.
- Missing or malformed evidence fails closed.
- `UNKNOWN` is never converted to failure, success, or retry authority.
- Bootloader locking and relocking have no valid contract or override path.
- These contracts add no physical execution capability and do not change Guided presentation.
