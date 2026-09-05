# ROMVERSE Product Assurance

## Current directive: Future-proofing minimum pre-v1.0 architecture

- Prior approved checkpoint: `bdb512e7e5d271e83c164a4ec7844cd7239e2fbe`
- Prior assurance handoff: `b3a2bca`
- Status: **CREATOR DIRECTIVE ACCEPTED — BOUNDED TASK ORDER APPROVED**

No new Build source checkpoint exists after `b3a2bca`. This record authorizes architecture and
correctness work only; it does not authorize physical Recovery execution, publication, release, or
changes to the protected Companion files.

### Approved task order

1. **Durable-schema compatibility inventory — first checkpoint.** Inventory every v1-retained
   project, evidence, history, Guardian, Recovery, Knowledge, update, Desktop, and Companion-Link
   record. For each schema record its version, read support, migration or deterministic
   re-derivation path, audit-only status where applicable, fail-closed behavior, and tests. This
   must be documentation/contracts/tests first and must not silently rewrite existing records.

2. **Neutral Recovery/execution evidence contracts.** Extract dependency-neutral contracts between
   evidence, Recovery, Guardian, and execution boundaries so Guardian↔Repair/ROM cycles are removed
   without weakening exact-device binding, consent, UNKNOWN semantics, no-blind-retry, Guardian-only
   authority, or the absolute no-relock rule. No new execution capability is part of this slice.

3. **Bounded firmware source-evidence adapter protocol.** Define a neutral, evidence-only protocol
   and deterministic registry, then migrate only the existing OTA payload, Fastboot-super, and
   partition-bundle handlers. Ambiguous or conflicting matches must fail closed; evidence must
   never grant execution authority. No new firmware handler or device-changing path is approved.

Each checkpoint requires an independent Product Assurance review before the next begins. Windows
secure Recovery launch and controlled physical hardware verification remain mandatory later release
gates.

### Freeze and safety gates

- v0.2 Golden Foundation: **CLOSED**
- Pre-v1.0 feature freeze: **preserved**
- Physical execution, phone operation, installation, publication, release, and remote push: **not authorized**
- Windows trusted-launcher anti-TOCTOU: outstanding release blocker
- Physical Android hardware verification: outstanding release blocker
- Guardian-only execution, UNKNOWN-on-uncertainty, no blind retry, and no bootloader relocking:
  mandatory in every checkpoint

### Acceptance criteria for the first checkpoint

- All named retained schemas are inventoried against authoritative repository definitions and tests.
- Every record has an explicit read/compatibility and failure posture.
- Any migration or re-derivation is deterministic, auditable, and cannot create authority.
- No application source behavior, UI scope, execution path, or protected Companion change is
  introduced merely to complete the inventory.
