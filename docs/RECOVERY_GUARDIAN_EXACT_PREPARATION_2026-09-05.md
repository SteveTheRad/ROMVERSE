# Recovery to Guardian exact preparation — 2026-09-05

## Scope

This Stage 1 checkpoint closes the first real consequential boundary after the Recovery typed-owner
audit. The audit found no genuine ROM Studio-owned consequential Recovery route: boot observation is
correctly performed in place, while slot, image, stock and data-reset consequences are owned by
Guardian. Ownership was therefore not relabelled to satisfy a test plan.

The first implemented preparation is the existing exact-stock restoration route after Time Machine
has produced current external-backup and byte-identical stock-package evidence.

## Implemented chain

1. Recovery reloads the same integrity-checked incident and current ranked route.
2. A shared Recovery domain boundary requires a fresh physical-device pseudonym match for every
   phone-changing handoff. A model, product name, historical selection or same-model substitute is
   insufficient.
3. Guardian preparation independently reloads the exact project and its protected original.
4. It resolves the freshly scanned phone to the exact incident Device Pack ID and Pack digest.
5. It validates the Pack's signed schema-three transition/recovery contract against its firmware
   source and the project's protected-source SHA-256.
6. It reloads current Time Machine recovery evidence. Both the external backup and byte-identical
   stock package must still be present and unchanged; a device-bound backup must belong to the
   incident phone.
7. It selects the Pack-declared stock restoration action and every required subsequent signed action,
   then seals the exact sequence in a local tamper-evident preparation.
8. Guardian displays the incident, project, complete protected-source digest, Device Pack identity,
   transition digest, recovery adapter, evidence digest and prepared steps in one contextual card.
9. The card still grants no approval or execution authority. Live-target validation and explicit
   user confirmation remain independently required.
10. Return reloads and validates the same preparation against current incident, phone, project,
    source, Pack, contract and evidence. Any drift expires the card visibly instead of returning
    stale authority or substituting context.

## Durable evidence

The zero-authority preparation is stored privately under
`diagnostics/recovery-preparations/<incident-id>/latest.romverse`. It contains only a pseudonymous
device key, never a raw serial. Its digest covers every field and ordered step.

This record is preparation evidence, not an execution receipt. It cannot prove that a command ran or
that a phone changed.

## Adversarial boundaries

- Same model, different physical phone: refused.
- Missing or changed incident/route: refused.
- Changed project, protected source, Device Pack or signed transition contract: refused.
- Missing, stale, changed or cross-device recovery evidence: refused.
- Altered preparation fields or steps: refused by strict digest/schema validation.
- Bootloader relock token in an adapter identity: refused.
- Opening, viewing and returning: no phone command, approval, recovery, wipe, retry or flash.

## Honest status

Implemented and simulated/tested on Fedora/Linux only. This checkpoint prepares exact Guardian
evidence but does not yet implement the independent live-target check, recovery-specific consent,
production runtime recovery executor, durable execution result ingestion or post-action incident
reassessment. Windows and physical-hardware verification remain outstanding. Feature freeze remains
active and the v0.2 Golden Foundation gate remains closed.

## Verification

- One final affected Fedora/Linux run passed 158 unique tests with zero failures, errors or skips in
  about 164 seconds. The scope covered Guardian preparation/UI, Recovery Autopilot/UI, Time Machine,
  recovery evidence and full desktop navigation; focused runs overlap and are not added to this
  count.
- Changed-file Ruff, Ruff format, Python compilation and diff checks passed.
- The 1440×900 offscreen render at
  `/tmp/romverse-guardian-recovery-preparation-20260905.png` was inspected: the exact preparation,
  approval boundary and return action are visible and unclipped.
- Approved ROMVERSE PNG/ICO and RadForge Labs production-logo hashes remained byte-exact.
