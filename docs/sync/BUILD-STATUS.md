# ROMVERSE Build Status

## Authoritative checkpoint

- Product Assurance authorization/base: `a6d9bca06d35c4f0ca8b84ad6ebd990be7e5700a`
  (`Approve durable local-build journey`).
- Implementation and focused-regression checkpoint:
  `14de58e376bbd5cf14369f605bdfd6355f892cca`
  (`Stop unsigned AVB flow at signing boundary`).
- Final handoff checkpoint: the follow-up commit containing this status document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, local candidate to artifact-verification/offline-signing
  readiness.
- Working tree at the implementation checkpoint: clean.

## Exact journey and evidence

- Reused the approved disposable Fedora project and its already durable unsigned local candidate;
  the seven-step local build was not rebuilt.
- Reset only the disposable AVB/signing evidence, then activated the production
  `Continue to artifact verification` action from `BuildControlCenter`.
- Used a bounded synthetic signed source identity, the existing unsigned candidate artifacts and a
  deterministic inert AVBTool adapter. The production `AvbEvidenceService`:
  - rehashed the exact source and candidate images before inspection;
  - bound the AVB receipt to the exact protected source, Device Pack/contract and durable local-build
    receipt;
  - recorded the candidate as unsigned under `signed_custom_rechain` policy;
  - recorded `signing_ready: false` and `phone_changed: false`.
- After the correction, the production Guided action dispatched exactly four expected AVB
  `info_image` inspections and stopped at `Open offline signing ceremony`; no fifth/repeated
  inspection was dispatched.
- The production offline-signing worker exported a content-addressed request through the existing
  ceremony path. It bound exactly:
  - `product.img`, 1,024 bytes,
    SHA-256 `754088c63a3955205ede94ca4425f8feb67fabf9bff2800b9caf8d2406ef59d0`;
  - `vbmeta_system.img`, 6 bytes,
    SHA-256 `a0c6f07a4b3a17fb9348db981de3c5602e2685d626599be1bd909195c694a57b`.
- Offline-signing request digest:
  `531849d40c16c8610d19d0bad9d09189c22b38b17be11246a61aec8b89c31195`.
- The request declares `offline-signing-request-only`, `private_key_included: false` and
  `phone_changed: false`.
- After normal UI/service reconstruction, ROMVERSE reverified the same request and AVB evidence,
  remained `LOCAL BUILD COMPLETE / INSTALL NOT AUTHORIZED`, retained
  `local_candidate_ready: true` / `signing_ready: false`, and offered
  `Open offline signing ceremony`.

## First concrete defect and correction

- Defect reproduced before correction: after the first successful four-image candidate AVB
  inspection, Autopilot immediately dispatched the same inspection again. The inert adapter blocked
  the fifth call, after which the primary action incorrectly became
  `Prepare verified ROM installation…` despite `signing_ready: false`.
- Cause:
  - `_avb_complete` always continued Autopilot after a valid candidate receipt, even when the
    durable result precisely proved that offline-signing evidence was the next boundary;
  - `_finish_autopilot` unconditionally overwrote every durable local-candidate next action with the
    installation action.
- Minimum correction:
  - a valid unsigned candidate AVB receipt terminates automatic resolution at the offline-signing
    boundary;
  - Forge Control strictly reloads/revalidates that exact receipt before presenting the next action;
  - the primary action becomes `Open offline signing ceremony`, never another AVB scan or
    installation handoff;
  - the existing ceremony either exports the exact content-addressed request or exposes its precise
    Device Pack policy requirement;
  - one focused regression proves no repeated Autopilot dispatch and no installation routing.
- No AVB policy, signing eligibility, build, Guardian, Recovery, installation, adapter-execution or
  release authority changed.

## Result classification

- Implemented: truthful unsigned-candidate completion and stable offline-signing handoff.
- Simulated/Tested: yes — one production widget/service/worker artifact-verification and request
  export journey using synthetic inputs and an inert AVBTool adapter; seven unique affected
  regressions; lint clean.
- Hardware Verified: no.
- Released: no.

## Non-double-counted verification

- Production widget/service/worker journey: **1/1 passed** after the correction.
- Pre-correction loop reproduction: first four inspections completed; a fifth duplicate dispatch was
  observed and deliberately rejected by the inert harness.
- Focused regression nodes in one invocation: **7/7 passed**:
  - unsigned AVB completion stops at the offline-signing boundary;
  - reopened unsigned local candidate routes to artifact verification;
  - exact source contract selects full candidate AVB comparison;
  - direct signing action resolves AVBTool before eligibility review;
  - AVB topology truthfully reports an unsigned candidate;
  - AVB parser accepts unsigned evidence without inventing a key;
  - offline ceremony exports no private key and verifies its exact existing import contract.
- Ruff on the two changed Python files: **passed**.
- Git whitespace check: **passed**.
- No full suite, package/APK build, local-candidate rebuild, interruption campaign, emulator,
  physical phone, real private signature, production trust enrollment, Guardian, Recovery,
  installation or release test ran.

## Guided friction and remaining boundaries

- Removed the circular `AVB inspect → AVB inspect` path.
- The user now receives one stable, direct next action after artifact inspection:
  `Open offline signing ceremony`.
- Exporting the request does not pretend that signing is complete. Reload preserves
  `signing_ready: false`, `INSTALL NOT AUTHORIZED`, and the same exact request.
- A protected external signing environment must still perform any real signature. ROMVERSE has no
  private key and this checkpoint did not import a signed result.
- The synthetic AVBTool output proves orchestration, strict parsing, binding, persistence and UI
  routing only; it is not production-key, vendor-firmware or hardware evidence.

## Guardian, Recovery and safety implications

- Guardian remains the only device-execution gate. Artifact inspection and offline request export
  grant no installation, consent, flash or phone authority.
- Candidate/source/contract/local-build digests remain exact and independently reloadable.
- UNKNOWN-on-uncertainty, no blind retry, exact-device evidence, same-incident Recovery and
  independent post-operation verification remain unchanged.
- Bootloader locking/relocking remains permanently prohibited with no override.

## Platform and version-gate status

- Fedora/Linux: genuinely exercised current production Qt widget, service and background-worker
  paths using the existing local dependency environment and offscreen Qt platform.
- AVBTool behavior: simulated by a deterministic inert adapter; no hardware claim.
- Packaged Fedora artifact: unchanged and not exercised for this checkpoint.
- Windows: unchanged; no Windows claim is made.
- Physical Android and emulator: not used; no hardware claim is made.
- 5 September 2026 feature freeze: compliant. This is the first concrete dead-end correction in the
  already approved artifact-verification flow, not new capability.
- v0.2 Golden Foundation remains **CLOSED**. Real signing/trust, Guardian, Recovery, hardware,
  installation, publication and release gates remain closed.

## External actions

- Physical phone operation, device-scoped ADB/Fastboot, emulator, Recovery, flash, install, APK
  transfer, real signing, production trust enrollment, publication and release: none.
- Tool/dependency download or installation, package build, merge, history rewrite and force-push:
  none.
- Remote action: normal push of these scoped Linux checkpoints to the existing working branch only.
- The protected Companion files, original-checkout Windows drafts, website, assets and unrelated
  user work were untouched.

## Next proposed Build task

Stop for independent Product Assurance review. Do not begin another consequential slice.

## Product Assurance Review Requested

- Confirm the exact four-image AVB evidence, content-addressed request export and reload satisfy the
  bounded artifact-verification/offline-signing-readiness milestone.
- Confirm the corrected no-repeat/no-install routing preserves the approved separation between
  artifact evidence, external signing, Guardian consent and physical execution.
