# ROMVERSE Build Status

## Adaptive Online Device DNA checkpoint — 8 September 2026

- Branch/base: `adaptive-online-device-dna` from
  `a6d9bca06d35c4f0ca8b84ad6ebd990be7e5700a`.
- Implementation checkpoint: `d4c7d57ea7bc4e5f289973d6558b85b0633d6af3`
  (`Add bounded online device evidence foundation`).
- Result: strict claim-level online evidence/storage, deterministic conflict-preserving merging,
  privacy filtering, a four-source official/public registry boundary, later firmware/live comparison,
  and read-only contracts for the approved intelligence/device consumers are implemented.
- Focused verification: 79 passed across the new evidence tests plus existing local-store and online
  remediation regressions; focused Ruff check/format and Git whitespace checks passed.
- Safety: unknown devices remain `UNCONFIRMED` and trigger investigation. Evidence grants no command,
  phone, Guardian, execution, or bootloader-relock authority.
- Physical device, firmware mutation, emulator, APK, production service, publication, and full-suite
  work: none.
- Detailed handoff: `docs/sync/KNOWLEDGE-RESEARCH-STATUS.md`.
- Next: stop for Product Assurance before adding an OEM firmware adapter, additional sources, UI
  wiring, or any consequential workflow.

## Authoritative checkpoint

- Product Assurance authorization/base: `4282da62947dd7e21de56eeb4550a827b468ae87`.
- Implementation and focused-regression checkpoint:
  `b77ee3c03aac1746a8e8f18acd370ddcb3094360`
  (`Preserve local build completion across restart`).
- Final handoff checkpoint: the follow-up commit containing this status document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, Fedora Recipe Forge to durable local-build acceptance.
- Working tree at the implementation checkpoint: clean.

## Exact journey and evidence

- Used one new disposable workspace and bounded synthetic unfamiliar firmware source. The source
  contained only `payload.bin` and `system/build.prop`; it was not a vendor firmware package or
  Device Pack.
- Drove the real production Qt widgets and production persistence/services with no device engine:
  1. opened `RecipeForgeSequence` from a Recipe Forge-ready isolated tree;
  2. created one deterministic `set_property` Recipe for `system/build.prop`;
  3. reviewed the exact property change before saving;
  4. ran the production Recipe preview and proved the target remained unchanged;
  5. explicitly approved the production transactional Recipe action;
  6. verified the changed property and durable Recipe receipt plus rollback snapshot;
  7. froze the final tree, supplied a bounded synthetic exact local-build contract and inert test
     tool identities, and prepared the production deterministic local-build plan;
  8. ran the production `BuildControlCenter` worker and `LocalDeviceBuildExecutor` through all
     seven durable build steps using a deterministic no-phone process adapter;
  9. verified three output artifacts and the durable local-build receipt;
  10. closed the UI/services, reconstructed `RomProjectStore`, `RomStudio`, and
      `BuildControlCenter`, and reverified the same durable receipts and final UI state.
- Recipe receipt:
  `99877801448532adaae3226976f8e1709434e7739b684f6449cf78fc89b35207`.
- Local-build receipt:
  `0dd0f114ac1bcbb2787205124941dbf159bf11e51ca39499da171e03684401ce`.
- The deterministic local-build adapter observed eight bounded host-tool invocations and zero ADB
  or Fastboot invocations. Every persisted receipt states `phone_changed: false`.
- The reopened production UI reverified `local_candidate_ready: true` and
  `signing_ready: false`.

## First concrete defect and correction

- Defect: after successful local-build completion, the immediate footer reported a verified local
  candidate, but the same project reopened as `BUILD READY / FLASH LOCKED`. It also offered
  `Prepare verified ROM installation…` before artifact trust/signing evidence was ready.
- Cause: Forge Control presented durable local-build completion only when `signing_ready` was true,
  and routed its primary action to installation whenever `local_candidate_ready` was true.
- Minimum correction:
  - durable `local_candidate_ready` now renders `LOCAL BUILD COMPLETE / INSTALL NOT AUTHORIZED`;
  - the reopened view explicitly says that artifact trust, signing/AVB, and Guardian gates remain
    separate and that nothing was installed or flashed;
  - it offers `Finish local build` or `Continue to artifact verification`;
  - installation preparation is not the primary route until artifact trust is ready;
  - a focused regression proves the completed-but-unsigned state cannot route directly to the
    installation handoff.
