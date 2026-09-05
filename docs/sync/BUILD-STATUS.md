# ROMVERSE Build Status

## Authoritative implementation checkpoint

- Commit: `74388863b2264a641073eda4bbadb70955d525ff`
- Title: `Inventory durable schema compatibility`
- Stage: Stage 1 — v0.2 Golden Foundation, Future-proofing checkpoint 1 of 3
- Milestone: durable-schema compatibility inventory
- Build status: committed and locally verified; Product Assurance review requested
- Working tree after the implementation commit: only the three pre-existing unrelated Companion
  modifications remain. This slice did not edit, stage, discard, or commit them.

## Exact changes

- Added a dependency-neutral compatibility inventory covering **188** retained durable, logical,
  and wire formats across project, evidence, history, Guardian, Recovery, Knowledge, update, and
  Desktop/Companion Link domains.
- Each entry declares its current version, supported read versions, migration or deterministic
  re-derivation policy, audit-only treatment, fail-closed behavior, authority effect,
  implementation marker, and compatibility-test owner.
- Added exhaustive checks that account for every retained `romverse.*` source format and packaged
  JSON `format` identifier, while explicitly excluding package namespaces that are not records.
- Added safety assertions that audit-only records never grant authority and that no retained schema
  permits bootloader lock/relock authority.
- Documented the compatibility contract and the boundary between an inventory declaration and
  actual runtime migration. Importing the inventory performs no migration and imports no schema
  owner.
- Corrected the declared current Forge bundle version to `3`; the Forge receipt remains version
  `2`, matching their implementations.

Files in the implementation commit:

- `src/romverse/core/durable_schemas.py`
- `docs/DURABLE-SCHEMA-COMPATIBILITY.md`
- `tests/test_durable_schema_inventory.py`

## Classification

- Implemented: the durable-schema compatibility inventory, its contract documentation, and
  exhaustive inventory/authority tests.
- Simulated/Tested: yes, on Linux/Fedora through the full Python regression and focused Companion
  retained-record JVM tests.
- Hardware Verified: no.
- Released: no.

## Verification evidence

- Full Python repository regression: **2,857/2,857 passed**. This total includes the new focused
  durable-schema tests (**6/6**) and all affected Python coverage; those tests are not added again.
- Focused Companion retained-schema JVM tests: **50/50 passed** across device DNA, Link integrity,
  history, cache/optimizer history, Galaxy, first-boot, and transfer-offer records.
- Full Companion JVM attempt: **160/163 passed**. The three failures are confined to the protected,
  pre-existing `CompanionNavigationTest` working-tree modification and are reported as an observed
  unrelated limitation, not added to the passing totals above.
- Android instrumented Link vault tests: not run; no emulator or physical device was used.
- Ruff lint and formatting checks: passed for all checkpoint Python files.
- Git whitespace/diff inspection: passed.
- Approved production assets remain byte-exact:
  - ROMVERSE PNG: `ab9286ce69e77abd82fe88105df70680186a4eb992289580c23f5d362c132a18`
  - ROMVERSE ICO: `bcfe1c5b960de2327c5e706cc22b872923c8ce2c254aa0b125c4f9b1dd4036b2`
  - RadForge Labs PNG: `d82ff146aab1f18474005d1a2d9ce0c3944467ae30ff7cb4fb3284387daa95cb`

## Blockers and remaining limitations

- The inventory declares compatibility policy; it does not silently add runtime migrations or
  claim that every historical artifact has been exercised on every platform.
- Three full Companion JVM failures remain in protected, unrelated navigation work. This Build
  slice did not repair or absorb that work.
- Android instrumented tests and physical Android behavior remain unverified.
- Windows secure Recovery launch and anti-TOCTOU behavior remain unverified mandatory release
  blockers.
- Controlled physical-hardware verification remains a mandatory release blocker.
- v0.2 Golden Foundation remains closed pending Product Assurance review and later evidence.

## Guided friction and dead ends

- No Guided UI, route, dialog, execution, or user decision changed in this checkpoint.
- No new user-facing dead end was introduced. Missing or incompatible durable evidence continues
  to fail closed under its owning runtime policy; this inventory does not manufacture authority or
  present speculative recovery actions.

## Guardian, Recovery, and safety implications

- This checkpoint changes no Guardian or Recovery execution behavior and grants no build, flash,
  device, consent, retry, or verification authority.
- Exact-device, exact-incident, digest, evidence-integrity, independent-verification, UNKNOWN,
  no-blind-retry, and Guardian-only execution-gate invariants remain unchanged.
- Audit-only evidence is explicitly classified as non-authoritative.
- Bootloader locking and relocking remain permanently prohibited; the inventory contains no valid
  relock authority or migration path.

## Platform status

- Linux/Fedora: full Python regression passed; focused Companion retained-schema JVM tests passed
  with the pinned Java 17 toolchain.
- Windows: not run. Secure trusted Recovery launch remains outstanding.
- Android emulator/physical hardware: not run.

## Feature-freeze and version-gate impact

- 5 September 2026 pre-v1.0 feature freeze: compliant. This is foundation/correctness inventory
  work only and adds no product capability, format, vendor, route, or execution path.
- v0.2 Golden Foundation: remains **CLOSED**.

## Next proposed Build task

Stop at this safe committed checkpoint. After Product Assurance approves this inventory, the next
bounded task is future-proofing checkpoint 2: extract neutral Recovery/execution evidence contracts
so policy and persistence no longer depend cyclically on orchestration or ROM presentation. Do not
begin that slice before checkpoint review, and do not broaden Stage 1.

## External actions

- Physical phone operation: none.
- Package/APK installation: none.
- Publication/release: none.
- Remote push: none.
- Website change: none.
- Source-data migration: none.
- Companion source change by this Build slice: none.
- Local action: scoped source/docs/tests commit, local lint/tests, Gradle test compilation, and this
  repository handoff only.

## Product Assurance Review Requested

- Confirm that the 188-format inventory is complete and its read/migration/re-derivation,
  audit-only, failure, and authority policies are conservative enough for pre-v1.0 durability.
- Confirm that the dependency-neutral inventory boundary does not itself perform migration or
  weaken any Guardian/Recovery invariant.
- Approve or correct the proposed next bounded task: neutral Recovery/execution evidence-contract
  extraction, while retaining Windows secure launch and controlled hardware verification as
  mandatory release blockers.
