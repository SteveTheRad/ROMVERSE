# ROMVERSE Build Status

## Authoritative implementation checkpoint

- Commit: `b9afd9f9377942a0303f4352d290bf109a43e0a1`
- Title: `Bound firmware source evidence adapters`
- Stage: Stage 1 — v0.2 Golden Foundation, Future-proofing checkpoint 3 of 3
- Milestone: bounded firmware source-evidence adapter protocol and deterministic registry
- Build status: committed and locally verified; Product Assurance review requested
- Working tree after the implementation commit: only the three pre-existing unrelated Companion
  modifications remain. This slice did not edit, stage, discard, or commit them.

## Exact changes

- Added a read/derive-only firmware source-evidence adapter protocol and a closed deterministic
  registry containing exactly the three pre-freeze representations: Android OTA `payload.bin`,
  Fastboot `super.img`, and extracted partition-image bundle.
- Migrated the existing source intelligence facade to create those three fixed adapters internally.
  Its public construction has no adapter injection, plug-in discovery, dynamic import, vendor
  extension, free-form command, or device/execution path.
- Added a single immutable, sorted, workspace-relative source snapshot consumed by every matcher.
  Duplicate, unsorted, malformed, absolute, escaping, or misnamed evidence paths fail closed.
- Removed priority-based classification. Multiple matching adapters, multiple payloads, multiple
  super images, duplicate/missing/unknown registered identities, and mixed OTA/Fastboot material
  now fail closed rather than silently selecting a handler.
- Kept the raw partition-image path as a deterministic fallback only when no payload or super image
  exists, preserving the established handling of Fastboot packages that contain `super.img` plus
  other partition images.
- Removed priority-based durable loading. More than one independently valid source blueprint now
  fails closed as ambiguous.
- Revalidates every prepared or loaded blueprint against the exact project, adapter identity,
  evidence-only authority label, unchanged-phone marker, and ready baseline state.
- Preserved all three retained durable formats, schema versions, fields, digests, and source-specific
  validation. `FirmwareAdapter`, `FirmwareSourceAnalysis`, and the existing source-intelligence
  facade remain available through their established imports.
- Added architecture documentation and focused/adversarial tests.

Files in the implementation commit:

- `src/romverse/rom/source_evidence_adapters.py`
- `src/romverse/rom/source_intelligence.py`
- `tests/test_firmware_source_evidence_adapters.py`
- `docs/FIRMWARE-SOURCE-EVIDENCE-ADAPTERS.md`

## Classification

- Implemented: bounded evidence protocol, closed three-adapter registry, immutable source snapshot,
  deterministic classification/loading, ambiguity rejection, evidence-result validation, and
  migration of the three existing handlers behind the registry.
- Simulated/Tested: yes, on Linux/Fedora using isolated local projects, fake source inspection tools,
  immutable evidence snapshots, synthetic hostile adapters, and durable blueprint fixtures.
- Hardware Verified: no.
- Released: no.

## Verification evidence

- Full Python repository regression: **2,880/2,880 passed**.
- Affected firmware-source, readiness, flash, Device Pack UI, navigation, Ascension, and durable
  schema regression: **223/223 passed**; included in the full-suite total and not added again.
- New adapter/registry adversarial cases: **11/11 passed**; included in both totals above.
- New cases prove closed deterministic registration, absence of execution/authority surface,
  duplicate/missing/unknown identity rejection, registration-order independence, mixed OTA/Fastboot
  ambiguity rejection, conflicting durable blueprint rejection, exact project/adapter/evidence-only
  authority/unchanged-phone/readiness validation, and unsafe snapshot-path rejection.
- Existing three-handler source-intelligence cases: **8/8 passed**; included in the totals above.
- Ruff lint for all Python source and tests: passed.
- Ruff formatting for every changed Python file and Git whitespace checks: passed. Repository-wide
  formatting was not claimed because 31 untouched pre-existing Python files differ from the current
  formatter output; none was reformatted by this slice.
- Companion tests were not rerun because this slice did not touch Companion. Its three protected
  working-tree modifications remain outside this checkpoint.
