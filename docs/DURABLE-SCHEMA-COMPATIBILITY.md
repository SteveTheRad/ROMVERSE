# ROMVERSE durable-schema compatibility inventory

Status: pre-v1 foundation contract, 6 September 2026

Scope: retained v1 project, evidence, history, Guardian, Recovery, Knowledge, update, and Desktop/Companion Link records

The machine-readable authority is `src/romverse/core/durable_schemas.py`. It inventories 188
retained formats across the eight required domains. Each format declares its current version,
accepted read versions, migration or deterministic re-derivation policy, audit-only posture,
failure behavior, authority effect, owning implementation, and compatibility regression.

## Compatibility rules

1. A version being readable does not make it current, trusted, or authoritative.
2. Legacy evidence is upgraded only after the current implementation independently verifies or
   re-derives every binding needed by that record. Parsing alone never authorizes a rewrite.
3. Re-derived records are caches or evidence candidates. Their source, project, Device Pack,
   device, artifact, digest, mode, slot, and other applicable bindings are checked again by their
   owner before use.
4. Audit-only records preserve historical meaning. They may describe an intended, successful,
   failed, or `UNKNOWN` result but never supply present execution authority.
5. Guardian records are components of an exact chain. Recommendation, preparation, live target,
   consent, execution, durable result, Recovery reassessment, and verification remain separate.
6. Invalid or unsupported Guardian/Recovery evidence fails closed. Missing UI/history convenience
   state may fall back or disappear, but that fallback cannot satisfy a consequential gate.
7. Desktop/Companion wire records are parsed, not migrated in transit. Unknown versions,
   malformed shapes, duplicate fields, hidden commands, and unexpected authority fields are
   rejected.
8. No migration, re-derivation, audit record, update record, Knowledge record, or Link record may
   authorize bootloader locking/relocking. Relocking remains permanently prohibited.

## Version classes

- **Strict:** only explicitly listed versions are accepted; unknown/future versions fail.
- **Verified upgrade:** older versions remain readable but current output is written only after
  fresh verification.
- **Re-derived:** the saved record is recomputed from current bounded evidence before it can be
  trusted.
- **Audit preserve:** historical bytes are not rewritten to change their meaning; later facts are
  appended as new records.
- **Safe default:** damaged non-authority preferences/continuity state reset conservatively.
- **Wire only:** accepted protocol versions become bounded neutral data and never authority.

## Inventory boundaries

The inventory uses a logical identifier for durable records that deliberately have no JSON
`format` field, such as `settings.json`, the Companion encrypted token vault, and the phone-local
Lifeline session. The implementation marker binds those declarations to the actual owner.

Nested objects that cannot be stored independently inherit the version and failure posture of
their enclosing format; they are not counted twice. Temporary files, locks, caches with no retained
semantic claim, raw firmware/artifact bytes, private keys, ephemeral in-memory capability tokens,
and UI-only view state are not durable schema formats. Signed package/request/result protocols are
included when their bytes are retained or when a retained record is contractually bound to their
version.

## Release posture

This checkpoint changes no loader, writer, migration, UI, build, flash, install, or device behavior.
It does not enable physical Recovery execution. Windows secure Recovery launch and controlled
physical-hardware verification remain mandatory release blockers. The pre-v1 feature freeze and
Guardian-only execution boundary remain unchanged.

Run `pytest tests/test_durable_schema_inventory.py` to verify inventory structure, source anchors,
test anchors, domain coverage, audit authority, Guardian failure posture, and the no-relock schema
boundary. Existing owner-specific suites remain the behavioral compatibility proof named by each
inventory entry.