- No build, signing, Guardian, Recovery, adapter, device or release semantics changed.

## Result classification

- Implemented: truthful durable-local-build completion state and safe next-action routing in Fedora
  Forge Control.
- Simulated/Tested: yes — one production-widget/service Recipe Forge → local-build → normal reload
  journey with a bounded synthetic source and deterministic inert host-tool adapter; seven unique
  focused regressions; lint clean.
- Hardware Verified: no.
- Released: no.

## Non-double-counted verification

- Production-widget/service journey: **1/1 passed**.
- Focused regression nodes in one invocation: **7/7 passed**:
  - Recipe Forge multi-step reviewed creation;
  - transactional Recipe and restore workflow enablement;
  - Recipe worker completion only after durable project receipt;
  - versioned local candidate build and partition verification;
  - completed-but-unsigned project remains complete after reload and routes to artifact verification;
  - refreshed Forge cards/footer remain aligned;
  - resumable and UNKNOWN local-build states remain truthful with no automatic retry.
- Ruff on the two changed Python files: **passed**.
- Git whitespace check: **passed**.
- No full regression suite, package build, APK build, emulator run, physical-phone journey,
  interruption injection, signing, Guardian or Recovery test was run for this checkpoint.

## Guided friction and remaining boundaries

- The bounded Recipe preview and explicit one-decision execution path completed without a dead end.
- The local build completed and survived a normal UI/service reconstruction with its exact receipt.
- The discovered misleading restart state is corrected: local-build completion no longer appears to
  regress, and installation is not presented as the next verified action while artifact trust is
  unresolved.
- The next visible choices are now truthful: finish with the intact local artifact, or continue to
  artifact verification.
- The synthetic process adapter proves deterministic orchestration and persistence only. It does
  not prove real EROFS/AVB/dynamic-partition output correctness, packaging, or physical hardware.

## Guardian, Recovery and safety implications

- Guardian remains the only execution gate. Local build and Recipe receipts grant no installation,
  flash or device authority.
- Exact-device evidence, consent separation, UNKNOWN-on-uncertainty, no blind retry, same-incident
  Recovery and independent verification remain unchanged.
- The correction reduces premature installation routing and does not bypass any gate.
- Bootloader locking/relocking remains permanently prohibited with no override.

## Platform and version-gate status

- Fedora/Linux: genuinely exercised current production Qt widget/service code using the existing
  local dependency environment and offscreen Qt platform.
- Linux host tools: simulated by a deterministic inert adapter; not hardware verified.
- Packaged Fedora artifact: unchanged and not exercised for this checkpoint.
- Windows: unchanged; no Windows claim is made.
- Physical Android and emulator: not used for this journey; no hardware claim is made.
- 5 September 2026 feature freeze: compliant. This is one evidence-backed UI correctness fix in the
  already approved Stage 1 journey, not new capability.
- v0.2 Golden Foundation remains **CLOSED**. Signing, Guardian, Recovery, hardware, publication and
  release gates remain unchanged.

## External actions

- A separate read-only `adb devices -l` / `fastboot devices -l` safety check was performed before
  this journey in response to the creator's unplug question; no device was detected and no
  device-scoped command ran.
- Physical phone operation, emulator use, Recovery, flash, install, APK transfer, signing,
  publication and release: none.
- Tool/dependency download or installation, package rebuild, merge, history rewrite and force-push:
  none.
- Remote action: normal push of these scoped checkpoints to the existing Linux working branch only.
- The protected Companion files, original-checkout Windows drafts, website, assets and unrelated
  user work were untouched.

## Next proposed Build task

Stop for independent Product Assurance review. Do not begin another consequential slice.

## Product Assurance Review Requested

- Confirm the production-widget/service Recipe Forge → local-build → reload journey and unique 7/7
  focused regressions satisfy the bounded Fedora acceptance request.
- Confirm the corrected completion state and `Continue to artifact verification` routing preserve
  the approved separation between local build, artifact trust, installation and Guardian authority.