- Approved production assets remain byte-exact:
  - ROMVERSE PNG: `ab9286ce69e77abd82fe88105df70680186a4eb992289580c23f5d362c132a18`
  - ROMVERSE ICO: `bcfe1c5b960de2327c5e706cc22b872923c8ce2c254aa0b125c4f9b1dd4036b2`
  - RadForge Labs PNG: `d82ff146aab1f18474005d1a2d9ce0c3944467ae30ff7cb4fb3284387daa95cb`

## Blockers and remaining limitations

- The registry intentionally supports no new format or vendor and performs no autonomous discovery.
- Source evidence cannot create a Device Pack, choose a route, select a phone, build, flash, install,
  dispatch, approve, consent, retry, or grant Guardian authority.
- Three Companion modifications remain protected, unrelated, and unverified by this slice.
- Android instrumented tests and physical Android behavior remain unverified.
- Windows secure Recovery launch and anti-TOCTOU behavior remain unverified mandatory release
  blockers.
- Controlled physical-hardware verification remains a mandatory release blocker.
- v0.2 Golden Foundation remains closed pending Product Assurance review and later release evidence.

## Guided friction and dead ends

- No Guided UI, route, dialog, confirmation, execution, or user decision changed.
- Existing valid single-source flows retain their behavior. Mixed or conflicting sources now stop
  with one explicit ambiguity error instead of being invisibly resolved by priority.
- No new Guided confirmation or recovery loop was introduced.

## Guardian, Recovery, and safety implications

- Guardian remains the sole execution gate. The new protocol and registry are evidence-only and
  contain no command, device, dispatch, retry, or authority method.
- Evidence can inform later consumers but cannot grant build, flash, device, consent, Recovery, or
  execution authority.
- Conflicting live or durable source interpretations fail closed and cannot silently cross an
  adapter boundary.
- Existing exact-device, exact-incident, evidence-integrity, UNKNOWN-result, no-blind-retry, and
  same-incident Recovery protections are unchanged.
- Bootloader locking and relocking remain permanently prohibited. No adapter or registry path can
  authorize or dispatch them.

## Platform status

- Linux/Fedora: full Python software regression passed.
- Windows: not run. Secure trusted Recovery launch and anti-TOCTOU verification remain outstanding.
- Android emulator/physical hardware: not run.

## Feature-freeze and version-gate impact

- 5 September 2026 pre-v1.0 feature freeze: compliant. This is the approved final foundational
  adapter-boundary checkpoint and adds no format, vendor, UI, product route, autonomous discovery,
  Device Pack, execution capability, or physical-device operation.
- Future-proofing checkpoints: **3/3 implemented and locally verified**, pending this checkpoint's
  Product Assurance review.
- v0.2 Golden Foundation: remains **CLOSED**.

## Next proposed Build task

After Product Assurance approval, perform a read-only Stage 1 closure audit against the authoritative
v0.2 Golden Foundation requirements and repository evidence, then identify the smallest remaining
already-approved Build gap. Do not begin a new consequential implementation boundary until that
direction is reviewed. Windows secure launch/anti-TOCTOU and controlled physical verification remain
release blockers rather than software-simulation claims.

## External actions

- Physical phone operation: none.
- Package/APK installation: none.
- Publication/release: none.
- Remote push: none.
- Website change: none.
- Source-data migration: none.
- Companion source change by this Build slice: none.
- Local action: scoped source/docs/tests implementation commit, lint, and local software tests only.

## Product Assurance Review Requested

- Confirm the registry is genuinely closed, deterministic, evidence-only, and limited to the three
  approved pre-freeze source representations.
- Confirm mixed matches and conflicting durable blueprints now fail closed without breaking the
  intended Fastboot-super-plus-partition-images classification.
- Confirm the facade migration preserves retained formats and public compatibility while creating no
  alternate Guardian, Recovery, device, build, flash, retry, or relock authority path.
- Approve or correct the proposed read-only Stage 1 closure audit as the next bounded task.
